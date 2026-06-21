import os
import subprocess

REPO = r"C:\Users\RJLoc\OneDrive\Desktop\dice-reaction\dice-reactions"
BACKEND = os.path.join(REPO, "backend")


def run(cmd):
    return subprocess.check_output(cmd, cwd=REPO, text=True)


print("=== git status ===")
print(run(["git", "status", "--short"]))
print("=== git diff --check ===")
try:
    print(run(["git", "diff", "--check"]))
except subprocess.CalledProcessError as e:
    print(e.output)
print("=== git diff --stat 4dadb3f..HEAD ===")
print(run(["git", "diff", "--stat", "4dadb3f..HEAD"]))
print("=== server.py prompt diff ===")
print(run(["git", "diff", "4dadb3f..HEAD", "--", "backend/server.py"]) or "(no changes)")
print("=== commits ===")
print(run(["git", "log", "--oneline", "4dadb3f..HEAD"]))
print("=== files per commit ===")
for line in run(["git", "log", "--oneline", "4dadb3f..HEAD"]).strip().splitlines():
    sha = line.split()[0]
    print(line)
    print(run(["git", "show", "--name-only", "--format=", sha]).strip())