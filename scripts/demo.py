#!/usr/bin/env python3
"""Run the hermetic Unwind demo (thin wrapper around ``unwind.demo``).

Used by ``make demo`` and by the VHS tape that records ``docs/assets/demo.gif``.
Kept dependency-free beyond the installed package so it records cleanly.
"""

from __future__ import annotations

from unwind.demo import main

if __name__ == "__main__":
    main()
