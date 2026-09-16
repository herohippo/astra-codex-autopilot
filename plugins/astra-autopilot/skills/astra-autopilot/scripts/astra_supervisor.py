#!/usr/bin/env python3
"""Self-contained plugin wrapper for the bundled Astra Autopilot Python package."""
from pathlib import Path
import sys

plugin_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(plugin_root / "python"))
from astra_supervisor.cli import main  # noqa: E402

raise SystemExit(main())
