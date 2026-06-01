"""Build VooDo.exe – run once, produces Desktop\\VooDo.exe."""
import subprocess, sys, os, shutil

VENV_PIP   = r"C:\Users\liavs\VooDo-Local\client\.venv\Scripts\pip.exe"
VENV_PY    = r"C:\Users\liavs\VooDo-Local\client\.venv\Scripts\python.exe"
ICON_PNG   = r"C:\Users\liavs\VooDo-Local\client\scripts\voodo_icon.png"
ICON_ICO   = r"C:\Users\liavs\VooDo-Local\client\scripts\voodo.ico"
LAUNCHER   = r"C:\Users\liavs\VooDo-Local\client\scripts\voodo_launcher.py"
DESKTOP    = r"C:\Users\liavs\Desktop"
BUILD_DIR  = r"C:\Users\liavs\VooDo-Local\client\scripts"

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
