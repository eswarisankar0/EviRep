# Baseline before any change (2026-10-20T10:11:41Z)

- branch: main  HEAD: 576bc7f57cbf08873ca9971da469dce3500defb8  commits: 6
- staged: 25  unstaged: 21  untracked: 188  stashes: 0
- index-diff md5: d04e97371800f54cc28abbb6a383742b  .git/index sha256: 0f381daa047d918c
- recovery: /Users/thrisha/EviRep_recovery_rr_20261020T1010Z (512 entries)
- Protected artefacts: 19/19 sha256 OK (`logs/baseline_hashes.txt`, list from the recovery snapshot)
- Running server: `./venv/bin/python ui/server.py` (pid 77116, started 09:48Z after the last server change); served
  `app.js`, `style.css` and `index.html` are byte-identical to the files on disk (`logs/served_source_check.txt`)
- Test suite: `./venv/bin/python -m unittest discover -s tests` 10:10:24Z-10:11:27Z, exit 0, **660 tests OK**, 0 ResourceWarnings

## Defects reproduced before changes (none covered by the 660 passing tests)
| ID | Reproduction | Expected | Actual |
|---|---|---|---|
| D1 | manifest that is valid JSON but structurally wrong: a stage record that is a string, `last_success` a list, or a history entry that is not an object | every stage UNKNOWN with a reason, as for unparseable JSON | `status()`, `/api/status`, `/api/live` (and `--check-manifest` for one shape) raise `AttributeError`, so the browser gets HTTP 500 |
| D2 | a RUNNING record whose `run_dir` points outside `data/_runs` | ignored | the last line of that directory's `log.txt` is shown in the UI (path traversal) |
| D3 | a launch record whose `log` points outside `data/_runs/_ui_launches` | ignored | that file's tail is shown in the launches panel |
| D4 | a stage whose process hangs | eventually failed with a clear reason, previous outputs restored | `run_stage.py` has no timeout: RUNNING forever while the process lives |
| D5 | the launch directory is not writable | an actionable error | HTTP 500 with only the class name ("launch failed (PermissionError)") |

## Probed and found correct
- 20 concurrent `POST /api/run`: 1 × 202, 19 × 409, one launch record.
- A missing runner script: 202, then the launch shows EXITED with exit 2 and the interpreter's own error (acceptance is never shown as success).
