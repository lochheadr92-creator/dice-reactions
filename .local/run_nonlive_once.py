import os
import subprocess
import sys

backend = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend")
os.chdir(backend)
raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "tests", "-m", "not live", "-q"]))