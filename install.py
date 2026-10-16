#!/usr/bin/env python3
"""Entry point for the downloaded, self-contained release."""
from pathlib import Path
import sys

PACKAGE = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE / 'app'))
from setup_wizard import main

if __name__ == '__main__':
    raise SystemExit(main(PACKAGE))
