"""VooDo Desktop Launcher – compiled to .exe via PyInstaller.

Launches dev_all.ps1 in a visible console window with the correct
working directory and backend URL.
"""
import os
import subprocess
import sys

SCRIPT_REL = os.path.join("client", "scripts", "dev_all.ps1")
BACKEND = "ws://127.0.0.1:7860"


def get_exe_dir() -> str:
    """Return the directory where the EXE (or .py) lives."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_repo_path() -> str:
    """Read or prompt for the VooDo-Local repo path."""
    config = os.path.join(get_exe_dir(), "voodo_path.txt")

    # Try reading saved path
    if os.path.isfile(config):
        path = open(config, "r", encoding="utf-8").read().strip()
        if os.path.isfile(os.path.join(path, SCRIPT_REL)):
            return path
        print(f"  [!] Saved path no longer valid: {path}")

    # Prompt user
    print("  First-time setup: enter the path to your VooDo-Local folder.")
    print("  Example: C:\\Users\\liavs\\VooDo-Local")
    print()
    while True:
        path = input("  Path: ").strip().strip('"')
        if os.path.isfile(os.path.join(path, SCRIPT_REL)):
            with open(config, "w", encoding="utf-8") as f:
                f.write(path)
            print(f"  [✓] Path saved to {config}")
            return path
        print(f"  [✗] Could not find dev_all.ps1 in '{path}'. Try again.")


def main():
    print()
    print("  ██╗   ██╗ ██████╗  ██████╗ ██████╗  ██████╗")
    print("  ██║   ██║██╔═══██╗██╔═══██╗██╔══██╗██╔═══██╗")
    print("  ██║   ██║██║   ██║██║   ██║██║  ██║██║   ██║")
    print("  ╚██╗ ██╔╝██║   ██║██║   ██║██║  ██║██║   ██║")
    print("   ╚████╔╝ ╚██████╔╝╚██████╔╝██████╔╝╚██████╔╝")
    print("    ╚═══╝   ╚═════╝  ╚═════╝ ╚═════╝  ╚═════╝")
    print()

    repo = get_repo_path()
    client_dir = os.path.join(repo, "client")
    script = os.path.join(repo, SCRIPT_REL)

    print(f"  Repo:    {repo}")
    print(f"  Backend: {BACKEND}")
    print()

    try:
        subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy", "Bypass",
                "-File", script,
                "-Backend", BACKEND,
            ],
            cwd=client_dir,
        )
    except KeyboardInterrupt:
        print("\n  [VooDo] Stopped by user.")
    except Exception as e:
        print(f"\n  [VooDo] Error: {e}")

    print()
    input("  VooDo executor stopped. Press Enter to close...")


if __name__ == "__main__":
    main()

