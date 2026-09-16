#!/usr/bin/env python3
"""Bundled native-app coordination helper."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
from astra_supervisor.app_control import main

raise SystemExit(main())
