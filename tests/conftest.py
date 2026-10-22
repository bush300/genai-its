# shared pytest setup - puts every module directory on sys.path once so
# individual test files don't have to repeat the same path hacks. Needed
# because directory names like "1.5_security" aren't valid Python package
# names, so nothing here can be imported as a normal dotted package.

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MODULE_DIRS = [
    PROJECT_ROOT,
    PROJECT_ROOT / "1.2_back_end",
    PROJECT_ROOT / "1.3_models",
    PROJECT_ROOT / "1.4_agent2_quiz",
    PROJECT_ROOT / "1.5_security",
]

for module_dir in MODULE_DIRS:
    path = str(module_dir)
    if path not in sys.path:
        sys.path.insert(0, path)
