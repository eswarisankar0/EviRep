"""
Tracked pipeline runs: one manifest, dependency-aware freshness, validated publication.

    ./venv/bin/python scripts/run_stage.py 06                 # run stage 06 (staged -> validated -> published)
    ./venv/bin/python scripts/run_stage.py 10h                # any stage id from the registry
    ./venv/bin/python scripts/run_stage.py 06 -- --rank-convention midrank   # extra args go to the stage
    ./venv/bin/python scripts/run_stage.py --status [--json]  # freshness of every stage
    ./venv/bin/python scripts/run_stage.py --adopt            # record existing outputs as the pre-tracking baseline

Single source of truth
  * Stage graph: ui/server.py STAGES (script, inputs, outputs, depends_on), the
    same registry the dashboard shows and tests/test_ui.py checks against the
    scripts. Nothing is duplicated here.
  * Run records: data/run_manifest.json (this module is the only writer; written
    atomically under a file lock). Per stage: last_attempt, last_success; plus a
    bounded history.

Statuses (per stage, derived at read time, never from timestamps alone)
  RUNNING      an attempt is in progress (its process is alive)
  SUCCESS / PARTIAL / ADOPTED   last successful run; ADOPTED = outputs that existed
               before tracking began, fingerprinted by --adopt (not re-run)
  STALE        an input changed since the last success, or an upstream stage is STALE/MODIFIED
  MODIFIED     an output changed outside a tracked run (unvalidated)
  MISSING      a published output no longer exists (deleted or moved outside a tracked run)
  FAILED       the latest attempt failed (the last good output, if any, is retained
               and named; it is not presented as fresh)
  UNTRACKED    outputs exist but no run was ever recorded
  NOT_RUN      no outputs, no record
Concurrency: a launch is refused (StageBusy, exit 3, nothing recorded or written) while the same stage, or any
stage upstream or downstream of it, has a RUNNING attempt whose process is alive.
Content fingerprints are md5 (cached by size + mtime, so polling stays cheap).

Publication
  * Stage 06 supports --output-dir: it runs into data/_runs/<run_id>/out, the
    result is validated (schema, finiteness, pool size, and an independent
    re-computation by scripts/vps_verify.py), and only then each file is moved
    into data/ with os.replace. The previous files are kept in
    data/_runs/<run_id>/previous/.
  * Other stages write into data/ themselves. Their previous outputs (< 50 MB) are
    copied to data/_runs/<run_id>/previous/ first; on failure the new files are
    moved to .../failed/ and the previous ones restored, so the last good output
    survives and the failure is recorded.
"""

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

MANIFEST = "data/run_manifest.json"
LOCK = "data/.run_manifest.lock"
RUNS_DIR = "data/_runs"
BACKUP_LIMIT = 512 * 1024 * 1024   # 01 writes an 89 MB edge list in place; at 50 MB a failed 01 run could not restore it
STAGED = {"06"}                      # stages that accept --output-dir
PARTIAL_ON_EXIT1 = {"04", "05", "04p", "05h", "10a-all"}   # these exit 1 when some compounds failed but outputs are
                                     # usable (E-021; 04p/05h/10a-all added 2026-10-20, E-055 A-1); only when every
                                     # output was rewritten (a traceback also exits 1) and no output reports FAILED
SUCCESS_LIKE = ("SUCCESS", "PARTIAL", "ADOPTED")
#: Only STALE propagates downstream: the upstream stage must be recomputed, so its dependants will change.
#: MODIFIED (an output edited outside a tracked run) does not: a dependant that already consumed the
#: current file is consistent with it (its own input fingerprints decide), but it carries a warning.
PROPAGATES = ("STALE",)
HISTORY = 200
_FP = {}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_stages():
    """The stage registry from ui/server.py (loaded under a private name; no server is started)."""
    spec = importlib.util.spec_from_file_location("_evirep_registry", os.path.join(REPO, "ui", "server.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.STAGES


def fingerprint(root, rel):
    """{'md5','size','mtime_ns'} or None if absent. md5 is recomputed only when size/mtime change."""
    p = os.path.join(root, rel)
    try:
        st = os.stat(p)
    except OSError:
        return None
    key = (os.path.abspath(p), st.st_size, st.st_mtime_ns)
    if key not in _FP:
        h = hashlib.md5()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        _FP[key] = h.hexdigest()
    return {"md5": _FP[key], "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def _fps(root, rels):
    return {r: fingerprint(root, r) for r in rels}


# ------------------------------------------------------------------ manifest
class _Lock:
    def __init__(self, root):
        os.makedirs(os.path.join(root, "data"), exist_ok=True)
        self.fh = open(os.path.join(root, LOCK), "a")

    def __enter__(self):
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


class ManifestError(RuntimeError):
    """data/run_manifest.json exists but cannot be used. It is never overwritten automatically: a corrupt manifest
    is evidence, and replacing it would erase every recorded success (restore it from a snapshot instead)."""


def read_manifest(root):
    p = os.path.join(root, MANIFEST)
    if not os.path.exists(p):
        return {"schema": 1, "stages": {}, "history": []}
    try:
        with open(p, encoding="utf-8") as fh:
            m = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ManifestError(f"{MANIFEST} unreadable ({type(exc).__name__})") from exc
    problem = _structure_problem(m)
    if problem:
        raise ManifestError(f"{MANIFEST} has an unexpected structure ({problem})")
    return m


def _structure_problem(m):
    """The first structural defect of a parsed manifest, or None. Every field status() dereferences is checked, so
    a malformed file is reported (UNKNOWN) instead of crashing the dashboard."""
    if not isinstance(m, dict):
        return "top level is not an object"
    if not isinstance(m.get("stages", {}), dict):
        return "'stages' is not an object"
    if not isinstance(m.get("history", []), list):
        return "'history' is not a list"
    for i, h in enumerate(m.get("history") or []):
        if not isinstance(h, dict):
            return f"history[{i}] is not an object"
    for sid, rec in (m.get("stages") or {}).items():
        if not isinstance(rec, dict):
            return f"stage {sid!r} is not an object"
        for kind in ("last_success", "last_attempt"):
            r = rec.get(kind)
            if r is None:
                continue
            if not isinstance(r, dict):
                return f"{sid}.{kind} is not an object"
            for part in ("inputs", "outputs"):
                if r.get(part) is not None and not isinstance(r[part], dict):
                    return f"{sid}.{kind}.{part} is not an object"
                for rel, fp in (r.get(part) or {}).items():
                    if fp is not None and not isinstance(fp, dict):
                        return f"{sid}.{kind}.{part}[{rel!r}] is not an object"
            for key in ("run_id", "status", "run_dir", "started_utc", "finished_utc", "script_md5"):
                if r.get(key) is not None and not isinstance(r[key], str):
                    return f"{sid}.{kind}.{key} is not a string"
    return None


def check_manifest(root, stages=None):
    """Read-only diagnostic: (ok, problems, summary). Never writes."""
    stages = stages or load_stages()
    try:
        m = read_manifest(root)
    except ManifestError as exc:
        return False, [str(exc)], {}
    ids = {s["id"] for s in stages}
    problems = []
    for sid, rec in (m.get("stages") or {}).items():
        if sid not in ids:
            problems.append(f"stage {sid!r} is recorded but not in the registry")
        for kind in ("last_success", "last_attempt"):
            r = (rec or {}).get(kind)
            if r is None:
                continue
            if not isinstance(r, dict) or not r.get("run_id") or not r.get("status"):
                problems.append(f"{sid}.{kind} lacks run_id/status")
            elif r.get("run_dir") and not os.path.isdir(os.path.join(root, r["run_dir"])):
                problems.append(f"{sid}.{kind} run directory missing: {r['run_dir']}")
    summary = {"stages_recorded": len(m.get("stages") or {}), "history_entries": len(m.get("history") or []),
               "updated_utc": m.get("updated_utc"), "registry_stages_never_recorded":
                   sorted(ids - set(m.get("stages") or {}))}
    return not problems, problems, summary


def _write_manifest(root, m):
    p = os.path.join(root, MANIFEST)
    m["updated_utc"] = now()
    with open(p + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=1, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())              # the rename must never expose a file whose bytes are not on disk
    os.replace(p + ".tmp", p)


def _update(root, fn):
    with _Lock(root):
        m = read_manifest(root)
        fn(m)
        _write_manifest(root, m)
        return m


# ------------------------------------------------------------------ freshness
def _alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


class UnsafeRun(RuntimeError):
    """A run was refused because a failure could not be undone (nothing was written)."""


class StageBusy(RuntimeError):
    """A run was refused because a conflicting attempt is in progress (nothing was written)."""


def _related(stages, stage_id):
    """The stage itself plus every transitive upstream and downstream stage: running any of them
    concurrently would read or write files this stage reads or writes."""
    by = {s["id"]: s for s in stages}
    up, todo = set(), [stage_id]
    while todo:
        for d in by.get(todo.pop(), {}).get("depends_on", []):
            if d not in up:
                up.add(d)
                todo.append(d)
    down, todo = set(), [stage_id]
    while todo:
        cur = todo.pop()
        for s in stages:
            if cur in s["depends_on"] and s["id"] not in down:
                down.add(s["id"])
                todo.append(s["id"])
    return {stage_id} | up | down


def _running_conflicts(m, related):
    """[(stage, run_id, pid)] of attempts recorded as RUNNING whose process is still alive."""
    out = []
    for sid in sorted(related):
        la = ((m.get("stages") or {}).get(sid) or {}).get("last_attempt") or {}
        if la.get("status") == "RUNNING" and _alive(la.get("pid")):
            out.append((sid, la.get("run_id"), la.get("pid")))
    return out


def _topo(stages):
    by = {s["id"]: s for s in stages}
    order, seen = [], set()

    def visit(i):
        if i in seen or i not in by:
            return
        seen.add(i)
        for d in by[i]["depends_on"]:
            visit(d)
        order.append(i)
    for s in stages:
        visit(s["id"])
    return [by[i] for i in order]


def _changed(root, recorded):
    out = []
    for rel, fp in (recorded or {}).items():
        cur = fingerprint(root, rel)
        if (cur or {}).get("md5") != (fp or {}).get("md5"):
            out.append(rel)
    return out


def status(root, stages=None, manifest=None):
    """{stage_id: {...}} dependency-aware; cheap enough to call on every dashboard poll."""
    stages = stages or load_stages()
    if manifest is None:
        try:
            manifest = read_manifest(root)
        except ManifestError as exc:
            # nothing can be called fresh without the run records: every stage is UNKNOWN, with the reason
            return {s["id"]: {"id": s["id"], "name": s["name"], "status": "UNKNOWN", "reasons": [str(exc)],
                              "warnings": [], "unvalidated_upstream": False, "latest_attempt_failed": False,
                              "fresh": False, "retained_run_id": None, "last_success": None, "last_attempt": None,
                              "elapsed_s": None, "upstream": [{"id": d, "status": "UNKNOWN"} for d in s["depends_on"]]}
                    for s in _topo(stages)}
    m = manifest
    res = {}
    for s in _topo(stages):
        rec = m.get("stages", {}).get(s["id"], {})
        ls, la = rec.get("last_success"), rec.get("last_attempt")
        reasons, warnings = [], []
        unvalidated = [d for d in s["depends_on"] if res.get(d, {}).get("status") == "MODIFIED"
                       or res.get(d, {}).get("unvalidated_upstream")]
        if unvalidated:
            warnings.append("built on upstream output(s) changed outside a tracked run (unvalidated): "
                            + ", ".join(unvalidated))
        # A dependency whose latest attempt failed keeps its last validated output (restored); a stage run on top of
        # it uses that retained output. Legitimate, but it must be visible (audit 2026-10-21).
        failed_up = [d for d in s["depends_on"] if res.get(d, {}).get("latest_attempt_failed")]
        if failed_up:
            warnings.append("dependency's latest attempt failed; its last validated output is the one in use: "
                            + ", ".join(failed_up))
        code_fp = (ls or {}).get("script_md5")
        if code_fp and code_fp != _script_md5(s):
            # a warning, not STALE: the outputs still match their inputs, but the code that produced them changed
            warnings.append("stage code changed since the last success (re-run to apply it): " + s["script"])
        if ls is not None:
            # Inputs added to the registry after the last success were never fingerprinted, so _changed cannot see
            # them. Flag the existing ones (an absent optional input is consistent with any past run).
            untracked_in = [i for i in s["inputs"] if i not in (ls.get("inputs") or {})
                            and os.path.exists(os.path.join(root, i))]
            if untracked_in:
                warnings.append("declared input(s) not fingerprinted at the last success (re-run to track them): "
                                + ", ".join(untracked_in))
            untracked_out = [o for o in s["outputs"] if o not in (ls.get("outputs") or {})
                             and os.path.exists(os.path.join(root, o))]
            if untracked_out:
                warnings.append("declared output(s) not fingerprinted at the last success, so edits to them are not "
                                "detected (re-run to track them): " + ", ".join(untracked_out))
        if ls is None:
            present = [o for o in s["outputs"] if os.path.exists(os.path.join(root, o))]
            st = "NOT_RUN" if not present else ("UNTRACKED" if len(present) == len(s["outputs"]) else "UNTRACKED")
            if present and len(present) < len(s["outputs"]):
                reasons.append(f"{len(s['outputs']) - len(present)} declared output(s) missing")
        else:
            mod_out = _changed(root, ls.get("outputs"))
            mod_in = _changed(root, ls.get("inputs"))
            up = [d for d in s["depends_on"] if res.get(d, {}).get("status") in PROPAGATES]
            gone = [o for o in mod_out if not os.path.exists(os.path.join(root, o))]
            if gone:
                st = "MISSING"
                reasons.append("published output missing: " + ", ".join(gone))
            elif mod_out:
                st = "MODIFIED"
                reasons.append("output changed outside a tracked run: " + ", ".join(mod_out))
            elif mod_in or up:
                st = "STALE"
                if mod_in:
                    reasons.append("input changed since last success: " + ", ".join(mod_in))
                if up:
                    reasons.append("upstream stage stale: " + ", ".join(up))
            else:
                st = ls["status"]
        retained, attempt_failed = None, False
        if la and la.get("status") == "RUNNING":
            if _alive(la.get("pid")):
                st, retained = "RUNNING", (ls or {}).get("run_id")
            else:
                reasons.append(f"attempt {la['run_id']} was interrupted (runner process gone)")
                if _alive(la.get("child_pid")):
                    reasons.append(f"its stage process (pid {la['child_pid']}) is still running orphaned: outputs may "
                                   "still change; stop it before restoring")
                if st == "MODIFIED":
                    reasons.append(f"the output change came from the interrupted run, not an outside edit; restore the "
                                   f"last validated outputs with: ./venv/bin/python scripts/run_stage.py --restore {s['id']}")
                attempt_failed = True
                if st not in PROPAGATES + ("MODIFIED", "MISSING"):
                    st = "FAILED"
                retained = (ls or {}).get("run_id")
        elif la and la.get("status") == "FAILED" and (not ls or la["run_id"] != ls["run_id"]):
            reasons.append(f"latest attempt {la['run_id']} failed" + (
                f"; showing retained result of run {ls['run_id']}" if ls else "; no successful result exists"))
            if st not in PROPAGATES + ("MODIFIED", "MISSING"):
                st = "FAILED"
            attempt_failed = True
            retained = (ls or {}).get("run_id")
        elapsed = _seconds(la.get("started_utc"), now()) if st == "RUNNING" else None
        activity = _last_activity(root, la.get("run_dir")) if st == "RUNNING" else None
        upstream = [{"id": d, "status": res.get(d, {}).get("status")} for d in s["depends_on"]]
        res[s["id"]] = {"id": s["id"], "name": s["name"], "status": st, "reasons": reasons, "warnings": warnings,
                        "elapsed_s": elapsed, "upstream": upstream, "last_activity": activity,
                        # runs before script fingerprinting (C-78) and ADOPTED baselines cannot reveal code drift
                        "code_fingerprint_recorded": bool((ls or {}).get("script_md5")),
                        "unvalidated_upstream": bool(unvalidated), "latest_attempt_failed": attempt_failed,
                        "fresh": st in SUCCESS_LIKE, "retained_run_id": retained,
                        "last_success": _summary(ls), "last_attempt": _summary(la)}
    return res


def _script_md5(s):
    """Fingerprint of the stage's script and related scripts (None if a file is missing)."""
    h = hashlib.md5()
    for rel in [s["script"]] + list(s.get("related_scripts", [])):
        p = rel if os.path.isabs(rel) else os.path.join(REPO, rel)
        try:
            with open(p, "rb") as fh:
                h.update(fh.read())
        except OSError:
            return None
    return h.hexdigest()


def _seconds(a, b):
    try:
        return round((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds())
    except (TypeError, ValueError):
        return None


def _last_activity(root, run_dir):
    """Last non-empty line of a running stage's log and its age: the only progress signal stages expose (no
    stage reports a reliable percentage, so none is computed)."""
    if not run_dir:
        return None
    runs = os.path.realpath(os.path.join(root, RUNS_DIR))
    p = os.path.realpath(os.path.join(root, run_dir, "log.txt"))
    if os.path.dirname(os.path.dirname(p)) != runs:      # a manifest cannot point the dashboard at other files
        return None
    try:
        with open(p, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 4096))
            lines = [x for x in fh.read().decode("utf-8", "replace").splitlines() if x.strip()]
        age = round(datetime.now(timezone.utc).timestamp() - os.path.getmtime(p))
    except OSError:
        return None
    return {"line": lines[-1][-300:] if lines else None, "log_age_s": age}


def _summary(r):
    if not r:
        return None
    out = {k: r.get(k) for k in ("run_id", "status", "started_utc", "finished_utc", "exit_code", "scoring",
                                 "validation_ok", "diagnostics")}
    out["duration_s"] = _seconds(r.get("started_utc"), r.get("finished_utc"))
    out["log"] = f"{r['run_dir']}/log.txt" if r.get("run_dir") else None
    return out


# ------------------------------------------------------------------ validation
def _validate_file(path, rel):
    """Generic checks; returns list of problems."""
    if not os.path.exists(path):
        return [f"{rel}: missing"]
    if os.path.getsize(path) == 0:
        return [f"{rel}: empty"]
    try:
        if rel.endswith(".csv"):
            import pandas as pd
            df = pd.read_csv(path)
            if df.empty:
                return [f"{rel}: no rows"]
        elif rel.endswith(".jsonl"):
            with open(path, encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    if line.strip():
                        json.loads(line)
        elif rel.endswith(".json"):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and "run_status" in data:
                from agent_contract import validate_envelope
                validate_envelope(data)
                if data["run_status"] == "FAILED":
                    return [f"{rel}: agent reported run_status FAILED"]
    except Exception as exc:  # malformed output is a validation failure, reported, never ignored
        return [f"{rel}: {type(exc).__name__}: {str(exc)[:150]}"]
    return []


def validate_vps(root, scores_path, convention="legacy"):
    """Stage-06 specific: schema, finiteness, ranges, and the independent re-computation."""
    import math

    import pandas as pd
    import vps_verify  # noqa: E402
    problems = []
    df = pd.read_csv(scores_path)
    need = ["compound_name", "r_proximity", "r_clinical", "r_literature", "r_safety", "r_molecular",
            "VPS_equal", "VPS_equal_5d", "label", "dimensions_missing", "n_dimensions_measured"]
    miss = [c for c in need if c not in df.columns]
    if miss:
        return [f"vps_scores_v2.csv: missing columns {miss}"], convention
    if df["compound_name"].duplicated().any():
        problems.append("duplicate compounds")
    for c in need[1:8]:
        bad = df[c].map(lambda x: not (isinstance(x, (int, float)) and math.isfinite(x) and 0 <= x <= 1)).sum()
        if bad:
            problems.append(f"{c}: {bad} value(s) non-finite or outside [0, 1]")
    if not set(df["label"].unique()) <= {0, 1}:
        problems.append("label not binary")
    conv = convention
    try:
        expected, _ = vps_verify.recompute(root, convention)
        res = vps_verify.compare(expected, scores_path)
        if not res["ok"]:
            problems.append(f"independent re-computation disagrees: {res['problems'][:3]} {list(res['rank_differences'])[:3]}")
    except Exception as exc:
        problems.append(f"independent re-computation failed: {type(exc).__name__}: {exc}")
    return problems, conv


# ------------------------------------------------------------------ run
def run(stage_id, root=".", extra_args=(), stages=None, python=sys.executable, skip_fresh=False):
    root = os.path.abspath(root)
    stages = stages or load_stages()
    by = {s["id"]: s for s in stages}
    if stage_id not in by:
        raise SystemExit(f"unknown stage {stage_id!r}; known: {', '.join(by)}")
    if skip_fresh and not extra_args:
        cur = status(root, stages)[stage_id]
        if cur["fresh"] and not cur["warnings"]:
            # identical inputs and untouched outputs since the last success: nothing to recompute
            return {**(cur["last_success"] or {}), "status": "SKIPPED_FRESH", "run_dir": None,
                    "validation_ok": True, "validation_problems": []}
    s = by[stage_id]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{stage_id}-{secrets.token_hex(2)}"
    rundir = os.path.join(root, RUNS_DIR, run_id)
    args = list(s.get("run_args", [])) + list(extra_args)
    rec = {"run_id": run_id, "stage": stage_id, "script": s["script"], "args": args, "started_utc": now(),
           "pid": os.getpid(), "status": "RUNNING", "inputs": _fps(root, s["inputs"]), "run_dir": os.path.relpath(rundir, root),
           "script_md5": _script_md5(s)}
    if stage_id == "06":
        conv = args[args.index("--rank-convention") + 1] if "--rank-convention" in args else "legacy"
        rec["scoring"] = {"model": "equal-weight 4d/5d percentile-rank fusion (D-002, D-004)", "rank_convention": conv,
                          "baseline_lineage": "data/vps_scores_v2.csv published by this run"}
    related = _related(stages, stage_id)
    if stage_id not in STAGED:
        # Fail closed: a stage that writes in place must be able to restore its previous outputs after a failure.
        too_big = [o for o in s["outputs"] if os.path.exists(os.path.join(root, o))
                   and os.path.getsize(os.path.join(root, o)) > BACKUP_LIMIT]
        if too_big:
            raise UnsafeRun(f"stage {stage_id} not started: output(s) larger than the backup limit "
                            f"({BACKUP_LIMIT // (1024 * 1024)} MB) could not be restored after a failure: {too_big}")

    def claim(m):
        # check and claim under one manifest lock, so two launches cannot both start
        busy = _running_conflicts(m, related)
        if busy:
            raise StageBusy(f"stage {stage_id} not started: conflicting run(s) in progress: "
                            + ", ".join(f"{sid} ({rid}, pid {pid})" for sid, rid, pid in busy))
        m.setdefault("stages", {}).setdefault(stage_id, {})["last_attempt"] = rec
    _update(root, claim)
    os.makedirs(rundir)

    prev = os.path.join(rundir, "previous")
    before = {o: (fingerprint(root, o) or {}).get("mtime_ns") for o in s["outputs"]}
    backed, skipped = [], []
    for o in s["outputs"]:
        p = os.path.join(root, o)
        if os.path.exists(p):
            if os.path.getsize(p) <= BACKUP_LIMIT:
                os.makedirs(prev, exist_ok=True)
                shutil.copy2(p, os.path.join(prev, os.path.basename(o)))
                backed.append(o)
            else:
                skipped.append(o)
    staged = stage_id in STAGED
    out_dir = os.path.join(rundir, "out")
    script = s["script"] if os.path.isabs(s["script"]) else os.path.join(REPO, s["script"])
    cmd = [python, script] + (["--output-dir", out_dir] if staged else []) + args
    with open(os.path.join(rundir, "log.txt"), "w", encoding="utf-8") as log:
        env = dict(os.environ)
        timeout = s.get("timeout_s")
        child = subprocess.Popen(cmd, cwd=root, stdout=log, stderr=subprocess.STDOUT, env=env)
        # record the stage process, so a runner that dies cannot leave an untracked process writing outputs
        _update(root, lambda m: (m.get("stages", {}).get(stage_id, {}).get("last_attempt") or {}).__setitem__(
            "child_pid", child.pid))
        try:
            code = child.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:      # only this run's own child is killed
            child.kill()
            child.wait()
            code, timed_out = -9, True
            log.write(f"\n[run_stage] TIMEOUT: stage exceeded timeout_s={timeout}; its process was killed\n")
    diags = []
    if timed_out:
        diags.append({"level": "error", "code": "TIMEOUT",
                      "message": f"exceeded the stage timeout ({timeout} s); process killed, previous outputs restored"})
    if skipped:
        diags.append({"level": "warn", "code": "NO_BACKUP", "message": f"not backed up (> {BACKUP_LIMIT // (1024 * 1024)} MB): {skipped}"})
    loc = (lambda o: os.path.join(out_dir, os.path.basename(o))) if staged else (lambda o: os.path.join(root, o))
    problems = [p for o in s["outputs"] for p in _validate_file(loc(o), o)]
    if stage_id == "06" and not problems:
        vp, _ = validate_vps(root, loc("data/vps_scores_v2.csv"), rec["scoring"]["rank_convention"])
        problems += vp
    # Outputs this run did not write. A non-staged stage that exits without writing leaves the previous
    # files in place, and they would validate as if they were this run's result.
    stale_out = [] if staged else [o for o in s["outputs"]
                                   if before[o] is not None and (fingerprint(root, o) or {}).get("mtime_ns") == before[o]]
    if code == 0 and not problems:
        st = "SUCCESS"
        if stale_out:
            st = "PARTIAL"
            diags.append({"level": "warn", "code": "NOT_REWRITTEN",
                          "message": f"exit 0 but output(s) not rewritten by this run: {stale_out}"})
        for o in s["outputs"]:
            if o.endswith(".json"):
                try:
                    if json.load(open(loc(o))).get("run_status") == "PARTIAL":
                        st = "PARTIAL"
                except (OSError, ValueError, AttributeError):
                    pass
    elif code == 1 and stage_id in PARTIAL_ON_EXIT1 and not problems and not stale_out:
        st = "PARTIAL"
        diags.append({"level": "warn", "code": "INCOMPLETE", "message": f"exit {code}: some compounds failed (see failure file)"})
    else:
        st = "FAILED"
        diags.append({"level": "error", "code": "EXIT" if code else "VALIDATION",
                      "message": (f"exit code {code}; " if code else "") + "; ".join(problems[:5]) + f" (log: {rec['run_dir']}/log.txt)"})
    if st in SUCCESS_LIKE and staged:
        for o in s["outputs"]:
            os.replace(loc(o), os.path.join(root, o))      # atomic per file; manifest updated only afterwards
    elif st == "FAILED" and not staged:
        failed = os.path.join(rundir, "failed")
        for o in s["outputs"]:
            p = os.path.join(root, o)
            if o in backed:
                os.makedirs(failed, exist_ok=True)
                if os.path.exists(p):
                    shutil.move(p, os.path.join(failed, os.path.basename(o)))
                shutil.copy2(os.path.join(prev, os.path.basename(o)), p + ".restore")
                os.replace(p + ".restore", p)
        diags.append({"level": "info", "code": "RESTORED", "message": f"previous outputs restored: {backed}"})
    rec.update({"finished_utc": now(), "exit_code": code, "status": st, "validation_ok": not problems,
                "validation_problems": problems[:20], "outputs": _fps(root, s["outputs"]),
                "published": st in SUCCESS_LIKE, "previous_dir": os.path.relpath(prev, root) if backed else None,
                "diagnostics": diags})
    rec.pop("pid", None)

    def fin(m):
        e = m.setdefault("stages", {}).setdefault(stage_id, {})
        e["last_attempt"] = rec
        if st in SUCCESS_LIKE:
            e["last_success"] = rec
        m.setdefault("history", []).append({k: rec[k] for k in ("run_id", "stage", "status", "started_utc", "finished_utc", "exit_code")})
        m["history"] = m["history"][-HISTORY:]
    _update(root, fin)
    return rec


def restore(stage_id, root, stages=None):
    """Put back the last validated outputs after an interrupted or failed run, from the copies that run saved in
    its run directory (previous/). Only files whose md5 equals the last success's fingerprint are restored, nothing
    else is touched, and it refuses while the interrupted run's processes are alive. Returns (ok, message)."""
    stages = stages or load_stages()
    s = {x["id"]: x for x in stages}.get(stage_id)
    if s is None:
        return False, f"unknown stage {stage_id!r}"
    rec = (read_manifest(root).get("stages") or {}).get(stage_id) or {}
    ls, la = rec.get("last_success") or {}, rec.get("last_attempt") or {}
    if not ls or not la or la.get("run_id") == ls.get("run_id"):
        return False, "the latest attempt is the last success: nothing to restore"
    if la.get("status") not in ("RUNNING", "FAILED"):
        return False, f"latest attempt status {la.get('status')!r} is not an interrupted or failed run"
    for pid in (la.get("pid"), la.get("child_pid")):
        if la.get("status") == "RUNNING" and _alive(pid):
            return False, f"process {pid} of the interrupted run is still alive; stop it first"
    prev = os.path.join(root, la.get("run_dir") or "", "previous")
    runs = os.path.realpath(os.path.join(root, RUNS_DIR))
    if os.path.dirname(os.path.dirname(os.path.realpath(prev))) != runs or not os.path.isdir(prev):
        return False, "the attempt saved no previous outputs"
    restored, already = [], []
    for o in s["outputs"]:
        want = ((ls.get("outputs") or {}).get(o) or {}).get("md5")
        cur = (fingerprint(root, o) or {}).get("md5")
        if cur == want:
            already.append(o)
            continue
        src = os.path.join(prev, os.path.basename(o))
        with open(src, "rb") as fh:
            if not want or hashlib.md5(fh.read()).hexdigest() != want:
                return False, f"saved copy of {o} does not match the last success; not restored"
        shutil.copy2(src, os.path.join(root, o) + ".restore")
        os.replace(os.path.join(root, o) + ".restore", os.path.join(root, o))
        restored.append(o)

    def mark(m):
        a = m["stages"][stage_id]["last_attempt"]
        if a.get("run_id") == la.get("run_id"):
            a.update(status="FAILED", finished_utc=a.get("finished_utc") or now())
            a.pop("pid", None)
            a.setdefault("diagnostics", []).append({"level": "info", "code": "RESTORED_BY_COMMAND",
                                                    "message": f"validated outputs restored: {restored}"})
    _update(root, mark)
    return True, f"restored {restored or 'nothing'}; already valid {already}"


def attest(stage_id, root, copy_root, stages=None):
    """Record a code fingerprint for a last success that lacks one (ADOPTED baselines, runs before C-78), ONLY when
    an isolated copy proves it: the copy's last success of this stage ran the CURRENT script and produced outputs
    byte-identical (md5) to the live ones. Outputs are never touched. Returns (ok, reason)."""
    stages = stages or load_stages()
    s = {x["id"]: x for x in stages}.get(stage_id)
    if s is None:
        return False, f"unknown stage {stage_id!r}"
    code = _script_md5(s)
    copy_ls = ((read_manifest(copy_root).get("stages") or {}).get(stage_id) or {}).get("last_success") or {}
    if copy_ls.get("status") not in ("SUCCESS", "PARTIAL"):
        return False, "the copy has no executed success for this stage"
    if copy_ls.get("script_md5") != code:
        return False, "the copy's run used different code than the current script"
    for o in s["outputs"]:
        live_fp, copy_fp = fingerprint(root, o), (copy_ls.get("outputs") or {}).get(o)
        if not live_fp or not copy_fp or live_fp.get("md5") != copy_fp.get("md5"):
            return False, f"output differs from the isolated reproduction: {o}"
    result = {}

    def put(m):
        ls = ((m.get("stages") or {}).get(stage_id) or {}).get("last_success")
        if not ls:
            result["r"] = (False, "no live last success to attest")
            return
        if ls.get("script_md5"):
            result["r"] = (False, "already has a code fingerprint")
            return
        ls["script_md5"] = code
        ls["code_fingerprint_attested"] = {"method": "byte-identical isolated reproduction by the current script",
                                           "copy_run_id": copy_ls.get("run_id"), "attested_utc": now()}
        result["r"] = (True, f"attested by copy run {copy_ls.get('run_id')}")
    _update(root, put)
    return result["r"]


def run_sequence(stage_ids, root=".", stages=None, skip_fresh=True):
    """Run the given stages in dependency order, one at a time, through run(). A stage whose upstream (within the
    sequence) failed, was refused or was blocked is not started and is reported BLOCKED. Fresh stages are skipped
    (unchanged inputs and outputs). Returns [{stage, status, run_id, detail}] in execution order."""
    stages = stages or load_stages()
    by = {s["id"]: s for s in stages}
    unknown = [i for i in stage_ids if i not in by]
    if unknown:
        raise SystemExit(f"unknown stage(s) {unknown}")
    wanted = set(stage_ids)
    order = [s["id"] for s in _topo(stages) if s["id"] in wanted]
    bad, out = set(), []
    for sid in order:
        upstream_bad = sorted(_upstream_ids(stages, sid) & bad)
        if upstream_bad:
            out.append({"stage": sid, "status": "BLOCKED", "run_id": None,
                        "detail": "not started: upstream in this sequence did not succeed: " + ", ".join(upstream_bad)})
            bad.add(sid)
            continue
        try:
            rec = run(sid, root, stages=stages, skip_fresh=skip_fresh)
        except (StageBusy, UnsafeRun, ManifestError) as exc:
            out.append({"stage": sid, "status": "REFUSED", "run_id": None, "detail": str(exc)})
            bad.add(sid)
            continue
        out.append({"stage": sid, "status": rec["status"], "run_id": rec.get("run_id"),
                    "detail": None if rec["status"] in SUCCESS_LIKE + ("SKIPPED_FRESH",) else
                    "; ".join(d.get("message", "") for d in rec.get("diagnostics") or [])[:300]})
        if rec["status"] not in SUCCESS_LIKE + ("SKIPPED_FRESH",):
            bad.add(sid)
    return out


def _upstream_ids(stages, stage_id):
    by = {s["id"]: s for s in stages}
    up, todo = set(), [stage_id]
    while todo:
        for d in by.get(todo.pop(), {}).get("depends_on", []):
            if d not in up:
                up.add(d)
                todo.append(d)
    return up


def adopt(root=".", stages=None):
    """Record every stage whose declared outputs all exist as ADOPTED (pre-tracking baseline, not re-run)."""
    root = os.path.abspath(root)
    stages = stages or load_stages()
    done = []
    for s in stages:
        if not s["outputs"] or not all(os.path.exists(os.path.join(root, o)) for o in s["outputs"]):
            continue
        rec = {"run_id": f"adopted-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{s['id']}", "stage": s["id"],
               "script": s["script"], "status": "ADOPTED", "started_utc": None, "finished_utc": now(), "exit_code": None,
               "inputs": _fps(root, s["inputs"]), "outputs": _fps(root, s["outputs"]), "published": True,
               "diagnostics": [{"level": "info", "code": "ADOPTED",
                                "message": "outputs existed before run tracking; fingerprinted, not re-run"}]}
        if s["id"] == "06":
            problems, conv = validate_vps(root, os.path.join(root, "data/vps_scores_v2.csv"))
            rec.update({"validation_ok": not problems, "validation_problems": problems,
                        "scoring": {"model": "equal-weight 4d/5d percentile-rank fusion (D-002, D-004)",
                                    "rank_convention": conv, "baseline_lineage": "published baseline 2026-10-14 07:50:56"}})
        done.append(s["id"])

        def put(m, s=s, rec=rec):
            e = m.setdefault("stages", {}).setdefault(s["id"], {})
            if "last_success" not in e:            # never overwrite a tracked run with an adoption
                e["last_success"] = rec
                e.setdefault("last_attempt", rec)
        _update(root, put)
    return done


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description="Run a pipeline stage with tracking, validation and safe publication")
    ap.add_argument("stage", nargs="*")
    ap.add_argument("--root", default=REPO)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--adopt", action="store_true")
    ap.add_argument("--check-manifest", action="store_true", help="read-only manifest diagnostic (exit 2 on problems)")
    ap.add_argument("--restore", metavar="STAGE",
                    help="after an interrupted/failed run: restore the last validated outputs (md5-verified)")
    ap.add_argument("--attest-from", metavar="COPY_ROOT",
                    help="with stage ids: record code fingerprints proven by byte-identical runs in COPY_ROOT")
    ap.add_argument("--sequence", nargs="+", metavar="STAGE",
                    help="run these stages in dependency order (fresh ones skipped; dependants of a failure BLOCKED)")
    ap.add_argument("--skip-fresh", action="store_true",
                    help="do nothing when the stage is already fresh (same inputs, outputs untouched)")
    a = ap.parse_args(argv)
    if a.check_manifest:
        ok, problems, summary = check_manifest(os.path.abspath(a.root))
        print(json.dumps({"ok": ok, "problems": problems, "summary": summary}, indent=1))
        return 0 if ok else 2
    try:
        return _main(a, extra)
    except ManifestError as exc:
        print(f"{exc}; nothing was run or written. Diagnose with --check-manifest; restore the file from a recovery "
              f"snapshot or data/_runs history (it is never overwritten automatically).", file=sys.stderr)
        return 2


def _main(a, extra):
    if a.restore:
        ok, msg = restore(a.restore, os.path.abspath(a.root))
        print(f"{a.restore}: {'RESTORED' if ok else 'NOT restored'} - {msg}")
        return 0 if ok else 1
    if a.attest_from:
        rc = 0
        for sid in a.stage:
            ok, reason = attest(sid, os.path.abspath(a.root), os.path.abspath(a.attest_from))
            print(f"{sid}: {'ATTESTED' if ok else 'NOT attested'} - {reason}")
            rc = rc or (0 if ok else 1)
        return rc
    if len(a.stage) > 1:
        print("run one stage at a time, or use --sequence", file=sys.stderr)
        return 2
    a.stage = a.stage[0] if a.stage else None
    if a.sequence:
        res = run_sequence(a.sequence, a.root)
        for r in res:
            print(f"{r['stage']}: {r['status']}" + (f" ({r['run_id']})" if r["run_id"] else "")
                  + (f" - {r['detail']}" if r["detail"] else ""))
        print("SEQUENCE " + json.dumps(res))
        return 0 if all(r["status"] in SUCCESS_LIKE + ("SKIPPED_FRESH",) for r in res) else 1
    if a.adopt:
        print("adopted:", ", ".join(adopt(a.root)) or "nothing")
        return 0
    if a.status or not a.stage:
        st = status(os.path.abspath(a.root))
        if a.json:
            print(json.dumps(st, indent=1))
        else:
            for v in st.values():
                ls = v["last_success"] or {}
                print(f"{v['id']:>5} {v['status']:<10} last success {ls.get('run_id') or '-':<40} {'; '.join(v['reasons'])[:120]}")
        return 0
    try:
        rec = run(a.stage, a.root, extra, skip_fresh=a.skip_fresh)
    except StageBusy as exc:
        print(exc, file=sys.stderr)
        return 3
    except UnsafeRun as exc:
        print(exc, file=sys.stderr)
        return 4
    if rec["status"] == "SKIPPED_FRESH":
        print(f"{a.stage}: fresh (last success {rec['run_id']}); nothing to do")
        return 0
    print(f"{rec['run_id']}: {rec['status']} (exit {rec['exit_code']}); validation "
          f"{'ok' if rec['validation_ok'] else rec['validation_problems'][:3]}; log {rec['run_dir']}/log.txt")
    return 0 if rec["status"] in SUCCESS_LIKE else 1


if __name__ == "__main__":
    sys.exit(main())
