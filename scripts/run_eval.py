#!/usr/bin/env python3
"""Convenience wrapper for benchmark/evaluate.py — same interface, root-level shortcut."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.evaluate import main

if __name__ == "__main__":
    main()
