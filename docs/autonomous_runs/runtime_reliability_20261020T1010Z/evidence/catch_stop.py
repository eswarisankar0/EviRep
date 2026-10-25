"""Pause (SIGSTOP) the real stage process of a RUNNING tracked run, so a test can observe a genuinely running stage.
Precise: the runner's pid comes from the run manifest's RUNNING record; only that runner's child is stopped."""
import json, os, signal, subprocess, sys, time
root, stage, out = sys.argv[1], sys.argv[2], sys.argv[3]
end = time.time() + 60
while time.time() < end:
    try:
        la = json.load(open(os.path.join(root, "data/run_manifest.json")))["stages"][stage]["last_attempt"]
    except Exception:
        la = {}
    if la.get("status") == "RUNNING" and la.get("pid"):
        kids = subprocess.run(["pgrep", "-P", str(la["pid"])], capture_output=True, text=True).stdout.split()
        if kids:
            for k in kids:
                os.kill(int(k), signal.SIGSTOP)
            open(out, "w").write(" ".join(kids))
            sys.exit(0)
    time.sleep(0.01)
sys.exit(1)
