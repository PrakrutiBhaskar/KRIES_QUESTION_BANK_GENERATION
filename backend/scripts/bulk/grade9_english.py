"""Generate English questions for Grade 9 (default 100; add --per-subject N).

Run from backend/:   python scripts/bulk/grade9_english.py --token <JWT>
Extra flags pass straight through (--seed 2, --verify, --dry-run, --email/--password, ...).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bulk_generate  # noqa: E402

bulk_generate.main(["--grade", "9", "--subjects", "English", *sys.argv[1:]])
