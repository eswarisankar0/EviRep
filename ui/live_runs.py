"""
Live Pipeline run controls for the dashboard (2026-10-20). Every launch goes through scripts/run_stage.py: this
module never runs a stage itself, never bypasses the runner's E-035 lock, and adds no second source of run state
(data/run_manifest.json stays authoritative; the launch records here only say "the dashboard asked for this").

Policy (enforced server-side; the UI only mirrors it):
  ALLOWED   offline stages whose outputs are not protected artefacts
  CONFIRM   stages that may contact an external service for uncached items; the request must carry confirm=true
  REFUSED   everything that rewrites a protected or approved artefact (candidate pool, labels, score dimensions,
            the approved score, the evaluation report) or needs live services without a cache. Those are owner
            decisions, run from the command line in an isolated copy first.
Not offered: cancellation. Killing the runner mid-stage would skip its restore-on-failure step, so a cancel button
could leave half-written outputs; no reliable cancellation exists.
"""
import json
import os
import re
import secrets
import subprocess
import sys
import threading
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_STAGE = os.path.join(os.path.dirname(HERE), "scripts", "run_stage.py")
LAUNCH_DIR = "data/_runs/_ui_launches"
MAX_RECORDS = 30

#: The approved / frozen artefacts (sha256-checked in every recovery snapshot). A stage writing any of them is never
#: launchable from the browser.
PROTECTED_ARTEFACTS = frozenset({
    "data/ground_truth_postcutoff.csv", "data/ground_truth_postcutoff_clean.csv", "data/vps_scores_v2.csv",
    "data/clinical_maturity_precutoff.csv", "data/clinical_maturity_precutoff_clean.csv",
    "data/label_role_exclusions.csv", "data/pd_candidates.csv", "data/pd_candidates_filtered.csv",
    "data/pd_candidates_full.csv", "data/network_proximity.csv", "data/safety_signal.csv",
    "data/literature_independence.csv", "data/molecular_pathway.csv", "data/molecular_pathway_evidence.jsonl",
    "data/feature_trial_roles_td038.csv", "data/clinicaltrials_match_audit.csv", "data/vps_evaluation_report.json",
    "data/conflict_claims_curated.json", "data/cache/ctgov_precutoff_trials.json"})
ALLOWED = ("10a", "10a-all", "10b", "10c", "10d", "10e", "10f", "10g", "10h", "review", "07")
CONFIRM = {"04p": "may query PubMed for compounds without a valid cache entry",
           "05h": "may query DailyMed for labels without a cached version history",
           "diag": "queries ClinicalTrials.gov once per linked trial (about 250 requests)"}
LIVE_ONLY = {"04b": "re-runs stage-04 PubMed/Semantic Scholar queries; its provenance guard refuses content drift"}

_PROCS = {}                 # launch_id -> Popen (this server process only)
_LAUNCH_ID_RE = re.compile(r"^\d{8}T\d{6}Z-ui-[0-9a-f]{6}$")
_LOCK = threading.Lock()    # serialises launch decisions inside this server


def policy(stage):
    """(class, reason) for one registry stage."""
    prot = sorted(set(stage["outputs"]) & PROTECTED_ARTEFACTS)
    if prot:
        return "REFUSED", ("rewrites protected/approved artefacts (" + ", ".join(prot) + "); owner decision - run "
                           "from the command line in an isolated copy first")
    if stage["id"] in LIVE_ONLY:
        return "REFUSED", LIVE_ONLY[stage["id"]] + "; run from the command line"
    if stage["id"] in CONFIRM:
        return "CONFIRM", CONFIRM[stage["id"]]
    if stage["id"] in ALLOWED:
        return "ALLOWED", "offline; outputs are not protected artefacts"
    return "REFUSED", "not on the dashboard allow-list"


def new_nonce():
    return secrets.token_urlsafe(32)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json_atomic(path, obj):
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1)
    os.replace(path + ".tmp", path)


class LaunchError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def launch(root, stages, status, request):
    """Validate and start one launch. `request` = {"stage": id} | {"pipeline": true}, optional "confirm": true.
    `status` = scripts/run_stage.status() output (for an early conflict answer; the runner's lock decides).
    Returns the launch record. Raises LaunchError(http_code, message)."""
    by = {s["id"]: s for s in stages}
    if not isinstance(request, dict) or set(request) - {"stage", "pipeline", "confirm"}:
        raise LaunchError(400, "body must be {\"stage\": id} or {\"pipeline\": true}, optional \"confirm\": true")
    if request.get("pipeline") is True and "stage" not in request:
        ids = [s["id"] for s in stages if policy(s)[0] == "ALLOWED"]
        kind = "pipeline"
    elif isinstance(request.get("stage"), str) and request["stage"] in by and "pipeline" not in request:
        sid = request["stage"]
        cls, reason = policy(by[sid])
        if cls == "REFUSED":
            raise LaunchError(403, f"stage {sid} cannot be started from the dashboard: {reason}")
        if cls == "CONFIRM" and request.get("confirm") is not True:
            raise LaunchError(428, f"stage {sid} {reason}; repeat with confirmation")
        ids, kind = [sid], "stage"
    else:
        raise LaunchError(400, "unknown stage or malformed request")
    with _LOCK:
        busy = [k for k, v in status.items() if v.get("status") == "RUNNING"]
        if busy:
            raise LaunchError(409, "a tracked run is in progress (" + ", ".join(busy) + "); wait for it to finish")
        pending = [lid for lid, p in _PROCS.items() if p.poll() is None]
        if pending:
            raise LaunchError(409, "a dashboard launch is still starting or running: " + ", ".join(pending))
        lid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-ui-" + secrets.token_hex(3)
        d = os.path.join(root, LAUNCH_DIR)
        log_rel = f"{LAUNCH_DIR}/{lid}.log"
        cmd = [sys.executable, RUN_STAGE] + (["--sequence"] + ids if kind == "pipeline" else ids) + ["--root", root]
        try:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(root, log_rel), "w", encoding="utf-8") as log:
                proc = subprocess.Popen(cmd, cwd=root, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                        start_new_session=True, close_fds=True)   # survives a server restart
        except OSError as exc:      # nothing started: say what could not be written or executed
            raise LaunchError(500, f"not started: {type(exc).__name__} writing {LAUNCH_DIR}/ or starting the runner "
                                   f"({os.path.basename(sys.executable)} {os.path.relpath(RUN_STAGE, os.path.dirname(HERE))}); "
                                   "check that data/_runs is writable and the virtual environment exists") from exc
        _PROCS[lid] = proc
        rec = {"launch_id": lid, "kind": kind, "stages": ids, "requested_utc": _now(), "pid": proc.pid,
               "log": log_rel, "confirmed": bool(request.get("confirm")), "exit_code": None, "finished_utc": None,
               "command": "scripts/run_stage.py " + " ".join((["--sequence"] if kind == "pipeline" else []) + ids)}
        _write_json_atomic(os.path.join(d, lid + ".json"), rec)
    threading.Thread(target=_reap, args=(os.path.join(d, lid + ".json"), proc), daemon=True,
                     name=f"reap-{lid}").start()
    return rec


def _reap(record_path, proc):
    """Wait for this launch's runner, reap it at once (no zombie) and record its exit code, whether or not any
    page is polling. The run manifest written by the runner stays the authority on the stage outcome."""
    code = proc.wait()
    with _LOCK:
        try:
            with open(record_path, encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            return
        if rec.get("exit_code") is None:
            rec.update(exit_code=code, finished_utc=_now())
            _write_json_atomic(record_path, rec)


def _tail(path, n=12):
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 8192))
            return [x for x in fh.read().decode("utf-8", "replace").splitlines() if x.strip()][-n:]
    except OSError:
        return []


def _launch_log(root, launch_id):
    """The log of a launch, derived from its validated id - never from a path stored in the record, so an edited
    record cannot make the dashboard read other files."""
    if not isinstance(launch_id, str) or not _LAUNCH_ID_RE.match(launch_id):
        return ""
    return os.path.join(root, LAUNCH_DIR, launch_id + ".log")


def _sequence(tail):
    """Per-stage outcome of a 'run all' launch, from the runner's own SEQUENCE line (None for single stages)."""
    for line in reversed(tail):
        if line.startswith("SEQUENCE "):
            try:
                rows = json.loads(line[len("SEQUENCE "):])
                return [{k: r.get(k) for k in ("stage", "status", "detail")} for r in rows if isinstance(r, dict)]
            except ValueError:
                return None
    return None


def launches(root):
    """Recent dashboard launches, newest first, with their real process outcome where this server knows it."""
    d = os.path.join(root, LAUNCH_DIR)
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted((x for x in os.listdir(d) if x.endswith(".json")), reverse=True)[:MAX_RECORDS]:
        p = os.path.join(d, f)
        try:
            with open(p, encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            out.append({"launch_id": f[:-5], "state": "UNREADABLE"})
            continue
        proc = _PROCS.get(rec.get("launch_id"))
        if rec.get("exit_code") is None and proc is not None and proc.poll() is not None:
            rec.update(exit_code=proc.returncode, finished_utc=_now())
            _write_json_atomic(p, rec)
        if rec.get("exit_code") is not None:
            rec["state"] = "EXITED"
        elif proc is not None:
            rec["state"] = "RUNNING"
        else:
            # started by an earlier server process: its outcome is in the run manifest, not knowable here
            rec["state"] = "UNKNOWN (started before this server; see the run table)"
        rec["log_tail"] = _tail(_launch_log(root, rec.get("launch_id")))
        rec["sequence"] = _sequence(rec["log_tail"])
        out.append(rec)
    return out
