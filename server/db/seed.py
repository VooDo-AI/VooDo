"""Seed the solutions table with a handful of canned Windows fixes for demo.

Run: `python -m server.db.seed`
"""
from __future__ import annotations

import sys

from server.db.client import record_solution
from shared.protocol import SolutionRecord, SolutionStep, ToolCall

SEEDS: list[SolutionRecord] = [
    SolutionRecord(
        problem_summary="WiFi is disconnected or showing 'no internet'.",
        steps=[
            SolutionStep(action=ToolCall(name="check_network_status", args={}), note="Check internet connectivity."),
            SolutionStep(action=ToolCall(name="get_ip_info", args={}), note="Retrieve IP and DNS info."),
            SolutionStep(action=ToolCall(name="flush_dns", args={}), note="Clear DNS cache."),
            SolutionStep(action=ToolCall(name="toggle_network", args={"wifi": False}), note="Disable WiFi."),
            SolutionStep(action=ToolCall(name="wait", args={"seconds": 2}), note="Wait for the adapter to fully disable."),
            SolutionStep(action=ToolCall(name="toggle_network", args={"wifi": True}), note="Enable WiFi."),
            SolutionStep(action=ToolCall(name="wait", args={"seconds": 5}), note="Wait for the adapter to fully enable."),
            SolutionStep(action=ToolCall(name="check_network_status", args={}), note="Verify connectivity again."),
            SolutionStep(action=ToolCall(name="suggest_solution", args={"suggestion": "I have reset the Wi-Fi adapter and cleared the DNS cache. Please check if you have internet access now."}), note="Ask user to verify."),
        ],
    ),
    SolutionRecord(
        problem_summary="Audio is not playing through speakers or headphones.",
        steps=[
            SolutionStep(action=ToolCall(name="get_audio_devices", args={}), note="List available audio hardware."),
            SolutionStep(action=ToolCall(name="set_volume", args={"level": 50, "mute": False}), note="Ensure volume is set to 50 and unmuted."),
            SolutionStep(action=ToolCall(name="suggest_solution", args={"suggestion": "I've unmuted the audio and set the volume to 50. If you still don't hear anything, check if the correct output device is selected."}), note="Offer further manual steps."),
        ],
    ),
    SolutionRecord(
        problem_summary="Computer is running very slowly; want to see what's using CPU/RAM.",
        steps=[
            SolutionStep(action=ToolCall(name="get_system_info", args={}), note="Check RAM/CPU usage."),
            SolutionStep(action=ToolCall(name="list_running_apps", args={}), note="Check currently open apps."),
            SolutionStep(action=ToolCall(name="list_startup_programs", args={}), note="Identify heavy startup applications."),
            SolutionStep(action=ToolCall(name="suggest_solution", args={"suggestion": "I checked your system resources. If an app is consuming too much, I can close it for you, or you can manage startup apps."}), note="Offer next steps."),
        ],
    ),
    SolutionRecord(
        problem_summary="Printer is not printing or shows offline.",
        steps=[
            SolutionStep(action=ToolCall(name="list_printers", args={}), note="List installed printers and default status."),
            SolutionStep(action=ToolCall(name="clear_print_queue", args={}), note="Clear any stuck print jobs."),
            SolutionStep(action=ToolCall(name="suggest_solution", args={"suggestion": "I've listed your printers and cleared the print queue. Please try printing again."}), note="Ask user to test printing."),
        ],
    ),
    SolutionRecord(
        problem_summary="Bluetooth device won't pair or keeps disconnecting.",
        steps=[
            SolutionStep(action=ToolCall(name="list_usb_devices", args={}), note="Check if the Bluetooth dongle or internal hub is recognized."),
            SolutionStep(action=ToolCall(name="open_app", args={"app_name": "ms-settings:bluetooth"}), note="Open Bluetooth settings natively."),
            SolutionStep(action=ToolCall(name="search_files", args={"query": "bluetooth settings", "max_results": 5}), note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to the Bluetooth control panel."),
            SolutionStep(action=ToolCall(name="suggest_solution", args={"suggestion": "I have opened the Bluetooth settings. Please try toggling Bluetooth off and on, and then attempt to pair your device again."}), note="Suggest manual toggle."),
        ],
    ),
    SolutionRecord(
        problem_summary="Display resolution looks wrong or scaling is too small/large.",
        steps=[
            SolutionStep(action=ToolCall(name="open_app", args={"app_name": "ms-settings:display"}), note="Open display settings natively."),
            SolutionStep(action=ToolCall(name="search_files", args={"query": "display settings", "max_results": 5}), note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to the display control panel."),
            SolutionStep(action=ToolCall(name="suggest_solution", args={"suggestion": "I've opened the display settings. You can adjust the resolution and scaling here to fix the issue."}), note="Guide user to adjust settings."),
        ],
    ),
    SolutionRecord(
        problem_summary="Want to free up disk space — drive is nearly full.",
        steps=[
            SolutionStep(action=ToolCall(name="check_disk_space", args={}), note="Check available storage."),
            SolutionStep(action=ToolCall(name="clear_temp_files", args={}), note="Safely clear temp files."),
            SolutionStep(action=ToolCall(name="check_disk_space", args={}), note="Check available storage after clearing."),
            SolutionStep(action=ToolCall(name="suggest_solution", args={"suggestion": "I've cleared temporary files to free up disk space. If you still need more space, consider uninstalling large applications or using Disk Cleanup."}), note="Offer further advice."),
        ],
    ),
    SolutionRecord(
        problem_summary="Windows is asking to update / install pending updates.",
        steps=[
            SolutionStep(action=ToolCall(name="open_app", args={"app_name": "ms-settings:windowsupdate"}), note="Open Windows Update settings."),
            SolutionStep(action=ToolCall(name="search_files", args={"query": "windows update", "max_results": 5}), note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to the Windows Update panel."),
            SolutionStep(action=ToolCall(name="suggest_solution", args={"suggestion": "I've opened the Windows Update settings so you can review and install any pending updates."}), note="Prompt user to update."),
        ],
    ),
    SolutionRecord(
        problem_summary="A program is frozen and won't respond to clicks.",
        steps=[
            SolutionStep(action=ToolCall(name="list_running_apps", args={}), note="Find the names of running apps."),
            SolutionStep(action=ToolCall(name="get_event_log_errors", args={}), note="Check if any app recently crashed."),
            SolutionStep(action=ToolCall(name="suggest_solution", args={"suggestion": "If a specific app is frozen, I can forcefully close it for you using the close_app tool. Please let me know which one."}), note="Offer to close the app."),
        ],
    ),
    SolutionRecord(
        problem_summary="Want to change the default web browser.",
        steps=[
            SolutionStep(action=ToolCall(name="open_app", args={"app_name": "ms-settings:defaultapps"}), note="Open Default Apps settings."),
            SolutionStep(action=ToolCall(name="search_files", args={"query": "default apps", "max_results": 5}), note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to Default Apps settings."),
            SolutionStep(action=ToolCall(name="suggest_solution", args={"suggestion": "I've opened the Default Apps settings. You can change your default web browser here."}), note="Guide user to change default browser."),
        ],
    ),
    SolutionRecord(
        problem_summary="Open Zoom",
        steps=[
            SolutionStep(
                action=ToolCall(name="list_running_apps", args={}),
                note="Step 1 — Check if Zoom is already running. WHY: launching a second Zoom instance can trigger duplicate login prompts or ghost meeting windows that appear frozen.",
            ),
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "zoom"}),
                note="Step 2 — Launch Zoom. WHY: if already running this brings it to the foreground; if not, it starts a fresh session with no stale state.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "zoom", "max_results": 5}),
                note="Step 3 — Fallback: search for the Zoom executable if open_app did not launch it. WHY: open_app relies on the app being registered in the Windows app list; if Zoom was installed to a non-standard path or the registry entry is missing, open_app silently fails — search_files finds the actual .exe so the user can double-click it directly.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "Zoom is now open. Sign in if prompted. To join a meeting, click 'Join' and paste the meeting link or ID. If Zoom still did not open, use the file path found in the previous step to launch it directly. If no path was found, Zoom may not be installed — download it from zoom.us/download."},
                ),
                note="Step 4 — Confirm and anticipate the next action. WHY: most 'open Zoom' requests are pre-meeting — surfacing the Join flow saves a follow-up interaction.",
            ),
        ],
    ),
    SolutionRecord(
        problem_summary="Open Notepad",
        steps=[
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "notepad"}),
                note="Step 1 — Launch Notepad. WHY: Notepad is the fastest built-in plain-text editor on Windows — no formatting overhead, no autosave prompt for an empty file.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "notepad", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Notepad. WHY: search_files locates the notepad.exe on disk so the user can launch it directly if the registry entry is missing.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "Notepad is now open. Tip: if you're pasting text from a website or Word and want to strip formatting, paste into Notepad first (Ctrl+V), then copy from here and paste into your destination — Notepad removes all bold, colors, and fonts automatically."},
                ),
                note="Step 2 — Confirm and share the plain-text strip trick. WHY: the #1 reason users open Notepad is to strip rich formatting from copied text — proactively explaining it saves a second question.",
            ),
        ],
    ),
    SolutionRecord(
        problem_summary="Open Task Manager",
        steps=[
            SolutionStep(
                action=ToolCall(name="get_system_info", args={}),
                note="Step 1 — Snapshot CPU and RAM usage before opening Task Manager. WHY: gives a baseline reading so the agent can tell the user upfront if the system is already under pressure, rather than asking them to interpret the numbers themselves.",
            ),
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "taskmgr"}),
                note="Step 2 — Open Task Manager. WHY: the native tool shows real-time per-process CPU, RAM, disk, and network — everything needed to diagnose high resource usage, stuck processes, or startup bloat.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "task manager", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Task Manager. WHY: search_files finds taskmgr.exe on disk so the user can launch it directly if the registry entry is broken.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "Task Manager is now open. Useful tabs: 'Processes' (sorted by CPU or Memory) to find what's consuming resources, 'Startup' to disable apps that slow your boot, 'Performance' for a live graph of overall CPU/RAM/disk/network. To force-close a frozen app: right-click its row → End Task. Heads-up: ending a task loses any unsaved work in that app."},
                ),
                note="Step 3 — Orient the user to Task Manager's key tabs. WHY: most users only know the 'End Task' button — surfacing Startup and Performance tabs immediately increases the fix rate without another question.",
            ),
        ],
    ),
    SolutionRecord(
        problem_summary="Zoom is not opening or crashes on launch.",
        steps=[
            SolutionStep(action=ToolCall(name="close_app", args={"app_name": "zoom"}), note="Step 1 — Force-close any stuck Zoom processes. WHY: a partially crashed Zoom process holds a lock on its data files, so a fresh launch will immediately crash again unless the ghost process is cleared first."),
            SolutionStep(action=ToolCall(name="get_event_log_errors", args={}), note="Step 2 — Read the event log for Zoom crash details. WHY: the log records the exact DLL or component that faulted, which tells us whether the fix is 'clear the cache', 'update the driver', or 'reinstall'."),
            SolutionStep(action=ToolCall(name="open_app", args={"app_name": "zoom"}), note="Step 3 — Attempt to relaunch Zoom. WHY: after clearing the stuck process, most crash-on-launch issues are resolved by a clean restart."),
            SolutionStep(action=ToolCall(name="search_files", args={"query": "zoom", "max_results": 5}), note="Step 4 — Fallback: if open_app did not launch Zoom, search for its executable. WHY: open_app uses the Windows app registry; if Zoom's registry entry is corrupt or it was installed to a custom path, open_app silently fails — search_files locates the actual .exe so the user can launch it directly."),
            SolutionStep(action=ToolCall(name="suggest_solution", args={"suggestion": "I cleared stuck Zoom processes, checked crash logs, and attempted a relaunch. If Zoom still won't open: (1) use the file path found in the search step to launch it directly, (2) clear Zoom's cache by deleting C:\\Users\\<you>\\AppData\\Roaming\\Zoom\\data — this fixes most persistent crash loops, (3) if it still crashes, uninstall via Settings → Apps, reboot, then reinstall from zoom.us/download."}), note="Step 5 — Hand off with an ordered escalation. WHY: the cache-clear step fixes ~60% of persistent Zoom crashes and is safe to do without IT involvement."),
        ],
    ),
    SolutionRecord(
        problem_summary="Zoom video or microphone not working in a meeting.",
        steps=[
            SolutionStep(action=ToolCall(name="check_camera", args={}), note="Verify camera permissions and detection."),
            SolutionStep(action=ToolCall(name="get_audio_devices", args={}), note="Verify audio endpoints."),
            SolutionStep(action=ToolCall(name="get_event_log_errors", args={}), note="Check for recent camera or audio driver crashes in the event log."),
            SolutionStep(action=ToolCall(name="set_volume", args={"level": 70, "mute": False}), note="Ensure volume is high enough and unmuted."),
            SolutionStep(action=ToolCall(name="suggest_solution", args={"suggestion": "I've verified your camera and audio settings, and made sure your volume is unmuted. Please check Zoom's internal audio/video settings if the issue persists."}), note="Guide user to check Zoom settings."),
        ],
    ),

    # ──────────────────────────────────────────────────────────────────────
    # Extended template library — each step note is written as a plain-
    # English instruction with a clear PURPOSE so the agent (and any
    # human reading the DB) knows exactly what's being done and why.
    # Pattern:  "Step N — <verb>. WHY: <reason>. NEXT IF FAILS: <hint>."
    # ──────────────────────────────────────────────────────────────────────

    SolutionRecord(
        problem_summary="Browser pages are not loading even though Wi-Fi shows connected.",
        steps=[
            SolutionStep(
                action=ToolCall(name="check_network_status", args={}),
                note="Step 1 — Confirm the machine actually has internet by pinging an external host. WHY: 'Wi-Fi connected' only means the laptop reached the router; it doesn't prove the router reaches the internet. NEXT IF FAILS: continue to step 2 to inspect DNS/IP config.",
            ),
            SolutionStep(
                action=ToolCall(name="get_ip_info", args={}),
                note="Step 2 — Read the current IP, gateway, and DNS servers. WHY: a self-assigned IP like 169.254.x.x means DHCP failed; missing DNS servers means lookups will hang. NEXT IF FAILS: continue to step 3 — DNS is the most common silent failure.",
            ),
            SolutionStep(
                action=ToolCall(name="flush_dns", args={}),
                note="Step 3 — Clear the DNS resolver cache (`ipconfig /flushdns`). WHY: a stale cached failure for the user's homepage will keep returning 'no such host' even after the real DNS recovers. NEXT IF FAILS: continue to step 4 to reset the adapter.",
            ),
            SolutionStep(
                action=ToolCall(name="toggle_network", args={"wifi": False}),
                note="Step 4a — Turn the Wi-Fi radio OFF. WHY: forces Windows to drop any stuck association with the AP and re-handshake from scratch on the way back up.",
            ),
            SolutionStep(
                action=ToolCall(name="wait", args={"seconds": 3}),
                note="Step 4b — Wait 3 seconds. WHY: gives the OS time to fully unload the adapter driver before re-enabling — flipping faster than this often re-attaches to the broken state.",
            ),
            SolutionStep(
                action=ToolCall(name="toggle_network", args={"wifi": True}),
                note="Step 4c — Turn the Wi-Fi radio back ON. WHY: forces a clean re-association which usually fixes a stuck DHCP lease or PMK cache problem.",
            ),
            SolutionStep(
                action=ToolCall(name="wait", args={"seconds": 6}),
                note="Step 4d — Wait 6 seconds for the adapter to come up. WHY: rushing the next check before DHCP has assigned an IP will give a false 'still broken' reading.",
            ),
            SolutionStep(
                action=ToolCall(name="check_network_status", args={}),
                note="Step 5 — Re-test connectivity. WHY: this is the success criterion — if ping works now, the fix is verified end-to-end, not just 'the adapter is up'.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I flushed DNS and re-cycled your Wi-Fi adapter. If pages still won't load, the issue is likely upstream (router, ISP) or a VPN/proxy is hijacking traffic — try unplugging the router for 30 seconds, or disable any VPN client and retry."},
                ),
                note="Step 6 — Hand off with the next escalation. WHY: tells the user exactly what to try if the automated fix didn't catch it, instead of leaving them stuck.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="System is running out of memory or apps feel sluggish.",
        steps=[
            SolutionStep(
                action=ToolCall(name="get_system_info", args={}),
                note="Step 1 — Snapshot total/free RAM and CPU usage. WHY: establishes a baseline so we know whether the problem is RAM pressure, CPU saturation, or thermal throttling — each has a different fix.",
            ),
            SolutionStep(
                action=ToolCall(name="list_running_apps", args={}),
                note="Step 2 — List the top memory/CPU consumers. WHY: the fix is usually 'close the one app eating 4 GB', and we can't suggest that until we know which app it is. Look for browser tab hosts, Teams/Slack/Outlook, and any background indexers.",
            ),
            SolutionStep(
                action=ToolCall(name="list_startup_programs", args={}),
                note="Step 3 — List auto-start programs. WHY: chronic sluggishness right after login almost always traces to too many startup apps. Identifying them sets up the user's long-term fix even if today's symptom comes from something else.",
            ),
            SolutionStep(
                action=ToolCall(name="get_event_log_errors", args={}),
                note="Step 4 — Pull recent Application/System errors. WHY: a crashing service that auto-restarts every 10 seconds will tank performance silently. The event log surfaces it where Task Manager can't.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I gathered the resource picture. If one app is dominating memory or CPU, ask me to close it by name and I'll do it (close_app). For a permanent improvement, you can disable any startup programs you don't actually need via Settings → Apps → Startup."},
                ),
                note="Step 5 — Offer the obvious next action. WHY: the agent CAN'T close arbitrary apps without naming one — asking the user to pick keeps the destructive step (close_app) under explicit human approval.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="Sound is muted, very quiet, or coming from the wrong output device.",
        steps=[
            SolutionStep(
                action=ToolCall(name="get_audio_devices", args={}),
                note="Step 1 — Enumerate all playback devices and flag which one is the default. WHY: 'no sound' is almost always 'sound is playing to a different device' (e.g. HDMI monitor, disconnected Bluetooth). We need the device list before any change.",
            ),
            SolutionStep(
                action=ToolCall(name="set_volume", args={"level": 60, "mute": False}),
                note="Step 2 — Force unmute and set master volume to a comfortable 60%. WHY: a master-volume mute is invisible in many apps — they'll show full bars but produce silence. Setting an explicit level fixes both states at once.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I unmuted the system and set volume to 60%. If you still hear nothing, the audio is probably going to the wrong device (e.g. an HDMI monitor or a disconnected headset). Tell me which output you want (e.g. 'speakers' or 'headphones') and I can switch it (set_default_audio_device)."},
                ),
                note="Step 3 — Offer the device switch as the next step. WHY: changing the default audio device CAN startle the user if they had it that way intentionally, so we wait for them to name a target instead of guessing.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="Printer says 'offline' or jobs are stuck in the print queue.",
        steps=[
            SolutionStep(
                action=ToolCall(name="list_printers", args={}),
                note="Step 1 — List installed printers and their reported status. WHY: confirms the printer Windows thinks is the default actually matches the one the user is trying to print to — getting this wrong wastes the next 4 steps.",
            ),
            SolutionStep(
                action=ToolCall(name="clear_print_queue", args={}),
                note="Step 2 — Purge stuck jobs from the spooler queue. WHY: one stuck job at the front blocks every subsequent job and makes a healthy printer look offline. This single step fixes ~70% of 'printer offline' reports.",
            ),
            SolutionStep(
                action=ToolCall(name="check_network_status", args={}),
                note="Step 3 — Verify network connectivity. WHY: most modern printers are network-attached; if the laptop has no LAN/Wi-Fi route, every job will fail with a confusing 'printer offline' message even though the printer is fine.",
            ),
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "ms-settings:printers"}),
                note="Step 4 — Open the Printers & Scanners settings page natively. WHY: from here the user can right-click the device and choose 'Use Printer Offline → uncheck' or 'See what's printing' — actions that need a real human decision because they affect physical hardware.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "printers settings", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to the Printers control panel.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I cleared the stuck print queue and opened the Printers settings. If the printer is still offline, please confirm: (1) the printer is powered on, (2) it shows the SAME Wi-Fi network name as this PC, and (3) no paper jam or out-of-toner light. Then try printing again — the queue should now be empty."},
                ),
                note="Step 5 — Hand off with a physical-world checklist. WHY: the agent literally cannot fix paper jams or toner; calling that out explicitly prevents an infinite 'try again' loop.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="The C: drive is almost full and Windows is warning about low disk space.",
        steps=[
            SolutionStep(
                action=ToolCall(name="check_disk_space", args={}),
                note="Step 1 — Read free/used space on every drive. WHY: gives a concrete BEFORE number so step 4 can prove the cleanup actually freed space, not just 'felt like it did'.",
            ),
            SolutionStep(
                action=ToolCall(name="clear_temp_files", args={}),
                note="Step 2 — Delete %TEMP% and Windows update leftovers safely. WHY: this is the only fully-automatic destructive step we trust — it touches only known-safe locations (no Documents, no Downloads). Usually frees 2-20 GB on a long-running install.",
            ),
            SolutionStep(
                action=ToolCall(name="check_disk_space", args={}),
                note="Step 3 — Re-read free/used space. WHY: the AFTER number proves the fix worked and tells us if the problem is 'solved' or 'still serious' before we suggest the next, more invasive cleanup.",
            ),
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "ms-settings:storagepolicies"}),
                note="Step 4 — Open Storage Sense settings. WHY: Storage Sense is the proper long-term fix (auto-deletes old Downloads, empties Recycle Bin on schedule) — turning it on once is worth more than ten manual cleanups.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "storage sense", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to the Storage Sense panel.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I cleared temporary files and opened Storage Sense. If C: is still low: (1) check Downloads — sort by size and delete what you don't need, (2) uninstall apps you no longer use via Settings → Apps, (3) move large media to an external drive or OneDrive. Avoid manually deleting anything inside C:\\Windows."},
                ),
                note="Step 5 — Hand off with safe manual options. WHY: explicitly tells the user where NOT to delete (C:\\Windows) — agents have to assume the user might literally try `del /s` in System32 if given vague advice.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="Windows updates are stuck downloading or failing to install.",
        steps=[
            SolutionStep(
                action=ToolCall(name="check_disk_space", args={}),
                note="Step 1 — Verify there's at least 10 GB free on C:. WHY: feature updates need 8-12 GB scratch space; an install will silently fail-and-retry forever on a near-full drive, and no error message will explain why.",
            ),
            SolutionStep(
                action=ToolCall(name="check_network_status", args={}),
                note="Step 2 — Verify internet connectivity. WHY: a flaky connection causes updates to download to ~99% and then restart from 0%. Confirming the link is stable is the cheapest pre-check.",
            ),
            SolutionStep(
                action=ToolCall(name="get_event_log_errors", args={}),
                note="Step 3 — Pull Windows Update errors from the event log. WHY: surfaces the actual hex error code (0x80070002, 0x800f0922, …) which maps to a specific fix in Microsoft's docs — without this we'd just be guessing.",
            ),
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "ms-settings:windowsupdate"}),
                note="Step 4 — Open the Windows Update settings page. WHY: from here the user clicks 'Check for updates' / 'Retry' / 'Pause for 7 days' — all decisions that need an explicit human click for safety (a restart may follow).",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "windows update", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to Windows Update.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I checked free disk space, connectivity, and the update error logs, then opened Windows Update. Try clicking 'Retry' or 'Check for updates' there. If it still fails: (1) the error code in Settings tells you the cause — Google it with 'Windows Update <code>', (2) restart the PC and try once more (clears stuck service state), (3) as a last resort, run the Windows Update troubleshooter from Settings → System → Troubleshoot."},
                ),
                note="Step 5 — Hand off with escalation steps. WHY: 'update troubleshooter' is the official Microsoft path; pointing at it avoids us re-implementing 100 KB of Microsoft's repair logic.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="Bluetooth headphones or mouse won't pair or keep disconnecting.",
        steps=[
            SolutionStep(
                action=ToolCall(name="list_usb_devices", args={}),
                note="Step 1 — Check whether the Bluetooth adapter itself is enumerated. WHY: on many laptops the BT radio shares a USB hub with Wi-Fi; if the hub vanished from Device Manager, no pairing will ever work and the fix is a power-cycle, not a re-pair.",
            ),
            SolutionStep(
                action=ToolCall(name="get_event_log_errors", args={}),
                note="Step 2 — Check the event log for Bluetooth driver crashes. WHY: 'won't pair' is often a driver that crashed silently 4 minutes ago. The log entry will name the exact device causing it.",
            ),
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "ms-settings:bluetooth"}),
                note="Step 3 — Open the Bluetooth settings page. WHY: pairing requires the user to put the device into pairing mode (a physical button on the device) at the same instant Windows is scanning — only the human can do that half.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "bluetooth settings", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to Bluetooth settings.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I opened the Bluetooth settings. Now: (1) on the device itself, hold the pairing button until its LED FLASHES (usually 5-10 seconds — a steady LED is not pairing mode), (2) in the Windows settings I just opened, click 'Add device → Bluetooth' and pick it from the list, (3) if your device shows but won't connect, click it → Remove, then re-add. If you don't see your device at all even after step 1, restart the PC — that re-loads the Bluetooth driver."},
                ),
                note="Step 4 — Hand off with a precise physical recipe. WHY: 99% of failed pairings are timing problems — the user starts pairing mode 30 seconds before Windows starts scanning. Spelling out 'LED must FLASH not be STEADY' fixes most reports on the spot.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="A specific application is frozen and ignoring clicks.",
        steps=[
            SolutionStep(
                action=ToolCall(name="list_running_apps", args={}),
                note="Step 1 — List running processes and which are non-responsive. WHY: 'frozen' is sometimes a single window of a multi-window app — we need the exact process name to close the right one without nuking unrelated work.",
            ),
            SolutionStep(
                action=ToolCall(name="get_event_log_errors", args={}),
                note="Step 2 — Pull recent application crash events. WHY: if the app already crashed and just hasn't redrawn yet, there will be a hang-or-crash entry in the log — telling the user this prevents them blaming the wrong thing (e.g. their mouse).",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I gathered the list of running apps and their state. Tell me the EXACT name of the frozen app (e.g. 'chrome', 'outlook', 'excel') and I'll force-close it for you with close_app. Heads up: any unsaved work in that app will be lost — if you have unsaved changes, give it 30 seconds first to see if it un-freezes on its own."},
                ),
                note="Step 3 — Require an explicit app name. WHY: close_app is destructive (data loss risk on unsaved files) so the agent must NEVER guess which app to kill — we ask the user to name it.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="Screen is too dim, too bright, or auto-brightness is misbehaving.",
        steps=[
            SolutionStep(
                action=ToolCall(name="get_system_info", args={}),
                note="Step 1 — Check whether the device is on AC or battery. WHY: Windows has separate brightness curves for plugged-in vs. on-battery; fighting auto-brightness while on battery is usually a power-plan setting, not a display problem.",
            ),
            SolutionStep(
                action=ToolCall(name="change_display_brightness", args={"level": 70}),
                note="Step 2 — Set brightness to a clearly visible 70%. WHY: gives the user an immediate, obvious 'something changed' signal and rules out the simple case (it really was just turned down).",
            ),
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "ms-settings:display"}),
                note="Step 3 — Open the Display settings page. WHY: from here the user can disable 'Change brightness automatically when lighting changes' (the most common cause of mystery dimming) and 'Help improve battery by optimizing the content shown'.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "display settings", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to Display settings.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I set brightness to 70% and opened Display settings. To stop the screen auto-dimming on you: untick 'Change brightness automatically when lighting changes' and 'Help improve battery by optimizing the content shown and brightness' on that page. If the brightness slider does NOTHING, the display driver is the issue — open Device Manager → Display adapters → right-click → Update driver."},
                ),
                note="Step 4 — Hand off with the two switches that fix this 90% of the time. WHY: the user almost certainly doesn't know those toggles exist, and they're buried under a non-obvious 'Brightness & color' section.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="Camera shows a black image or 'camera in use by another app' in Teams/Zoom/Meet.",
        steps=[
            SolutionStep(
                action=ToolCall(name="check_camera", args={}),
                note="Step 1 — Verify the camera is detected and which app is holding it. WHY: 'camera in use' means another process has an exclusive lock — we need its name before we can break the conflict.",
            ),
            SolutionStep(
                action=ToolCall(name="list_running_apps", args={}),
                note="Step 2 — List other potential camera consumers (Teams, Zoom, OBS, the legacy Camera app, browsers with a hangover from Meet). WHY: usually it's the Windows Camera app left open from earlier, or a closed Teams meeting whose process didn't fully exit.",
            ),
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "ms-settings:privacy-webcam"}),
                note="Step 3 — Open the Camera privacy settings. WHY: in Windows 10/11, per-app camera access can be DENIED at the OS level — even if the app shows 'allow camera', the global toggle here can override it and produce a confusing black frame.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "camera privacy", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to Camera privacy settings.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I checked the camera and opened the Camera privacy page. Two likely fixes: (1) if you see 'app is using your camera' for an app you're not actively in, tell me its name and I'll close it (close_app), (2) on the privacy page I just opened, make sure 'Camera access' is ON and the specific app (Teams, Zoom, Chrome) has its toggle ON. After fixing, fully QUIT and re-open the meeting app — most apps only re-check camera permission on startup."},
                ),
                note="Step 4 — Hand off with a clear two-branch fix. WHY: separates the 'process conflict' branch from the 'OS permission' branch — they look identical to users but need different fixes, and saying both spares a back-and-forth.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="Mouse cursor is jumpy, lagging, or freezing intermittently.",
        steps=[
            SolutionStep(
                action=ToolCall(name="list_usb_devices", args={}),
                note="Step 1 — Enumerate USB devices and look for repeating connect/disconnect entries. WHY: a flaky USB port or a dying wireless dongle disconnects and reconnects every few seconds — each reconnect freezes the cursor for ~0.5s and looks exactly like lag.",
            ),
            SolutionStep(
                action=ToolCall(name="get_system_info", args={}),
                note="Step 2 — Read CPU load. WHY: 100% CPU starves the mouse driver of cycles — the cursor 'lag' is actually the whole OS lagging. If CPU is normal, the cause is hardware/driver; if pegged, the cause is whatever's pegging it.",
            ),
            SolutionStep(
                action=ToolCall(name="get_event_log_errors", args={}),
                note="Step 3 — Pull HID/USB driver errors from the event log. WHY: 'Device Manager' won't show transient driver crashes; the event log will, and the entry names the device that's misbehaving.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I checked USB devices, CPU load, and driver errors. Try in order: (1) if you're on a wireless mouse, replace the battery — low battery is the #1 cause of jumpy cursors and looks like 'broken mouse', (2) move the receiver to a different USB port, ideally one directly on the PC not on a hub or monitor, (3) plug a wired mouse in temporarily — if it's smooth, the wireless one is the problem; if it lags too, the driver/CPU is."},
                ),
                note="Step 5 — Hand off with an ordered, cheapest-first checklist. WHY: 'replace the battery' costs 30 seconds and fixes more cursor complaints than any software step — putting it first saves the user from a driver-reinstall rabbit hole.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="Need to take a screenshot of the screen.",
        steps=[
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "snippingtool"}),
                note="Step 1 — Launch the built-in Snipping Tool. WHY: this is the modern Windows screenshot tool — gives the user a rectangle/freeform selector and copies the capture to clipboard automatically. Better than blindly pressing PrintScreen because it works the same on every Windows 10/11 build.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "snipping tool", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Snipping Tool. WHY: search_files locates SnippingTool.exe on disk so the user can launch it directly if the registry entry is missing.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I opened the Windows snipping tool. Drag to select the area you want — it'll be copied to your clipboard. Paste with Ctrl+V into any chat, email, or document. Tip: pressing Win+Shift+S opens the same tool any time, without needing me."},
                ),
                note="Step 2 — Teach the keyboard shortcut. WHY: a one-time fix is fine, but Win+Shift+S is the actual long-term answer — once the user knows it, they'll never need to ask again.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="Files are missing or I can't find a recently saved document.",
        steps=[
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "recent", "max_results": 20}),
                note="Step 1 — Run a quick search for recently modified files. WHY: 90% of 'lost file' reports are 'saved to a different folder than expected' — usually Downloads, OneDrive, or Desktop. A recent-modified search finds it without the user having to remember the name.",
            ),
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "ms-settings:storagesense"}),
                note="Step 2 — Open Storage Sense settings. WHY: if Storage Sense ran recently with 'delete files in Downloads older than X days' enabled, it may have eaten the file. We need the user to see whether that setting is on before we conclude the file is unrecoverable.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "storage sense", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to Storage Sense settings.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I searched for recent files and opened Storage Sense. Three places to check yourself: (1) Recycle Bin — double-click on the desktop, files deleted in the last 30 days are usually still recoverable, (2) your app's own recent-files menu (Word: File → Open → Recent; Excel same), (3) OneDrive's web version at onedrive.live.com — it keeps deleted files for 30 days even after the local Recycle Bin is emptied. Tell me the file's exact name and I'll search for it specifically."},
                ),
                note="Step 3 — Hand off with three recoverable-source checks. WHY: each of the three covers a different deletion path (manual delete, app crash, cloud sync) — together they recover the file >95% of the time.",
            ),
        ],
    ),

    # ──────────────────────────────────────────────────────────────────────
    # Second extended batch — same explicit Step / WHY / NEXT IF FAILS
    # format. Covers scenarios not yet templated above.
    # ──────────────────────────────────────────────────────────────────────

    SolutionRecord(
        problem_summary="Keyboard is typing the wrong characters or has no input at all.",
        steps=[
            SolutionStep(
                action=ToolCall(name="list_usb_devices", args={}),
                note="Step 1 — Enumerate USB devices and look for the keyboard. WHY: if the keyboard isn't even enumerated, no software fix will work — the cable / receiver is the cause and the user needs a different port. If it IS enumerated, the issue is software (layout, language, stuck key).",
            ),
            SolutionStep(
                action=ToolCall(name="get_event_log_errors", args={}),
                note="Step 2 — Pull HID / keyboard driver errors from the event log. WHY: 'wrong characters' can mean a driver crashed and Windows fell back to a generic layout. The log entry names the device and timestamps the failure.",
            ),
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "ms-settings:keyboard"}),
                note="Step 3 — Open the Keyboard / Language settings. WHY: 99% of 'typing the wrong characters' reports are accidentally-pressed Alt+Shift (which cycles input languages on Windows). From here the user can see which language is active and remove extras.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "keyboard settings", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to Keyboard settings.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I checked your USB devices and driver errors, then opened Keyboard settings. The fix usually is: (1) look at the bottom-right of the taskbar — if it shows 'ENG', 'HEB', 'RUS' etc., press WIN+SPACE to cycle to the language you want, (2) on the settings page I opened, remove every language you don't actually use to prevent it happening again. If it's a single key acting weird (e.g. ; typing :), check Num Lock and Caps Lock LEDs — both off should be the normal state."},
                ),
                note="Step 4 — Hand off with the WIN+SPACE shortcut. WHY: this is THE answer for the most common report and almost no user knows the shortcut — they just live with the wrong layout.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="External monitor is not detected or shows 'No signal'.",
        steps=[
            SolutionStep(
                action=ToolCall(name="get_event_log_errors", args={}),
                note="Step 1 — Check display-driver errors in the event log. WHY: a recent display driver crash (Display TDR, error 4101) explains both 'no signal' and 'monitor not detected' — without this, we'd waste steps on cable checks when the GPU driver is the culprit.",
            ),
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "ms-settings:display"}),
                note="Step 2 — Open Display settings. WHY: this page has the 'Detect' button that re-scans for monitors AND 'Multiple displays' dropdown where the user can pick Extend / Duplicate / Second screen only — each of which fixes a different 'no signal' cause.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "display settings", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to Display settings.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I opened Display settings. Try in order: (1) on this page, scroll down and click 'Detect' (under 'Multiple displays') — wakes monitors that didn't auto-handshake, (2) press WIN+P and pick 'Extend' or 'Duplicate' — if you accidentally hit 'PC screen only', the second monitor will go black, (3) unplug the monitor cable for 10 seconds and replug — clears stuck HDMI/DisplayPort handshake state, (4) try a different cable — a broken HDMI cable looks IDENTICAL to a broken monitor."},
                ),
                note="Step 3 — Hand off in ordered, cheapest-first. WHY: WIN+P is the answer for ~40% of these reports and takes 3 seconds; cable swap is the answer for another ~30%. Software fixes come BEFORE hardware fixes because they're free.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="VPN won't connect or keeps dropping.",
        steps=[
            SolutionStep(
                action=ToolCall(name="check_network_status", args={}),
                note="Step 1 — Confirm the underlying internet works WITHOUT the VPN. WHY: a VPN can't tunnel over a connection that isn't there. If basic internet is broken, every VPN debug step that follows is wasted.",
            ),
            SolutionStep(
                action=ToolCall(name="get_ip_info", args={}),
                note="Step 2 — Read current IP / DNS. WHY: if there's already a tunneled IP (10.x.x.x or a corporate range) the VPN may actually be 'connected' but not routing — the symptom looks like 'won't connect' but the fix is different (it's a routing issue, not auth).",
            ),
            SolutionStep(
                action=ToolCall(name="flush_dns", args={}),
                note="Step 3 — Flush DNS cache. WHY: stale entries for internal corporate hostnames (e.g. intranet.company.local) from BEFORE the VPN was connected will keep failing to resolve. Flushing forces a re-lookup over the VPN's DNS.",
            ),
            SolutionStep(
                action=ToolCall(name="get_event_log_errors", args={}),
                note="Step 4 — Pull VPN / RasMan / IKEEXT errors from the event log. WHY: built-in Windows VPN errors surface here with specific codes (691 = bad credentials, 800 = no route, 809 = NAT/firewall block) — each maps to a different fix.",
            ),
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "ms-settings:network-vpn"}),
                note="Step 5 — Open VPN settings. WHY: from here the user can disconnect → reconnect the connection (clearing a stuck session), edit credentials, or remove and re-add the profile entirely. None of these can be done safely without explicit human action.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "vpn settings", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to VPN settings.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I verified your base internet, flushed DNS, and opened VPN settings. Likely fixes: (1) disconnect and reconnect on the page I opened — clears a stuck session 60% of the time, (2) if your company uses a vendor client (Cisco AnyConnect, GlobalProtect, FortiClient, OpenVPN), restart THAT app from the system tray — not the Windows page I opened, (3) if you're on hotel/coffee-shop Wi-Fi, sign into the captive portal first (open a regular site like example.com), then retry the VPN — most public Wi-Fi blocks VPN until you've accepted their terms."},
                ),
                note="Step 6 — Hand off branching on vendor client vs. Windows built-in. WHY: half of VPN issues are 'wrong app being told to reconnect' — the user opens Windows Settings while the actual VPN runs from a tray icon they forgot about.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="OneDrive is stuck syncing or showing a sync error.",
        steps=[
            SolutionStep(
                action=ToolCall(name="check_network_status", args={}),
                note="Step 1 — Verify internet connectivity. WHY: OneDrive sync goes idle (not 'errors') when offline — the user sees 'not syncing' and panics. Confirming the network is fine narrows the cause to OneDrive itself.",
            ),
            SolutionStep(
                action=ToolCall(name="check_disk_space", args={}),
                note="Step 2 — Verify free space on C:. WHY: OneDrive refuses to sync new files when free space drops below ~10% of the drive AND below ~1 GB. The error in the UI says 'sync error' but the real cause is disk-full.",
            ),
            SolutionStep(
                action=ToolCall(name="list_running_apps", args={}),
                note="Step 3 — Check whether OneDrive.exe is actually running. WHY: a crashed OneDrive process shows the cloud icon as grey/missing in the tray; the fix is to relaunch it, not to debug sync rules.",
            ),
            SolutionStep(
                action=ToolCall(name="get_event_log_errors", args={}),
                note="Step 4 — Pull recent OneDrive errors from the event log. WHY: OneDrive logs its sync failures here with codes (0x8004de40 = sign-in, 0x80070005 = permissions) — each maps to a different fix the user must apply themselves.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I checked network, disk, the OneDrive process, and recent errors. Most-common fixes: (1) right-click the OneDrive cloud icon in your taskbar (bottom-right) → Settings → Account → 'Unlink this PC', then sign back in — clears 70% of sync errors, (2) if a specific file is stuck, look for a filename with illegal characters (< > : \" / \\ | ? *) or a path longer than 256 chars — OneDrive silently refuses these, (3) if the cloud icon is missing entirely, OneDrive crashed — search 'OneDrive' in Start and re-launch it."},
                ),
                note="Step 5 — Hand off with the unlink-and-relink reset. WHY: this is the official Microsoft repair step and works far more often than any other fix; surfacing it explicitly saves a long manual debug.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="Taskbar or Start menu is unresponsive or missing icons.",
        steps=[
            SolutionStep(
                action=ToolCall(name="list_running_apps", args={}),
                note="Step 1 — Check whether explorer.exe is running. WHY: the taskbar, Start menu, and desktop icons are all owned by explorer.exe. If it crashed, the user will see a blank black bottom bar or no taskbar at all. The fix is restart-explorer, not reboot.",
            ),
            SolutionStep(
                action=ToolCall(name="get_event_log_errors", args={}),
                note="Step 2 — Pull recent application crash errors. WHY: a third-party shell extension or a corrupt icon-cache crashes explorer.exe repeatedly — the log names the faulting DLL so we can tell the user what to uninstall.",
            ),
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "taskmgr"}),
                note="Step 3 — Open Task Manager so the user can restart explorer.exe themselves. WHY: this is the safe, official fix — far better than us blindly killing explorer.exe (which can leave the desktop in a half-state).",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "task manager", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Task Manager. WHY: search_files finds taskmgr.exe on disk so the user can launch it directly if the registry entry is broken.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I opened Task Manager. In there: scroll to find 'Windows Explorer' under Processes → click it once → click 'Restart' (bottom-right). Your taskbar will flash and rebuild. If this fixes it temporarily but it keeps crashing: (1) on Windows 11, right-click the taskbar → Taskbar settings → toggle every section off, restart explorer, toggle them back on one at a time, (2) the long-term fix is `sfc /scannow` in an admin terminal — but that needs PowerShell which I can't run for you for security reasons. Ask your IT admin to run it."},
                ),
                note="Step 4 — Hand off with the safe Task Manager restart. WHY: voo·do can't run sfc /scannow (security restriction on shells), so we have to surface that path verbally and route the user to IT for the system-file repair.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="PC takes a very long time to boot or log in.",
        steps=[
            SolutionStep(
                action=ToolCall(name="list_startup_programs", args={}),
                note="Step 1 — Enumerate everything that auto-runs at login. WHY: slow boots are 90% startup apps — every additional one adds 1-5 seconds. Without this list we can't tell the user what to disable.",
            ),
            SolutionStep(
                action=ToolCall(name="check_disk_space", args={}),
                note="Step 2 — Check free space on C:. WHY: when C: is below ~10% free, Windows can't write its pagefile efficiently and login time doubles. This is a fixable cause we'd miss otherwise.",
            ),
            SolutionStep(
                action=ToolCall(name="get_event_log_errors", args={}),
                note="Step 3 — Pull boot-time errors from the event log. WHY: a hung service that times out adds 30 seconds to login. The log entry names the service so the user (or IT) can disable it.",
            ),
            SolutionStep(
                action=ToolCall(name="get_system_info", args={}),
                note="Step 4 — Read RAM and disk type. WHY: 8 GB RAM + spinning HDD = legitimately slow boots no amount of tweaking will fix — at that point the honest answer is 'this is hardware, not software'. We must not promise a fix we can't deliver.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I gathered startup apps, free space, boot errors, and your hardware specs. Likely fixes (do in order): (1) on the Task Manager → Startup tab, disable any app you don't NEED at login (Teams, Spotify, OneDrive can wait — they start themselves when you actually open them), (2) if C: is below 10% free, run my 'free up disk space' workflow first, (3) if you have an HDD (not SSD) with only 8 GB RAM, no software fix will make boot fast — an SSD upgrade is the real answer; talk to IT."},
                ),
                note="Step 5 — Hand off honestly about hardware limits. WHY: chasing software fixes on an HDD/8GB machine wastes hours; calling that out up front respects the user's time.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="Text or UI on an external monitor is too small or too large.",
        steps=[
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "ms-settings:display"}),
                note="Step 1 — Open Display settings. WHY: scaling is set PER MONITOR in Windows, and the dropdown for the external monitor is invisible unless you first click the monitor's number tile on this page. Getting the user to the right page is half the work.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "display settings", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to Display settings.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I opened Display settings. To fix per-monitor scaling: (1) click the numbered rectangle representing the EXTERNAL monitor at the top of the page (it'll highlight), (2) scroll down to 'Scale and layout' → 'Scale' — try 100% for a 24\" 1080p monitor, 125% or 150% for a 27\" 4K, (3) sign out and back in if some apps still look fuzzy — many older apps (Outlook 2016, legacy line-of-business apps) only re-read DPI at login. Tip: don't use 'Recommended' if it's too small for you; manually pick a percentage that's comfortable."},
                ),
                note="Step 2 — Hand off with concrete scale percentages. WHY: 'try a different scaling' is useless advice; '125% for a 27-inch 4K' is actionable. Specific numbers > vague encouragement.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="Need to record the screen as a video.",
        steps=[
            SolutionStep(
                action=ToolCall(name="check_disk_space", args={}),
                note="Step 1 — Verify there's at least 2 GB free on C:. WHY: screen recordings save to C:\\Users\\<user>\\Videos\\Captures by default and grow ~150 MB/minute at 1080p. A near-full drive will silently corrupt the recording at the worst moment.",
            ),
            SolutionStep(
                action=ToolCall(name="get_system_info", args={}),
                note="Step 2 — Check whether the GPU supports hardware encoding. WHY: the built-in Xbox Game Bar recorder uses GPU h.264 — on integrated graphics that don't support it (some old Intel HD), recording will fail with no error. We must verify before promising a fix.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I checked disk space and your GPU. Use the built-in recorder: (1) press WIN+G to open Xbox Game Bar (it works on the desktop too, not just games), (2) click the 'Capture' widget → red record button, (3) press WIN+ALT+R to stop. Recordings save to Videos\\Captures. Limitations: it can't record File Explorer or the desktop itself in some Windows builds — if it won't record what you're trying to capture, install OBS Studio (free, official) for full flexibility."},
                ),
                note="Step 3 — Hand off with the WIN+G shortcut. WHY: most users don't know Windows has a built-in recorder at all; teaching the shortcut is the actual fix.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="I forgot my password or my password isn't working.",
        steps=[
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "ms-settings:signinoptions"}),
                note="Step 1 — Open Sign-in options. WHY: voo·do CANNOT reset passwords — that requires admin rights and would be a critical security boundary violation. But we can route the user to the official, safe page that handles it.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "sign in options", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to Sign-in Options settings.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I opened Sign-in options. CRITICAL: I cannot reset your password for you — that would be a serious security issue. Your options: (1) if this is a personal Microsoft account, go to account.microsoft.com/password/reset on your phone, (2) if this is a WORK account (Office 365 / Entra ID), go to passwordreset.microsoftonline.com — you'll need your phone number or alternate email on file, (3) if it's a LOCAL Windows account on this PC, you need an admin to reset it (typically your IT department), (4) if Caps Lock is on and you didn't notice, that's by far the #1 cause of 'password isn't working' — check the LED. Never give your password to anyone, including IT or me, who asks for it directly."},
                ),
                note="Step 2 — Hand off the password-reset path WITHOUT touching the password. WHY: this is a security boundary — agents must never reset, store, or be told passwords. The suggestion also includes the Caps Lock check and an anti-phishing reminder.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="A specific file type opens in the wrong program (e.g. PDFs open in Edge instead of Acrobat).",
        steps=[
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "ms-settings:defaultapps"}),
                note="Step 1 — Open Default Apps settings. WHY: as of Windows 11 22H2, file-type defaults must be set per extension — there's no longer a 'make Acrobat default for everything' single button. The settings page is the only safe place to do this.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "default apps", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to Default Apps settings.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I opened Default Apps settings. To change which program opens a file type: (1) in the search box at the top of that page, type the extension you want to change INCLUDING the dot — e.g. '.pdf', '.txt', '.mp4', (2) click the result, then click the current app's tile, (3) pick the app you want from the popup → click 'Set default'. The change is immediate and applies to all future double-clicks. If the app you want isn't in the picker, install it first — Windows only lists apps it knows are installed. (Note: changing browser defaults works the same way but goes through a separate 'Default browser' button at the top of the settings page.)"},
                ),
                note="Step 2 — Hand off with the precise sequence including the leading dot. WHY: users typing 'pdf' (no dot) in the search box get no results and conclude the page is broken. Spelling out '.pdf' fixes it.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="The system clock is showing the wrong time or wrong time zone.",
        steps=[
            SolutionStep(
                action=ToolCall(name="check_network_status", args={}),
                note="Step 1 — Verify internet connectivity. WHY: Windows time sync (`w32time`) requires internet to reach time.windows.com. Without it, 'Sync now' will fail silently and the clock will keep drifting.",
            ),
            SolutionStep(
                action=ToolCall(name="open_app", args={"app_name": "ms-settings:dateandtime"}),
                note="Step 2 — Open Date & Time settings. WHY: this is the only safe place to change the clock — modifying it via terminal commands risks breaking Kerberos auth and certificate validation across the whole system.",
            ),
            SolutionStep(
                action=ToolCall(name="search_files", args={"query": "date time settings", "max_results": 5}),
                note="FALLBACK — only run if open_app did not launch Settings. WHY: if the ms-settings URI is broken, search_files finds an alternative path to Date & Time settings.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I opened Date & Time settings. Fix in order: (1) make sure 'Set time automatically' AND 'Set time zone automatically' are both ON — these handle 99% of cases, (2) if 'Set time zone automatically' is greyed out, your location services are off; toggle 'Location' under Privacy settings, (3) click 'Sync now' under 'Additional settings' to force a refresh — useful after a long sleep where the clock drifted, (4) if the clock keeps reverting to a wrong time after every boot, the motherboard's CMOS battery is dead — that's a hardware swap, talk to IT. A wrong system time will BREAK HTTPS sites (cert validation fails) and Microsoft 365 sign-in — fixing this is high-priority."},
                ),
                note="Step 3 — Hand off with the priority warning. WHY: users don't realize wrong-time = broken HTTPS = broken everything; framing it as urgent gets the fix done now, not 'later'.",
            ),
        ],
    ),

    SolutionRecord(
        problem_summary="Copy and paste are not working between apps.",
        steps=[
            SolutionStep(
                action=ToolCall(name="list_running_apps", args={}),
                note="Step 1 — Check running apps for clipboard managers. WHY: tools like Ditto, ClipboardFusion, or even some RDP / Citrix clients install a clipboard hook that intercepts and breaks copy/paste. The fix is to close them, not to debug Windows.",
            ),
            SolutionStep(
                action=ToolCall(name="read_clipboard", args={}),
                note="Step 2 — Read the current clipboard. WHY: confirms whether the clipboard itself is dead (read returns empty / fails) vs. paste is broken in a specific destination app (read works fine — problem is the target).",
            ),
            SolutionStep(
                action=ToolCall(name="get_event_log_errors", args={}),
                note="Step 3 — Pull recent errors for rdpclip / svchost. WHY: 'rdpclip' is the clipboard bridge between an RDP session and the host — if it crashed, copy/paste across RDP dies but local works. The log names the failure.",
            ),
            SolutionStep(
                action=ToolCall(
                    name="suggest_solution",
                    args={"suggestion": "I checked running apps and read the clipboard. Fixes by symptom: (1) clipboard COMPLETELY DEAD (nothing copies anywhere): open Task Manager → find 'rdpclip.exe' if present and end it (Windows auto-restarts it); if you have a clipboard manager (Ditto etc.), close it temporarily as a test, (2) Ctrl+C works but Ctrl+V doesn't in ONE specific app: that app may use a non-standard input field — try right-click → Paste; if that works too, the app has captured Ctrl+V for something else, (3) text copies fine but IMAGES / files don't: enable Clipboard History — WIN+V → 'Turn on' — this also lets you paste things you copied 10 minutes ago, (4) RDP / Remote Desktop only: disconnect and reconnect — rdpclip dies under load and only restarts on a fresh session."},
                ),
                note="Step 4 — Hand off branching on symptom. WHY: four distinct failure modes look identical to the user ('paste broken') but need totally different fixes — listing them by symptom prevents wasted effort.",
            ),
        ],
    ),
]

_INSTRUCTIONS_CONTROL = {
    "zoom": (
        "Zoom Workspace Precheck: If the workspace is open, look for a GREEN PILL near the top "
        "('Return to meeting'). If present, you are in a call. Click it and call `focus_window('Zoom Meeting')`. "
        "Otherwise, to fix audio/video, click the GEAR ICON at the TOP-RIGHT of the workspace "
        "(next to avatar/search). Do NOT use Alt+S. "
        "Use `focus_window` to target the 'Zoom Meeting' window for active calls, not just 'Zoom'."
    ),
    "teams": (
        "Teams Audio/Video Fix: Click your avatar at the top-right -> Settings -> Devices. "
        "When using `focus_window` for a live call, target a title containing 'Meeting'. "
        "Skip the main 'Microsoft Teams' window."
    ),
    "discord": (
        "Discord Audio/Video Fix: Click the gear icon at the bottom-left next to the username "
        "-> 'Voice & Video' in the left rail. "
        "For live calls, target the voice/video call panel (title contains the channel name "
        "and a green call indicator)."
    ),
    "slack": (
        "Slack Audio/Video Fix: Click avatar top-right -> Preferences -> Audio & video. "
        "For live calls, target the 'Huddle' window, not the main Slack workspace."
    ),
    "meet": (
        "Google Meet: Target a Chrome window whose title contains 'Meet' AND the meeting code "
        "or attendees. Skip blank 'New Tab' or 'Google' home."
    ),
    "taskbar": (
        "Do NOT click the taskbar to open Task Manager or settings. "
        "In Control Mode, you MUST use the built-in diagnostic tools "
        "(e.g., `list_running_apps`, `get_system_info`, `open_app(app_name='taskmgr')`). "
        "GUI clicks on the taskbar are error-prone and forbidden for these tasks."
    ),
    "typing": (
        "In Control Mode, simply call the `type(text='...')` tool directly after focusing the input field."
    ),
}

_INSTRUCTIONS_GUIDE = {
    "zoom": (
        "Zoom Workspace Precheck: If the workspace is open, look for a GREEN PILL near the top "
        "('Return to meeting'). If present, you are in a call. Highlight it so the user clicks it. "
        "Otherwise, to fix audio/video, highlight the GEAR ICON at the TOP-RIGHT of the workspace "
        "(next to avatar/search). Do NOT use Alt+S. "
        "Since you cannot use focus_window in guide mode, wait for the user to open the meeting window."
    ),
    "teams": (
        "Teams Audio/Video Fix: Highlight the avatar at the top-right -> Settings -> Devices. "
        "Skip the main 'Microsoft Teams' window if they are in a call."
    ),
    "discord": (
        "Discord Audio/Video Fix: Highlight the gear icon at the bottom-left next to the username "
        "-> 'Voice & Video' in the left rail."
    ),
    "slack": (
        "Slack Audio/Video Fix: Highlight the avatar top-right -> Preferences -> Audio & video. "
        "For live calls, highlight the 'Huddle' window."
    ),
    "meet": (
        "Google Meet: Instruct the user to navigate to the Meet tab."
    ),
    "taskbar": (
        "Windows 11 caveat: On Windows 11 with the default centered taskbar, the Start button "
        "is NOT at far-left — it's the leftmost icon in the CENTERED cluster. "
        "To right-click the taskbar (e.g. to open Task Manager): You MUST click an explicitly EMPTY space. "
        "Scan the entire taskbar and aim for the largest contiguous empty block of pixels "
        "(usually far-right near the clock, or far-left). Do NOT click in tiny gaps between app icons near the middle — "
        "you will almost certainly miss and hit an app (like Spotify) instead! "
        "Alternatively, right-click the Start button itself."
    ),
    "typing": (
        "If the user needs to type, follow this TWO-TURN pattern:\n"
        "1. Emit `click(x=..., y=...)` on the input field — the harness shows the spotlight at that spot and BLOCKS until the user clicks.\n"
        "2. On the NEXT turn (after the user clicks and you see the fresh screenshot), emit `type(text='<exact text>')`. "
        "The harness re-renders the spotlight at the SAME spot with a '⌨ Type: <exact text>' bubble next to it.\n"
        "If you emit `type` BEFORE any click, the harness rejects it — type needs a prior click to anchor the bubble."
    ),
}


def main() -> int:
    from server.db.client import _connect
    # Clear existing solutions so we don't get duplicates on re-seed
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM solutions")
        deleted = cur.rowcount
        cur.execute("DELETE FROM app_instructions")
        for topic in _INSTRUCTIONS_CONTROL.keys():
            cur.execute(
                "INSERT INTO app_instructions (topic, control_instruction, guide_instruction) VALUES (%s, %s, %s)",
                (topic, _INSTRUCTIONS_CONTROL[topic], _INSTRUCTIONS_GUIDE.get(topic, ""))
            )
        conn.commit()
    print(f"cleared {deleted} existing solutions")
    print(f"inserted {len(_INSTRUCTIONS_CONTROL)} app instructions")

    for seed in SEEDS:
        rec = record_solution(seed)
        print(f"inserted {rec.id} :: {rec.problem_summary[:60]}")
    print(f"seeded {len(SEEDS)} solutions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
