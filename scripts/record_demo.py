#!/usr/bin/env python3
"""Render the Unwind demo to a self-contained SVG for the README.

Uses ``rich``'s console recorder — no external tooling (vhs/ttyd/ffmpeg) needed,
and SVG is sharp on Retina and tiny. Regenerate with:  make demo-svg
(For an animated GIF instead, install VHS and run ``vhs docs/assets/demo.tape``.)
"""

from __future__ import annotations

import anyio
from rich.console import Console

import unwind.demo as demo


def main() -> None:
    rec = Console(record=True, width=100)
    demo.console = rec  # redirect the demo's output into the recorder
    anyio.run(demo.run_demo)
    out = "docs/assets/demo.svg"
    rec.save_svg(out, title="unwind demo")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
