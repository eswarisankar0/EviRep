#!/bin/bash
# Re-run browser suites on fresh isolated copies. usage: run_suites.sh drive16:uxcopy drive15:livecopy ... [timeout13]
SP=/private/tmp/claude-501/-Users-thrisha-Drup-Rep-PF-EviRep/e6733d36-fdb7-40b2-a548-915362746462/scratchpad
cd /Users/thrisha/Drup_Rep_PF/EviRep
closetabs() { curl -s http://127.0.0.1:9333/json/list | python3 -c "
import json,sys,urllib.request
for t in json.load(sys.stdin):
    if t['type']=='page': urllib.request.urlopen('http://127.0.0.1:9333/json/close/'+t['id'])"; }
fresh() { pkill -f "ui/server.py --"; sleep 0.5; rm -rf "${SP:?}/${1:?}" && rsync -a --exclude venv --exclude .git --exclude __pycache__ --exclude 'data/_runs' --exclude 'data/cache/opentargets_20.11' ./ "$SP/$1/" && mkdir -p "$SP/$1/data/_runs"; (nohup ./venv/bin/python ui/server.py --root "$SP/$1" --port 8799 > $SP/server8799.log 2>&1 &); until curl -s -o /dev/null http://127.0.0.1:8799/api/status; do sleep 1; done; }
for spec in "$@"; do
  if [ "$spec" = "timeout13" ]; then
    pkill -f "ui/server.py --"; G=$SP/gatecopy4; rm -rf "${G:?}" && rsync -a --exclude venv --exclude .git --exclude __pycache__ --exclude 'data/_runs' --exclude 'data/cache/opentargets_20.11' ./ "$G/" && mkdir -p "$G/data/_runs" && python3 - "$G" <<'PY'
import sys
G=sys.argv[1]
p=f"{G}/scripts/completeness_gap_agent.py"; s=open(p).read()
o='''    args = ap.parse_args(argv)
'''
n='''    args = ap.parse_args(argv)
    if os.path.exists(os.path.join(args.root, "HANG_FOR_TIMEOUT_TEST")):     # ISOLATED TEST COPY ONLY
        print("test hang: writing a partial output, then sleeping", flush=True)
        open(os.path.join(args.root, OUT), "w").write("{partial")
        import time
        time.sleep(600)
'''
assert s.count(o)==1; open(p,"w").write(s.replace(o,n,1))
p=f"{G}/ui/server.py"; s=open(p).read(); i=s.index('"id": "10h"'); j=s.index('"timeout_s": 900', i)
open(p,"w").write(s[:j]+'"timeout_s": 20'+s[j+len('"timeout_s": 900'):])
PY
    (cd $G && nohup /Users/thrisha/Drup_Rep_PF/EviRep/venv/bin/python ui/server.py --port 8799 > $SP/server_gate.log 2>&1 &); until curl -s -o /dev/null http://127.0.0.1:8799/api/live; do sleep 1; done
    (cd $SP/cdp && python3 drive13.py > $SP/drive13.out 2>&1); d=drive13
  else
    d=${spec%%:*}; c=${spec##*:}; closetabs; fresh $c; (cd $SP/cdp && python3 $d.py > $SP/$d.out 2>&1)
  fi
  echo "$d: $(grep SUMMARY $SP/$d.out || echo 'NO SUMMARY (crashed)') $(grep -c '^FAIL' $SP/$d.out) fail(s)"; grep "^FAIL" $SP/$d.out | cut -c1-330; grep -A3 Traceback $SP/$d.out | tail -2
done
closetabs; pkill -f "ui/server.py --"; echo "leftover runners: $(pgrep -f 'run_stage.py' | wc -l)"
