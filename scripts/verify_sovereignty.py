"""Prove the appliance cannot phone home. Run it INSIDE the box.

    docker compose exec mandate python scripts/verify_sovereignty.py

Exits non-zero if anything got out, so it can gate a deployment:
a sovereignty claim that is not enforced by CI is a sovereignty claim
that will quietly stop being true.
"""

import sys
from pathlib import Path

sys.path.insert(0, "core")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from sovereignty import audit, render  # noqa: E402

if __name__ == "__main__":
    report = audit()
    print(render(report))
    if not report.sovereign:
        print("FAILING: this appliance is not sovereign. The findings "
              "above name every way out.\n")
        sys.exit(1)
    print("This box tried to leave and could not.\n")
