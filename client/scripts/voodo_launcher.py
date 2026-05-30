"""VooDo Desktop Launcher – compiled to .exe via PyInstaller.

Launches dev_all.ps1 in a visible console window with the correct
working directory and backend URL.
"""
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIENT_DIR = os.path.join(REPO_ROOT, "client")
SCRIPT = os.path.join(CLIENT_DIR, "scripts", "dev_all.ps1")
BACKEND = "ws://127.0.0.1:7860"


def main():
    # Ensure paths exist
    if not os.path.isfile(SCRIPT):
        print(f"[VooDo] ERROR: Script not found: {SCRIPT}")
        input("Press Enter to close...")
        sys.exit(1)

    print()
    print("  ██╗   ██╗ ██████╗  ██████╗ ██████╗  ██████╗")
    print("  ██║   ██║██╔═══██╗██╔═══██╗██╔══██╗██╔═══██╗")
    print("  ██║   ██║██║   ██║██║   ██║██║  ██║██║   ██║")
    print("  ╚██╗ ██╔╝██║   ██║██║   ██║██║  ██║██║   ██║")
    print("   ╚████╔╝ ╚██████╔╝╚██████╔╝██████╔╝╚██████╔╝")
    print("    ╚═══╝   ╚═════╝  ╚═════╝ ╚═════╝  ╚═════╝")
    print()
    print(f"  Starting VooDo executor...")
    print(f"  Backend: {BACKEND}")
    print()

    try:
        proc = subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy", "Bypass",
                "-File", SCRIPT,
                "-Backend", BACKEND,
            ],
            cwd=CLIENT_DIR,
        )
    except KeyboardInterrupt:
        print("\n  [VooDo] Stopped by user.")
    except Exception as e:
        print(f"\n  [VooDo] Error: {e}")

    print()
    input("  VooDo executor stopped. Press Enter to close...")


if __name__ == "__main__":
    main()
