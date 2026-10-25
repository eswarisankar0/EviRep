"""
Non-destructive backup, verification and retention reporting for the git-ignored data/ directory (TD-044).

    ./venv/bin/python scripts/backup_data.py --dry-run                 # what would be archived; writes nothing
    ./venv/bin/python scripts/backup_data.py --dest ~/EviRep_backups   # archive + sha256 manifest, then verify
    ./venv/bin/python scripts/backup_data.py --verify ARCHIVE.tar.gz   # re-check an archive against its manifest
    ./venv/bin/python scripts/backup_data.py --retention-report        # sizes by category; deletes nothing

Rules
  * Never deletes or modifies anything under data/ and never prunes old backups (retention is a report and a
    proposal; any deletion is an owner decision).
  * The destination must be outside the repository (a backup inside the tree it protects is not a backup).
  * The archive is written to a temporary name and renamed only after it is complete; it is then re-read and every
    member's sha256 compared with the manifest before the command reports success.
  * Default scope: everything under data/ except data/cache/opentargets_20.11/ (161 MB of public Open Targets FTP
    files, re-downloadable from the URLs in scripts/vps_molecular_historical.py). --full includes it.
"""
import argparse
import hashlib
import json
import os
import sys
import tarfile
import time
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_CACHES = ("data/cache/opentargets_20.11",)
MANIFEST_SUFFIX = ".sha256.json"


def _sha256(fh):
    h = hashlib.sha256()
    for chunk in iter(lambda: fh.read(1 << 20), b""):
        h.update(chunk)
    return h.hexdigest()


def collect(root, full=False):
    """Sorted [(relpath, size)] of regular files under data/ in scope (symlinks are not followed)."""
    out = []
    skip = () if full else PUBLIC_CACHES
    base = os.path.join(root, "data")
    for d, dirs, files in os.walk(base):
        rel_d = os.path.relpath(d, root)
        dirs[:] = sorted(x for x in dirs if os.path.join(rel_d, x) not in skip)
        for f in sorted(files):
            p = os.path.join(d, f)
            if os.path.isfile(p) and not os.path.islink(p) and not f.endswith(".lock"):
                out.append((os.path.relpath(p, root), os.path.getsize(p)))
    return out


def _inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def backup(root, dest, full=False, now=None):
    if _inside(dest, root):
        raise ValueError(f"destination {dest} is inside the repository; choose a path outside it")
    files = collect(root, full)
    if not files:
        raise ValueError("nothing to back up (no files under data/)")
    os.makedirs(dest, exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    final = os.path.join(dest, f"evirep_data_{stamp}{'_full' if full else ''}.tar.gz")
    if os.path.exists(final):
        raise ValueError(f"{final} already exists; refusing to overwrite a backup")
    tmp = final + ".partial"
    members = {}
    with tarfile.open(tmp, "w:gz") as tar:
        for rel, _ in files:
            p = os.path.join(root, rel)
            with open(p, "rb") as fh:
                members[rel] = {"sha256": _sha256(fh), "bytes": os.path.getsize(p)}
            tar.add(p, arcname=rel, recursive=False)
    with open(tmp, "rb") as fh:
        archive_sha = _sha256(fh)
        os.fsync(fh.fileno())
    os.replace(tmp, final)
    manifest = {"archive": os.path.basename(final), "archive_sha256": archive_sha, "created_utc": stamp,
                "scope": "full" if full else f"data/ excluding {', '.join(PUBLIC_CACHES)}",
                "n_files": len(members), "bytes": sum(m["bytes"] for m in members.values()), "files": members}
    with open(final + MANIFEST_SUFFIX + ".partial", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True)
    os.replace(final + MANIFEST_SUFFIX + ".partial", final + MANIFEST_SUFFIX)
    ok, problems = verify(final)
    return final, manifest, ok, problems


def verify(archive):
    """(ok, problems): archive sha256 and every member's sha256 against the manifest written beside it."""
    mpath = archive + MANIFEST_SUFFIX
    if not os.path.exists(mpath):
        return False, [f"manifest missing: {mpath}"]
    with open(mpath, encoding="utf-8") as fh:
        man = json.load(fh)
    problems = []
    with open(archive, "rb") as fh:
        if _sha256(fh) != man["archive_sha256"]:
            problems.append("archive sha256 differs from the manifest")
    seen = set()
    try:
        with tarfile.open(archive, "r:gz") as tar:
            for m in tar:
                if not m.isfile():
                    continue
                exp = man["files"].get(m.name)
                if exp is None:
                    problems.append(f"unexpected member {m.name}")
                    continue
                with tar.extractfile(m) as fh:
                    if _sha256(fh) != exp["sha256"]:
                        problems.append(f"content differs: {m.name}")
                seen.add(m.name)
    except (tarfile.TarError, OSError, EOFError) as exc:
        problems.append(f"archive unreadable ({type(exc).__name__})")
    missing = sorted(set(man["files"]) - seen)
    if missing:
        problems.append(f"{len(missing)} member(s) missing, e.g. {missing[:3]}")
    return not problems, problems


def retention_report(root):
    """Read-only sizes by category and a proposal. Deletes nothing."""
    def size(rel):
        p = os.path.join(root, rel)
        if os.path.isfile(p):
            return os.path.getsize(p)
        return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(p) for f in fs
                   if not os.path.islink(os.path.join(d, f)))
    cache = os.path.join(root, "data", "cache")
    caches = {e: size(os.path.join("data", "cache", e)) for e in sorted(os.listdir(cache))} if os.path.isdir(cache) else {}
    runs_dir = os.path.join(root, "data", "_runs")
    runs = []
    if os.path.isdir(runs_dir):
        for e in sorted(os.listdir(runs_dir)):
            p = os.path.join(runs_dir, e)
            if os.path.isdir(p):
                runs.append({"run": e, "bytes": size(os.path.join("data", "_runs", e)),
                             "age_days": round((time.time() - os.path.getmtime(p)) / 86400, 1)})
    return {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_bytes": size("data"), "cache_bytes_by_entry": caches, "runs": runs,
            "runs_bytes": sum(r["bytes"] for r in runs),
            "proposal (owner decision; nothing is deleted by this tool)": [
                "keep every run referenced by data/run_manifest.json (last_success / last_attempt of any stage)",
                "keep all analysis directories under data/_runs that reports cite (named *_2026*)",
                "unreferenced tracked run directories older than 90 days: archive with this tool, then the owner may "
                "remove them",
                "data/cache/opentargets_20.11 is re-downloadable (public FTP); the PubMed/DailyMed/openFDA/CT.gov caches "
                "are needed for offline reproduction and data/cache/ctgov_precutoff_trials.json is protected: keep",
                "backups: run this tool after every tracked publication of stage 06 and keep at least the last 3"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Back up, verify and report retention for data/ (non-destructive)")
    ap.add_argument("--root", default=REPO)
    ap.add_argument("--dest", default=os.path.expanduser("~/EviRep_backups"))
    ap.add_argument("--full", action="store_true", help="also include re-downloadable public caches")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--verify", metavar="ARCHIVE")
    g.add_argument("--retention-report", action="store_true")
    a = ap.parse_args(argv)
    if a.verify:
        ok, problems = verify(a.verify)
        print(json.dumps({"archive": a.verify, "ok": ok, "problems": problems}, indent=1))
        return 0 if ok else 2
    if a.retention_report:
        print(json.dumps(retention_report(a.root), indent=1))
        return 0
    if a.dry_run:
        files = collect(a.root, a.full)
        print(json.dumps({"n_files": len(files), "bytes": sum(s for _, s in files), "dest": a.dest,
                          "excluded": [] if a.full else list(PUBLIC_CACHES)}, indent=1))
        return 0
    try:
        final, man, ok, problems = backup(a.root, a.dest, a.full)
    except ValueError as exc:
        print(f"backup refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"archive": final, "n_files": man["n_files"], "bytes": man["bytes"], "verified": ok,
                      "problems": problems}, indent=1))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
