"""Build the installed desktop app without bundling live task data."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_app_icon.py")], check=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm",
                    "--distpath", str(ROOT / "desktop"), "--workpath", str(ROOT / ".desktop-build"),
                    str(ROOT / "desktop_app.spec")], cwd=ROOT, check=True)
    installation = ROOT / "desktop" / "哲店长工作台"
    (installation / "project-location.json").write_text(
        json.dumps(dict(project_root=str(ROOT)), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Built: {installation / '哲店长工作台.exe'}")


if __name__ == "__main__":
    main()
