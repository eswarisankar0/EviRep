"""
STEP 5h: the FDA label as it stood at the cutoff (TD-022 / TD-033). New files only; stage 05 and VPS unchanged.

Stage 05 scores the CURRENT openFDA label (78 of 83 took effect after 2020), so the safety dimension is not
cutoff-bounded. For every compound whose current label stage 05 cached, this stage asks DailyMed for the version
history of that label's set ID, takes the latest version published on or before the cutoff, downloads that
versioned SPL and applies stage 05's exact scoring (boxed warning present; occurrences of stage 05's serious
terms in the boxed-warning / warnings / warnings-and-precautions sections, LOINC 34066-1 / 34071-1 / 43685-7).

Parser check: the CURRENT version of each set ID is scored the same way and compared with stage 05's published
values (`current_version_agrees_with_stage05`), so a disagreement in the historical score is not a parsing artefact.

States per compound (never collapsed):
  PRE_CUTOFF_VERSION_SCORED   a version published <= cutoff was scored
  NO_PRE_CUTOFF_VERSION       this set ID's first version is after the cutoff. The drug may have had a label under
                              another set ID: unknown, NOT "no label" and NOT zero risk
  NO_CURRENT_LABEL            stage 05 found no openFDA label (unchanged missing state)
  RETRIEVAL_FAILED            DailyMed did not answer usably (the stage exits 1)

Outputs: data/safety_label_history.csv, data/safety_label_history_run.json; cache data/cache/dailymed/.
    ./venv/bin/python scripts/05h_safety_label_history.py [--offline]
"""
import argparse
import importlib.util
import io
import json
import os
import re
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pandas as pd

CUTOFF = "2020-12-31"
DM = "https://dailymed.nlm.nih.gov/dailymed"
CACHE_DIR = "data/cache/dailymed"
LABEL_CACHE = "data/cache/openfda_labels"
SAFETY = "data/safety_signal.csv"
OUT = "data/safety_label_history.csv"
RUN_OUT = "data/safety_label_history_run.json"
SECTION_CODES = {"34066-1": "boxed_warning", "34071-1": "warnings", "43685-7": "warnings_and_cautions"}
NS = "{urn:hl7-org:v3}"
_s05 = importlib.util.spec_from_file_location(
    "s05", os.path.join(os.path.dirname(os.path.abspath(__file__)), "05_safety_signal.py"))


class RetrievalError(Exception):
    pass


def serious_terms():
    """Stage 05's term list, read from its source (importing it would run nothing, but it needs requests)."""
    with open(_s05.origin, encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r"SERIOUS_TERMS = \[(.*?)\]", src, re.S)
    return re.findall(r'"([^"]+)"', m.group(1))


def _get(session, url, params=None, retries=3, sleep=None):
    sleep = sleep or time.sleep
    last = None
    for attempt in range(retries + 1):
        try:
            r = session.get(url, params=params, timeout=60)
        except Exception as exc:
            last = type(exc).__name__
        else:
            if r.status_code == 200:
                sleep(0.25)
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        if attempt < retries:
            sleep(2 * 2 ** attempt)
    raise RetrievalError(f"{url.split('/')[-1][:60]}: {last}")


def parse_history(payload):
    """[(version, 'YYYY-MM-DD')] from DailyMed history.json; malformed -> RetrievalError."""
    try:
        rows = payload["data"]["history"]
        out = [(int(h["spl_version"]), datetime.strptime(h["published_date"], "%b %d, %Y").strftime("%Y-%m-%d"))
               for h in rows]
    except (KeyError, TypeError, ValueError) as exc:
        raise RetrievalError(f"history: unexpected schema ({type(exc).__name__})")
    if not out:
        raise RetrievalError("history: empty")
    return sorted(out)


def version_at(history, cutoff=CUTOFF):
    pre = [h for h in history if h[1] <= cutoff]
    return pre[-1] if pre else None


def spl_sections(xml_bytes):
    """{field: text} for the outermost boxed-warning / warnings / warnings-and-precautions sections."""
    root = ET.fromstring(xml_bytes)
    found = {}

    def walk(el, inside):
        for child in el:
            if child.tag == f"{NS}section":
                code = child.find(f"{NS}code")
                field = SECTION_CODES.get(code.get("code") if code is not None else None)
                if field and not inside:
                    found.setdefault(field, []).append(" ".join(t.strip() for t in child.itertext() if t.strip()))
                    walk(child, True)
                    continue
            walk(child, inside)
    walk(root, False)
    return {k: " ".join(v) for k, v in found.items()}


def score(sections, terms):
    text = " ".join(sections.get(f, "") for f in ("boxed_warning", "warnings", "warnings_and_cautions")).lower()
    return {"boxed_warning": "boxed_warning" in sections, "serious_term_count": sum(text.count(t) for t in terms),
            "warning_fields": "|".join(f for f in ("boxed_warning", "warnings", "warnings_and_cautions") if f in sections)}


def _cache(root, *parts):
    p = os.path.join(root, CACHE_DIR, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def history(session, root, setid, offline):
    p = _cache(root, "history", f"{setid}.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            return parse_history(json.load(fh))
    if offline:
        raise RetrievalError("offline and history not cached")
    r = _get(session, f"{DM}/services/v2/spls/{setid}/history.json")
    try:
        payload = r.json()
    except ValueError:
        raise RetrievalError("history: not JSON")
    h = parse_history(payload)
    with open(p + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(p + ".tmp", p)
    return h


def spl_xml(session, root, setid, version, offline):
    p = _cache(root, "spl", f"{setid}_v{version}.zip")
    data = None
    if os.path.exists(p):
        with open(p, "rb") as fh:
            data = fh.read()
    elif offline:
        raise RetrievalError(f"offline and SPL v{version} not cached")
    else:
        data = _get(session, f"{DM}/getFile.cfm", {"type": "zip", "setid": setid, "version": version}).content
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        xmls = [n for n in z.namelist() if n.lower().endswith(".xml")]
        if len(xmls) != 1:
            raise RetrievalError(f"SPL v{version}: {len(xmls)} XML files in the archive")
        xml = z.read(xmls[0])
        ET.fromstring(xml)
    except (zipfile.BadZipFile, ET.ParseError) as exc:
        raise RetrievalError(f"SPL v{version}: unreadable ({type(exc).__name__})")
    if not os.path.exists(p):
        with open(p + ".tmp", "wb") as fh:
            fh.write(data)
        os.replace(p + ".tmp", p)
    return xml


def _num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def main(argv=None, session=None, root="."):
    ap = argparse.ArgumentParser(description="FDA label version in effect at the cutoff (DailyMed history)")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    j = lambda p: os.path.join(root, p)
    if session is None and not a.offline:
        import requests
        session = requests.Session()
    terms = serious_terms()
    saf = pd.read_csv(j(SAFETY), keep_default_na=False)
    rows, failures = [], []
    for r in saf.itertuples():
        name = r.compound_name
        row = {"compound_name": name, "stage05_has_label": r.has_label, "stage05_boxed_warning": r.boxed_warning,
               "stage05_serious_term_count": r.serious_term_count}
        if str(r.has_label) != "True":
            rows.append({**row, "state": "NO_CURRENT_LABEL"})
            continue
        safe = "".join(ch if ch.isalnum() else "_" for ch in name)      # stage 05's cache_label naming
        lp = j(os.path.join(LABEL_CACHE, f"{safe}.json"))
        setid = None
        if os.path.exists(lp):
            with open(lp, encoding="utf-8") as fh:
                setid = json.load(fh).get("set_id")
        if not setid:
            rows.append({**row, "state": "RETRIEVAL_FAILED", "detail": "no cached openFDA label with a set_id"})
            failures.append(name)
            continue
        try:
            h = history(session, root, setid, a.offline)
            cur_v, cur_d = h[-1]
            cur = score(spl_sections(spl_xml(session, root, setid, cur_v, a.offline)), terms)
            agrees = (cur["boxed_warning"] == (str(r.boxed_warning) == "True")
                      and cur["serious_term_count"] == _num(r.serious_term_count))
            row.update(set_id=setid, n_versions=len(h), first_version_date=h[0][1], current_version=cur_v,
                       current_version_date=cur_d, current_boxed_warning=cur["boxed_warning"],
                       current_serious_term_count=cur["serious_term_count"],
                       current_version_agrees_with_stage05=agrees)
            v = version_at(h)
            if v is None:
                rows.append({**row, "state": "NO_PRE_CUTOFF_VERSION",
                             "detail": f"set ID first published {h[0][1]}; an earlier label under another set ID is "
                                       "not ruled out"})
                continue
            pre = score(spl_sections(spl_xml(session, root, setid, v[0], a.offline)), terms)
            rows.append({**row, "state": "PRE_CUTOFF_VERSION_SCORED", "cutoff_version": v[0], "cutoff_version_date": v[1],
                         "cutoff_boxed_warning": pre["boxed_warning"], "cutoff_serious_term_count": pre["serious_term_count"],
                         "cutoff_warning_fields": pre["warning_fields"]})
        except RetrievalError as exc:
            rows.append({**row, "state": "RETRIEVAL_FAILED", "detail": str(exc)[:200]})
            failures.append(name)
    df = pd.DataFrame(rows)
    if len(failures) == int((saf["has_label"].astype(str) == "True").sum()):
        print(f"FAILED: no label history retrieved ({failures[:3]}...); nothing written", file=sys.stderr)
        return 1
    df.to_csv(j(OUT) + ".tmp", index=False)
    os.replace(j(OUT) + ".tmp", j(OUT))
    scored = df[df["state"] == "PRE_CUTOFF_VERSION_SCORED"]
    cur_ok = df.get("current_version_agrees_with_stage05")
    run = {"stage": "05h", "status": "PARTIAL" if failures else "SUCCESS", "cutoff": CUTOFF,
           "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "states": df["state"].value_counts().to_dict(), "failures": failures,
           "parser_check_current_version_agrees_with_stage05": None if cur_ok is None else
           {"agree": int((cur_ok == True).sum()), "checked": int(cur_ok.notna().sum())},  # noqa: E712
           "serious_terms": terms,
           "limitations": ["only the set ID of the current openFDA label is followed; a drug relabelled under a new "
                           "set ID shows NO_PRE_CUTOFF_VERSION although an older label existed",
                           "DailyMed publication date is used as the version date"]}
    with open(j(RUN_OUT) + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(run, fh, indent=1)
    os.replace(j(RUN_OUT) + ".tmp", j(RUN_OUT))
    print(f"05h: {run['states']}; parser check {run['parser_check_current_version_agrees_with_stage05']}; "
          f"failures {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
