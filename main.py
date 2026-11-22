"""Root entry point for the bundled Formix runtime."""
from pathlib import Path
import sys

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root / "src" if (root / "src/formix").is_dir() else root))
    from formix.launcher import main
    raise SystemExit(main())
