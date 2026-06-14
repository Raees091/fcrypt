"""Allow running the package with ``python -m fcrypt``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
