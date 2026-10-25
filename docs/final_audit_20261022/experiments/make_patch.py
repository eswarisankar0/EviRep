"""Write the reviewable patch: work copy vs primary, for every file listed in records/changed_files_vs_primary.txt."""
import difflib
import os
import sys

P, W, LIST, OUT = sys.argv[1:5]
files = []
for line in open(LIST).read().splitlines():
    if line.startswith("Files "):
        files.append(line.split()[1])
    elif line.startswith("Only in "):
        d, name = line[len("Only in "):].split(": ")
        files.append(os.path.join(d.replace(W + "/", "").replace(W, ""), name).lstrip("/"))
out = []
for f in files:
    pa, pb = os.path.join(P, f), os.path.join(W, f)
    a = open(pa).read().splitlines(keepends=True) if os.path.exists(pa) else []
    b = open(pb).read().splitlines(keepends=True)
    for line in difflib.unified_diff(a, b, fromfile=("a/" + f) if a else "/dev/null", tofile="b/" + f):
        out.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")   # git/patch marker
open(OUT, "w").write("".join(out))
print(len(files), "files;", sum(1 for l in out if l.startswith("+") and not l.startswith("+++")), "added /",
      sum(1 for l in out if l.startswith("-") and not l.startswith("---")), "removed lines ->", OUT)
