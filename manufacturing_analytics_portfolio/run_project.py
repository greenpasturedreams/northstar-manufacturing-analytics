"""Run from any working directory: python run_project.py"""
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
for script in ['generate_data.py','build_database.py','eda.py','write_readme.py']:
    subprocess.run([sys.executable,str(ROOT/'src'/script)],check=True,cwd=ROOT)
