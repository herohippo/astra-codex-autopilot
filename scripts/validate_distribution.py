"""Validate manifests and portable entrypoints without invoking a model."""
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
plugin = root / "plugins" / "astra-autopilot"
manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8-sig"))
market = json.loads((root / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8-sig"))
assert manifest["name"] == plugin.name
assert market["plugins"][0]["name"] == manifest["name"]
assert (root / market["plugins"][0]["source"]["path"]).resolve() == plugin.resolve()
assert (root / "LICENSE").is_file()
for folder in (plugin / "skills" / "astra-autopilot", root / ".agents" / "skills" / "astra-autopilot"):
    skill = (folder / "SKILL.md").read_text(encoding="utf-8-sig")
    assert skill.startswith("---\nname: astra-autopilot\n")
    assert (folder / "references" / "native-app.md").is_file()
    for script in ("astra_supervisor.py", "astra_app.py"):
        subprocess.run([sys.executable, str(folder / "scripts" / script), "--help"],
                       cwd=root, stdout=subprocess.DEVNULL, check=True, timeout=15)
print("Manifests, skill references, license, and four portable entrypoints validated.")
