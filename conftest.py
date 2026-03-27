import importlib
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent / "tests"
sys.path[:] = [entry for entry in sys.path if Path(entry or ".").resolve() != TESTS_DIR]
importlib.import_module("mcp")
