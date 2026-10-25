"""scripts/backup_data.py: non-destructive backup, integrity verification, refusal rules (TD-044)."""
import hashlib
import importlib.util
import json
import os
import shutil
import tarfile
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("bk", os.path.join(ROOT, "scripts", "backup_data.py"))
bk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bk)


def tree_hash(root):
    h = hashlib.sha256()
    for d, dirs, files in sorted(os.walk(root)):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


class TestBackup(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="evirep_bk_root_")
        self.dest = tempfile.mkdtemp(prefix="evirep_bk_dest_")
        for rel, body in (("data/vps_scores_v2.csv", "a,b\n1,2\n"), ("data/run_manifest.json", "{}"),
                          ("data/_runs/r1/log.txt", "log\n"), ("data/cache/pubmed_lit/x.json", "{}"),
                          ("data/cache/opentargets_20.11/big.jsonl", "x" * 1000), ("data/.run_manifest.lock", "")):
            p = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as fh:
                fh.write(body)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.dest, ignore_errors=True)

    def test_backup_verifies_and_never_touches_source(self):
        before = tree_hash(self.root)
        final, man, ok, problems = bk.backup(self.root, self.dest)
        self.assertTrue(ok, problems)
        self.assertEqual(tree_hash(self.root), before)
        self.assertEqual(set(man["files"]), {"data/vps_scores_v2.csv", "data/run_manifest.json", "data/_runs/r1/log.txt",
                                             "data/cache/pubmed_lit/x.json"})    # public cache and lock excluded
        self.assertFalse([f for f in os.listdir(self.dest) if f.endswith(".partial")])
        self.assertTrue(bk.verify(final)[0])

    def test_full_includes_public_cache(self):
        _, man, ok, _ = bk.backup(self.root, self.dest, full=True)
        self.assertTrue(ok)
        self.assertIn("data/cache/opentargets_20.11/big.jsonl", man["files"])

    def test_tampered_archive_fails_verification(self):
        final, man, _, _ = bk.backup(self.root, self.dest)
        with open(final + bk.MANIFEST_SUFFIX) as fh:
            m = json.load(fh)
        m["files"]["data/vps_scores_v2.csv"]["sha256"] = "0" * 64
        with open(final + bk.MANIFEST_SUFFIX, "w") as fh:
            json.dump(m, fh)
        ok, problems = bk.verify(final)
        self.assertFalse(ok)
        self.assertIn("content differs: data/vps_scores_v2.csv", problems)
        with open(final, "r+b") as fh:                                   # truncate the archive itself
            fh.truncate(20)
        self.assertFalse(bk.verify(final)[0])

    def test_refuses_destination_inside_repository_and_overwrite(self):
        with self.assertRaises(ValueError):
            bk.backup(self.root, os.path.join(self.root, "backups"))
        from datetime import datetime, timezone
        t = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bk.backup(self.root, self.dest, now=t)
        with self.assertRaises(ValueError):
            bk.backup(self.root, self.dest, now=t)

    def test_dry_run_and_retention_report_write_nothing(self):
        before, dest_before = tree_hash(self.root), os.listdir(self.dest)
        self.assertEqual(bk.main(["--root", self.root, "--dest", self.dest, "--dry-run"]), 0)
        rep = bk.retention_report(self.root)
        self.assertEqual(tree_hash(self.root), before)
        self.assertEqual(os.listdir(self.dest), dest_before)
        self.assertEqual([r["run"] for r in rep["runs"]], ["r1"])
        self.assertIn("opentargets_20.11", rep["cache_bytes_by_entry"])

    def test_archive_members_are_relative_paths(self):
        final, _, _, _ = bk.backup(self.root, self.dest)
        with tarfile.open(final) as tar:
            self.assertTrue(all(n.startswith("data/") and ".." not in n for n in tar.getnames()))


if __name__ == "__main__":
    unittest.main()
