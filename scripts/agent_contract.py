"""
Shared contract for the specialised evidence agents (architecture 10a-10h).

Every agent output (or, for agents whose output predates this module, an
adapter over it) must provide the ENVELOPE fields below. The dashboard and
Stage 11 read only these fields to decide status, staleness and coverage, so a
new agent integrates by filling the envelope rather than by UI special cases.

    agent_id        "10a" ... "10h"
    agent           human-readable name
    agent_version   string
    schema_version  string
    run_status      one of RUN_STATUSES (see meaning below)
    generated_utc   ISO-8601 UTC time the output was written
    inputs          {relative path: md5} of every persisted input read
    coverage        {...} what was covered (counts), agent-specific keys
    limitations     [str]
    diagnostics     [{"level": "info"|"warn"|"error", "code": str, "message": str}]
                    -- never a secret, never an absolute path

Run status meaning (per output, not per compound):
    SUCCESS      every requested unit was processed
    PARTIAL      some units could not be processed (diagnostics say which)
    NO_EVIDENCE  ran correctly; no unit had evidence to assess
    FAILED       the run could not complete (output kept only as a record)
STALE is never written by an agent: it is derived at read time when an
input's md5 no longer matches (see stale_inputs).

Standard library only; importable from scripts/ and from ui/.
"""

import hashlib
import os
import re
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, TypedDict

RUN_STATUSES = ("SUCCESS", "PARTIAL", "NO_EVIDENCE", "FAILED")
DIAG_LEVELS = ("info", "warn", "error")
ENVELOPE_KEYS = ("agent_id", "agent", "agent_version", "schema_version", "run_status", "generated_utc",
                 "inputs", "coverage", "limitations", "diagnostics")
_SECRETISH = re.compile(r"(api[_-]?key|token|secret|password)\s*[=:]\s*\S+", re.I)


class Diagnostic(TypedDict):
    level: str
    code: str
    message: str


def md5(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def input_hashes(root: str, rels: Iterable[str]) -> Dict[str, Optional[str]]:
    """md5 of each declared input (relative path keys). An input absent at run time is recorded as None - nothing is
    invented, but its later appearance is detectable (E-055 A-7: absent inputs used to be left out, so a file that
    appeared after the run never made the output stale)."""
    return {rel: (md5(os.path.join(root, rel)) if os.path.exists(os.path.join(root, rel)) else None) for rel in rels}


def input_changed(root: str, rel: str, recorded: Optional[str]) -> bool:
    """One rule for every staleness check: a recorded md5 is stale if the file is missing or differs; a recorded
    None (absent at run time) is stale only once the file exists."""
    p = os.path.join(root, rel)
    if recorded is None:
        return os.path.exists(p)
    try:
        return md5(p) != recorded
    except OSError:
        return True


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def diag(level: str, code: str, message: str) -> Diagnostic:
    if level not in DIAG_LEVELS:
        raise ValueError(f"bad diagnostic level {level!r}")
    message = _SECRETISH.sub(r"\1=<redacted>", str(message))
    message = re.sub(r"/Users/[^/\s]+", "/Users/<user>", message)
    return {"level": level, "code": code, "message": message[:500]}


def run_status(n_units: int, n_failed: int, n_with_evidence: int) -> str:
    """Status from unit counts: failures win over emptiness; an empty request is FAILED, not success."""
    if n_units <= 0:
        return "FAILED"
    if n_failed >= n_units:
        return "FAILED"
    if n_failed:
        return "PARTIAL"
    if n_with_evidence == 0:
        return "NO_EVIDENCE"
    return "SUCCESS"


def envelope(agent_id: str, agent: str, agent_version: str, schema_version: str, status: str,
             inputs: Dict[str, str], coverage: Dict, limitations: List[str],
             diagnostics: Optional[List[Diagnostic]] = None) -> Dict:
    diagnostics = list(diagnostics or [])
    if status == "FAILED" and not any(d.get("level") == "error" for d in diagnostics) \
            and any(d.get("level") == "warn" for d in diagnostics):
        # Every unit failed and each failure was reported as a warning: record the run-level error
        # instead of refusing the envelope, which would leave the previous output looking current.
        diagnostics.append(diag("error", "RUN_FAILED", "no unit succeeded; see the warnings above"))
    out = {"agent_id": agent_id, "agent": agent, "agent_version": agent_version,
           "schema_version": schema_version, "run_status": status, "generated_utc": now_utc(),
           "inputs": dict(inputs), "coverage": dict(coverage), "limitations": list(limitations),
           "diagnostics": list(diagnostics or [])}
    validate_envelope(out)
    return out


def validate_envelope(out: Dict) -> bool:
    missing = [k for k in ENVELOPE_KEYS if k not in out]
    if missing:
        raise ValueError(f"envelope missing {missing}")
    if out["run_status"] not in RUN_STATUSES:
        raise ValueError(f"bad run_status {out['run_status']!r}")
    if not re.fullmatch(r"10[a-h]", str(out["agent_id"])):
        raise ValueError(f"bad agent_id {out['agent_id']!r}")
    if not isinstance(out["inputs"], dict) or any(os.path.isabs(k) for k in out["inputs"]):
        raise ValueError("inputs must map relative paths to md5")
    for d in out["diagnostics"]:
        if d.get("level") not in DIAG_LEVELS or not d.get("code"):
            raise ValueError(f"bad diagnostic {d!r}")
        if _SECRETISH.search(d.get("message", "")):
            raise ValueError("diagnostic message looks like it carries a secret")
    if out["run_status"] == "PARTIAL" and not any(d["level"] in ("warn", "error") for d in out["diagnostics"]):
        raise ValueError("PARTIAL must say why (a warn/error diagnostic)")
    if out["run_status"] == "FAILED" and not any(d["level"] == "error" for d in out["diagnostics"]):
        raise ValueError("FAILED must carry an error diagnostic")
    return True


def stale_inputs(root: str, inputs: Dict[str, str]) -> List[str]:
    """Inputs whose current md5 differs from the recorded one (or that disappeared)."""
    return [rel for rel, h in (inputs or {}).items() if input_changed(root, rel, h)]
