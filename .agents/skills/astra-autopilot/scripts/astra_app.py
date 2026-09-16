#!/usr/bin/env python3
from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(repo_root / "plugins" / "astra-autopilot" / "python"))
from astra_supervisor.app_control import main

raise SystemExit(main())
