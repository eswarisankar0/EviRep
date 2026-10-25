# Test results (2026-10-20, final code)

| Check | Command | Result | Log |
|---|---|---|---|
| Python unit/integration suite | `./venv/bin/python -m unittest discover -s tests` | **684 tests, OK**: 673 before + 11 new in `tests/test_ui_quality.py` | `logs/tests_after.log` (before: `logs/tests_before.log`, 673 OK) |
| New UI quality tests | `tests/test_ui_quality.py` | 11 / 11 | same |
| Ground-truth contract | `-m unittest tests.test_ground_truth_contract` | OK | — |
| Score verification | `scripts/vps_verify.py` | MATCH, 90 compounds, max abs diff 2.22e-16 | `logs/vps_verify.txt` |
| Run manifest | `scripts/run_stage.py --check-manifest` / `--status` | exit 0 / exit 0 | `logs/check_manifest.txt`, `logs/status_after.txt` |
| Protected artefacts | `shasum -a 256 -c logs/hashes_before.txt` | all OK | `logs/hashes_after_check.txt` |
| Whitespace | `git diff --check` | clean | — |
| JS syntax | `node --check ui/app.js` | OK | — |
| Real-browser acceptance | 8 CDP suites | **112 / 112** | `evidence/`, `BROWSER_ACCEPTANCE.md` |

## The 11 new tests
1. ROC/PR areas reproduce the approved report; endpoints are (0,0) and (1,1); n = 90, 14 positive / 76 negative.
2. Independent Mann-Whitney AUROC equals the served curve area (1e-12).
3. Model comparison, paired difference and missing data are copied verbatim from the report; proximity imputed = 2.
4. A mismatched report withholds the curves.
5. Freshness fields equal the tracker's statuses and times.
6. Sources never invent a retrieval time; PubMed time equals the provenance file.
7. Science counts equal the review artefact; pending candidates keep their exact id.
8. Ranking marks exactly Deferiprone and Trimethobenzamide as imputed.
9. Every agent status code in the pipeline scripts has a readable label.
10. Badges show the label and keep the code in the tooltip.
11. No blanket "All results current" claim.

## Not tested
- Real network stages and long production timeouts (see `BROWSER_ACCEPTANCE.md`).
- Browsers other than headless Chrome; assistive technology.
