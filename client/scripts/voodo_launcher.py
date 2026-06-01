"""VooDo Desktop Launcher – compiled to .exe via PyInstaller.

Launches dev_all.ps1 entirely in the background (no black CMD window).
Uses a System Tray icon (pystray) to allow the user to view logs,
open the chat, or quit.
"""
import os
import subprocess
import sys
import webbrowser

SCRIPT_REL = os.path.join("client", "scripts", "dev_all.ps1")
BACKEND = "ws://127.0.0.1:7860"


def get_exe_dir() -> str:
    """Return the directory where the EXE (or .py) lives."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_repo_path() -> str | None:
    """Read saved path or prompt using a GUI dialog."""
    config = os.path.join(get_exe_dir(), "voodo_path.txt")

    if os.path.isfile(config):
        path = open(config, "r", encoding="utf-8").read().strip()
        if os.path.isfile(os.path.join(path, SCRIPT_REL)):
            return path

    # Prompt user with GUI since we don't have a console
    import tkinter as tk
    from tkinter import filedialog, messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo("VooDo Setup", "First-time setup: Please select your VooDo-Local folder.")
    while True:
        path = filedialog.askdirectory(title="Select VooDo-Local folder")
        if not path:
            return None  # User cancelled
        if os.path.isfile(os.path.join(path, SCRIPT_REL)):
            with open(config, "w", encoding="utf-8") as f:
                f.write(path)
            return path
        messagebox.showerror("Error", f"Could not find dev_all.ps1 in '{path}'. Please select the correct VooDo-Local folder.")


def check_single_instance():
    """Ensure only one instance of VooDo is running.
    If already running, open the chat UI and exit."""
    import ctypes
    mutex_name = "Global\\VooDo_Local_Mutex_123"
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    last_error = ctypes.windll.kernel32.GetLastError()
    
    # 183 is ERROR_ALREADY_EXISTS
    if last_error == 183:
        webbrowser.open("http://127.0.0.1:7860/")
        sys.exit(0)
    
    # Keep the mutex reference alive for the lifetime of this process
    return mutex


def main():
    _mutex = check_single_instance()
    
    repo = get_repo_path()
    if not repo:
        sys.exit(0)

    client_dir = os.path.join(repo, "client")
    script = os.path.join(repo, SCRIPT_REL)
    log_path = os.path.join(get_exe_dir(), "voodo.log")

    # Start the process hidden
    log_file = open(log_path, "w", encoding="utf-8")
    log_file.write("Starting VooDo executor...\n")
    log_file.write(f"Repo: {repo}\n")
    log_file.write(f"Backend: {BACKEND}\n\n")
    log_file.flush()

    CREATE_NO_WINDOW = 0x08000000
    proc = subprocess.Popen(
        [
            "powershell",
            "-ExecutionPolicy", "Bypass",
            "-File", script,
            "-Backend", BACKEND,
        ],
        cwd=client_dir,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )

    import pystray
    from PIL import Image

    def on_open_chat(icon, item):
        webbrowser.open("http://127.0.0.1:7860/")

    def on_view_logs(icon, item):
        if os.path.isfile(log_path):
            os.startfile(log_path)

    def on_quit(icon, item):
        proc.terminate()
        icon.stop()

    # Load icon from bundled PyInstaller temp folder, or local path
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(base_path, "voodo_icon.png")
    image = Image.open(icon_path)

    menu = pystray.Menu(
        pystray.MenuItem("Open VooDo Chat", on_open_chat),
        pystray.MenuItem("View Logs", on_view_logs),
        pystray.MenuItem("Quit", on_quit)
    )

    icon = pystray.Icon("VooDo", image, "VooDo AI Agent", menu)
    icon.run()

    log_file.close()


if __name__ == "__main__":
    main()

