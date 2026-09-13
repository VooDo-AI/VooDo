"""Build VooDo.exe – run once, produces Desktop\\VooDo.exe."""
import subprocess, sys, os, shutil
from pathlib import Path

# All paths are relative to this script's directory.
SCRIPTS_DIR = Path(__file__).resolve().parent
CLIENT_DIR  = SCRIPTS_DIR.parent
VENV_PIP    = str(CLIENT_DIR / ".venv" / "Scripts" / "pip.exe")
VENV_PY     = str(CLIENT_DIR / ".venv" / "Scripts" / "python.exe")
ICON_PNG    = str(SCRIPTS_DIR / "voodo_icon.png")
ICON_ICO    = str(SCRIPTS_DIR / "voodo.ico")
LAUNCHER    = str(SCRIPTS_DIR / "voodo_launcher.py")
DESKTOP     = str(Path.home() / "Desktop")
BUILD_DIR   = str(SCRIPTS_DIR)

# 1. Convert PNG -> ICO using Pillow (already installed)
print("[build] Converting icon PNG -> ICO ...")
from PIL import Image, ImageOps
img = Image.open(ICON_PNG).convert("RGBA")
img = ImageOps.pad(img, (256, 256), color=(0, 0, 0, 0), method=Image.LANCZOS)
img.save(ICON_ICO, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print(f"[build] Icon saved: {ICON_ICO}")

# 2. Install PyInstaller
print("[build] Installing PyInstaller ...")
subprocess.run([VENV_PIP, "install", "--quiet", "pyinstaller"], check=True)

# 3. Build EXE
print("[build] Building VooDo.exe ...")
subprocess.run([
    VENV_PY, "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    f"--icon={ICON_ICO}",
    f"--add-data={ICON_PNG};.",
    f"--name=VooDo",
    f"--distpath={DESKTOP}",
    f"--workpath={os.path.join(BUILD_DIR, 'build_tmp')}",
    f"--specpath={os.path.join(BUILD_DIR, 'build_tmp')}",
    LAUNCHER,
], cwd=BUILD_DIR, check=True)

# 4. Cleanup
build_tmp = os.path.join(BUILD_DIR, "build_tmp")
if os.path.isdir(build_tmp):
    shutil.rmtree(build_tmp, ignore_errors=True)
print(f"\n[build] Done! VooDo.exe is on your Desktop.")
