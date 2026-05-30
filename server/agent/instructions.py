"""Specific instructions for apps and UI mechanics.

These are retrieved dynamically via the `get_specific_instructions` tool
so we don't bloat the main system prompt with instructions for every edge case.
The instructions are tailored to the current operating mode (control or guide).
"""

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

def get_instructions(topic: str, mode: str = "control") -> str:
    t = topic.lower().strip()
    instructions = _INSTRUCTIONS_GUIDE if mode == "guide" else _INSTRUCTIONS_CONTROL
    
    for key, text in instructions.items():
        if key in t:
            return text
    return "No specific instructions for this topic. Proceed with standard troubleshooting."
