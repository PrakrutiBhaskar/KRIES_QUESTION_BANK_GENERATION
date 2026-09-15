"""
Guarantees `generation_engine` is importable during test collection,
independent of how pytest is invoked (bare `pytest`, `python -m pytest`, an
IDE's test runner) or whether the `pythonpath` setting in pytest.ini is
honored on a given machine.

pytest always imports the nearest conftest.py before collecting tests in the
same directory tree, so this runs before tests/test_*.py try to import the
package — that ordering is what makes this reliable across platforms where
ini-based sys.path insertion has, in practice, been inconsistent.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
