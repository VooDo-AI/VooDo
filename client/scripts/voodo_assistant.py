import sys
import os
import json
import random
import threading
import time
import websocket  # pip install websocket-client
from dotenv import load_dotenv

from PyQt5.QtWidgets import (QApplication, QWidget, QHBoxLayout, QLabel, QMessageBox,
                             QTextEdit, QVBoxLayout, QPushButton,
                             QScrollArea, QGraphicsDropShadowEffect, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QPropertyAnimation, QEasingCurve, QPoint
from PyQt5.QtGui import QColor
from PyQt5.QtSvg import QSvgWidget

# Load the repo-root .env regardless of where the assistant is launched from.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_REPO_ROOT, ".env"))
# Where the voodo backend lives. Set BACKEND_WS_URL=ws://<backend-host>:7860
# in .env to drive a remote backend; defaults to whatever's on this host.
BACKEND_WS_URL = os.getenv("BACKEND_WS_URL", "ws://localhost:7860")
CONFIG_FILE    = os.path.join(_REPO_ROOT, "voodo_assistant_config.json")
ROBOT_SIZE     = 72

def _make_robot_svg(ry_left=5.8, ry_right=None, thinking=False, glow=1.0):
    """Return SVG string. thinking=True → eyes look upward.

    Bakes the web UI's three CSS-driven effects directly into the SVG so
    QSvgWidget produces a matching look (it doesn't see external CSS):
      • cyan robotHalo drop-shadow on the head group   (matches
        `drop-shadow(0 0 8px rgba(64,216,248,0.25))` on `.robot-logo`)
      • per-eye opacity from `glow` (0.82..1.0 sine — `eyeGlow` keyframe)
        plus a mid-blink opacity dip when an eye is mostly closed
        (mirrors the 0.6 opacity at scaleY(0.07) in `eyeBlink`).
      • per-eye `ry`, with left/right driven on independent timers in
        the widget (matches the 0.08 s blink stagger).
    """
    if ry_right is None:
        ry_right = ry_left

    def _eye_opacity(ry: float) -> float:
        # eyeGlow keyframe: continuous pulse 0.82..1.0 (driven by `glow`).
        # eyeBlink keyframe: at peak-close (ry≈0.3) opacity drops to 0.6.
        base = glow
        if ry < 1.0:
            # Smoothly fade toward 0.6 as the eye closes.
            t = max(0.0, min(1.0, (1.0 - ry) / 0.7))
            return base * (1 - t) + 0.6 * t
        return base

    op_left = _eye_opacity(ry_left)
    op_right = _eye_opacity(ry_right)

    # LED highlight opacity tracks the brighter eye so the face doesn't
    # go dark mid-blink. Averaged ry * glow scales the highlight depth.
    avg_ry = (ry_left + ry_right) / 2
    base_led = max(0.0, (avg_ry - 0.4) / 5.4) * 0.55
    led_op = base_led * glow
    eye_cy  = 19.5 if thinking else 23.0
    led_cy  = 17.0 if thinking else 20.5
    led2_cy = 16.0 if thinking else 19.5
    # eyeBloom std-deviation scales with glow — at peak the halo widens,
    # matching the brightness(1.25) bump in the eyeGlow keyframe.
    bloom_std = 2.2 + 0.6 * (glow - 1.0)
    return f"""<svg viewBox="0 0 40 44" width="{ROBOT_SIZE}" height="{ROBOT_SIZE}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="rHead" cx="38%" cy="28%" r="72%">
      <stop offset="0%" stop-color="#e8eef8"/>
      <stop offset="60%" stop-color="#b8c8df"/>
      <stop offset="100%" stop-color="#7a95b8"/>
    </radialGradient>
    <radialGradient id="rEar" cx="30%" cy="30%" r="70%">
      <stop offset="0%" stop-color="#c5d3e8"/>
      <stop offset="100%" stop-color="#8099b8"/>
    </radialGradient>
    <radialGradient id="rEye" cx="38%" cy="32%" r="62%">
      <stop offset="0%" stop-color="#d0f8ff"/>
      <stop offset="35%" stop-color="#40d8f8"/>
      <stop offset="100%" stop-color="#0088bb"/>
    </radialGradient>
    <filter id="eyeBloom" x="-100%" y="-100%" width="300%" height="300%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="{bloom_std:.2f}" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="headShadow" x="-10%" y="-5%" width="120%" height="120%">
      <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#4a6a9a" flood-opacity="0.35"/>
    </filter>
  </defs>
  <rect x="0"    y="17" width="7"  height="11" rx="3.5" fill="url(#rEar)"/>
  <rect x="1.5"  y="19.5" width="3" height="6" rx="1.5" fill="#1a2030" opacity="0.4"/>
  <rect x="33"   y="17" width="7"  height="11" rx="3.5" fill="url(#rEar)"/>
  <rect x="35.5" y="19.5" width="3" height="6" rx="1.5" fill="#1a2030" opacity="0.4"/>
  <rect x="6" y="5" width="28" height="35" rx="10" fill="url(#rHead)" filter="url(#headShadow)"/>
  <rect x="16" y="2" width="8" height="7" rx="3.5" fill="#b8c8df"/>
  <rect x="18" y="1" width="4" height="4" rx="2"   fill="#9aafc8"/>
  <rect x="9" y="12" width="22" height="22" rx="6" fill="#0d1825"/>
  <rect x="10" y="13" width="10" height="4" rx="2" fill="white" opacity="0.04"/>
  <ellipse cx="15.5" cy="{eye_cy}" rx="4.5" ry="{ry_left}"  opacity="{op_left:.2f}"  fill="url(#rEye)" filter="url(#eyeBloom)"/>
  <ellipse cx="24.5" cy="{eye_cy}" rx="4.5" ry="{ry_right}" opacity="{op_right:.2f}" fill="url(#rEye)" filter="url(#eyeBloom)"/>
  <circle cx="13.8" cy="{led_cy}" r="1.1" fill="white" opacity="{led_op:.2f}"/>
  <circle cx="22.8" cy="{led_cy}" r="1.1" fill="white" opacity="{led_op:.2f}"/>
  <circle cx="15"   cy="{led2_cy}" r="0.5" fill="white" opacity="{led_op*0.55:.2f}"/>
  <circle cx="24"   cy="{led2_cy}" r="0.5" fill="white" opacity="{led_op*0.55:.2f}"/>
</svg>"""


THOUGHT_BUBBLE_SVG = """<svg viewBox="0 0 58 46" width="58" height="46" xmlns="http://www.w3.org/2000/svg">
  <!-- connecting dots (small → big) -->
  <circle cx="3"  cy="40" r="2.5" fill="white" opacity="0.92"/>
  <circle cx="10" cy="33" r="3.8" fill="white" opacity="0.92"/>
  <circle cx="19" cy="26" r="5.2" fill="white" opacity="0.92"/>
  <!-- cloud bubble -->
  <rect x="16" y="2" width="40" height="24" rx="11" fill="white" opacity="0.95"/>
  <!-- thinking dots -->
  <circle cx="28" cy="14" r="3" fill="#7a95b8"/>
  <circle cx="36" cy="14" r="3" fill="#7a95b8"/>
  <circle cx="44" cy="14" r="3" fill="#7a95b8"/>
</svg>"""

SCROLLBAR_CSS = """
    QScrollBar:vertical {
        border: none; background: #c8cfd8;
        width: 8px; border-radius: 4px; margin: 0;
    }
    QScrollBar::handle:vertical {
        background: #5a6a80; border-radius: 4px; min-height: 28px;
    }
    QScrollBar::handle:vertical:hover { background: #3a4a60; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
"""


class WorkerSignals(QObject):
    """Qt-safe pipeline from the WS thread to the UI thread. One signal per
    AgentEvent kind, plus connect/disconnect."""
    connected      = pyqtSignal()
    disconnected   = pyqtSignal()
    status         = pyqtSignal(str)
    thought        = pyqtSignal(str, bool)   # text, stream
    thought_delta  = pyqtSignal(str)         # appended chunk
    tool_call      = pyqtSignal(str, dict)   # name, args
    observation    = pyqtSignal(dict)
    result         = pyqtSignal(bool, str)   # success, summary
    error          = pyqtSignal(str)
    user_prompt    = pyqtSignal(str)         # echo from a peer subscriber
    permission_req = pyqtSignal(str)         # tool name needing kb/mouse approval


class ChatBubble(QWidget):
    def __init__(self, role, text):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)

        lbl = QLabel()
        lbl.setWordWrap(True)
        lbl.setMaximumWidth(300)
        lbl.setTextFormat(Qt.RichText)
        safe = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
        lbl.setText(safe)
        self.lbl = lbl  # exposed so callers can stream updates into the bubble

        if role == "You":
            lbl.setStyleSheet("""
                QLabel { background-color:#2563eb; color:white;
                          border-radius:16px; padding:10px 14px;
                          font-size:13px; font-family:'Segoe UI'; }
            """)
            layout.addStretch()
            layout.addWidget(lbl)
        else:
            color = "#ef4444" if role == "System" else "#374151"
            lbl.setStyleSheet(f"""
                QLabel {{ background-color:#f0f2f5; color:{color};
                           border-radius:16px; padding:10px 14px;
                           font-size:13px; font-family:'Segoe UI'; }}
            """)
            layout.addWidget(lbl)
            layout.addStretch()


class ExpandingTextEdit(QTextEdit):
    """Enter → send, Shift+Enter → newline. Grows up to 3 lines."""
    submit = pyqtSignal()
    MIN_H  = 44
    MAX_H  = 90   # ~3 lines

    def __init__(self):
        super().__init__()
        self.setFixedHeight(self.MIN_H)
        self.document().contentsChanged.connect(self._resize)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            self.submit.emit()
        else:
            super().keyPressEvent(event)

    def _resize(self):
        h = int(self.document().size().height()) + 22
        self.setFixedHeight(max(self.MIN_H, min(h, self.MAX_H)))


class VoodoAssistant(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(540, 480)  # Fixed size so opening history doesn't resize the window

        self.drag_pos     = None
        self.hist_open    = False
        self._hist_cur_h  = 0
        self._hist_prev_h = 0
        self._is_thinking = False
        self._last_prompt: str = ""

        # Per-eye openness + a continuous glow multiplier. Updated by
        # blink frames and the glow-pulse tick respectively; both
        # drive a single _redraw_robot() call so the SVG stays consistent.
        self._eye_ry_left: float = 5.8
        self._eye_ry_right: float = 5.8
        self._eye_glow: float = 1.0
        self._glow_phase: float = 0.0  # 0..1, advances each tick

        self.signals = WorkerSignals()
        # Connection state belongs in a tooltip-style transient, not as the
        # default status line. Show it briefly, then clear so the line is
        # free to mirror the live thought / action stream.
        self.signals.connected.connect(lambda: self._flash_status("✓ connected"))
        self.signals.disconnected.connect(lambda: self._flash_status("⟳ reconnecting…"))
        self.signals.status.connect(self._on_status)
        self.signals.thought.connect(self._on_thought)
        self.signals.thought_delta.connect(self._on_thought_delta)
        self.signals.tool_call.connect(self._on_tool_call)
        self.signals.observation.connect(self._on_observation)
        self.signals.result.connect(self._on_result)
        self.signals.error.connect(self._on_err)
        self.signals.user_prompt.connect(self._on_peer_user_prompt)
        self.signals.permission_req.connect(self._on_permission_request)

        self._build_ui()
        self._load_pos()
        # Three independent loops that together mirror the web-UI
        # robot animation:
        #   • _schedule_blink: per-eye blink, right eye staggered ~80ms
        #     after left (matches eyeBlink 0.08s offset in style.css)
        #   • _float_anim: subtle Y bob, 4s sinusoidal (matches robotFloat)
        #   • _glow_timer: continuous eye-glow pulse, 2.5s cycle (eyeGlow)
        self._schedule_blink()
        self._start_float_anim()
        self._start_glow_pulse()

        # Persistent WebSocket to the voodo backend. Lives in a daemon thread.
        self._ws: websocket.WebSocketApp | None = None
        self._ws_lock = threading.Lock()
        self._streaming_thought: str = ""
        self._streaming_label = None  # QLabel currently receiving thought_delta
        threading.Thread(target=self._ws_thread, daemon=True).start()

        self._sim_steps = []
        self._sim_idx   = 0
        self._sim_timer = QTimer(self)
        self._sim_timer.timeout.connect(self._next_sim)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 10)
        root.setSpacing(6)
        root.addStretch(1)  # Push everything to the bottom

        # ── History panel (in layout) ─────────────────────────────────────
        self.hist_panel = QWidget()
        self.hist_panel.setMaximumHeight(0)
        self.hist_panel.setStyleSheet("""
            QWidget { background-color:white; border-radius:20px; }
        """)
        shade = QGraphicsDropShadowEffect()
        shade.setBlurRadius(28); shade.setOffset(0, -6); shade.setColor(QColor(0,0,0,90))
        self.hist_panel.setGraphicsEffect(shade)

        hp_layout = QVBoxLayout(self.hist_panel)
        hp_layout.setContentsMargins(10, 10, 10, 10)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(240)
        self.scroll.setMaximumHeight(320)
        self.scroll.setStyleSheet("QScrollArea{border:none;background:white;}" + SCROLLBAR_CSS)

        self.bubbles_w = QWidget()
        self.bubbles_w.setStyleSheet("background:white;")
        self.bubbles_l = QVBoxLayout(self.bubbles_w)
        self.bubbles_l.setContentsMargins(4,4,4,4)
        self.bubbles_l.setSpacing(6)
        self.bubbles_l.addStretch()

        self.scroll.setWidget(self.bubbles_w)
        hp_layout.addWidget(self.scroll)
        root.addWidget(self.hist_panel)

        # Animate maximumHeight; also compensate window Y each frame
        self._hist_anim = QPropertyAnimation(self.hist_panel, b"maximumHeight")
        self._hist_anim.setDuration(320)
        self._hist_anim.setEasingCurve(QEasingCurve.OutCubic)

        # ── Bottom bar ────────────────────────────────────────────────────
        bar = QHBoxLayout()
        bar.setContentsMargins(0,0,0,0)
        bar.setSpacing(8)

        # Robot (SVG) + thought bubble, both children of robot_box
        BOX_W = ROBOT_SIZE
        self.robot_box = QWidget()
        self.robot_box.setFixedSize(BOX_W, ROBOT_SIZE + 35)
        self.robot_box.setAttribute(Qt.WA_TranslucentBackground)

        self.robot_lbl = QSvgWidget(self.robot_box)
        self.robot_lbl.setFixedSize(ROBOT_SIZE, ROBOT_SIZE)
        self.robot_lbl.move(0, 30)
        self.robot_lbl.setAttribute(Qt.WA_TranslucentBackground)
        # Cyan halo, equivalent to the `.robot-logo` CSS drop-shadow:
        #   drop-shadow(0 0 8px rgba(64, 216, 248, 0.25))
        # QGraphicsDropShadowEffect is the Qt-native path here; doing it
        # via SVG filter primitives doesn't render reliably in QSvgWidget.
        self._robot_halo = QGraphicsDropShadowEffect(self.robot_lbl)
        self._robot_halo.setBlurRadius(16)
        self._robot_halo.setOffset(0, 0)
        self._robot_halo.setColor(QColor(64, 216, 248, 90))  # 0.35 alpha
        self.robot_lbl.setGraphicsEffect(self._robot_halo)
        self.robot_lbl.load(bytearray(_make_robot_svg(), 'utf-8'))

        # Thought bubble — upper-right of the robot, hidden by default
        self.thought_lbl = QSvgWidget(self.robot_box)
        self.thought_lbl.setFixedSize(58, 46)
        self.thought_lbl.move(ROBOT_SIZE - 25, 15)
        self.thought_lbl.setAttribute(Qt.WA_TranslucentBackground)
        self.thought_lbl.load(bytearray(THOUGHT_BUBBLE_SVG, 'utf-8'))
        self.thought_lbl.hide()

        self._thought_anim = QPropertyAnimation(self.thought_lbl, b"pos")
        self._thought_anim.setDuration(1200)
        self._thought_anim.setLoopCount(-1)
        self._thought_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._thought_anim.setStartValue(QPoint(ROBOT_SIZE - 25, 15))
        self._thought_anim.setEndValue(QPoint(ROBOT_SIZE - 25, 5))

        # Right column
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0,0,0,0)
        right_col.setSpacing(4)

        # Status label — above the input row. Wraps to a second line
        # so streamed thought tails and tool-call argument lists stay
        # readable instead of getting clipped at a single-line width.
        self.status_lbl = QLabel("")
        self.status_lbl.setVisible(False)
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setMaximumWidth(380)
        self.status_lbl.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        self.status_lbl.setStyleSheet("""
            QLabel {
                color: #111;
                font-size: 13px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
                background: white;
                border-radius: 12px;
                padding: 4px 12px;
            }
        """)
        right_col.addWidget(self.status_lbl)

        # Input row (input + history btn + close btn)
        in_row = QHBoxLayout()
        in_row.setContentsMargins(0,0,0,0)
        in_row.setSpacing(8)

        self.input = ExpandingTextEdit()
        self.input.setPlaceholderText("voo, what can I help you do?")
        self.input.setFixedWidth(280)
        self.input.setMinimumWidth(0)
        self.input.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input.setStyleSheet("""
            QTextEdit {
                background-color:white; color:#222;
                border-radius:14px; padding:8px 12px;
                font-size:15px; font-family:'Segoe UI',Arial,sans-serif;
                border:1.5px solid rgba(255,255,255,0.85);
            }
            QTextEdit:focus    { border:1.5px solid #5c9eff; }
            /* Locked while the agent is running. Faint red border + dimmed
               text makes it obvious the input isn't accepting new prompts —
               use Stop or Pause first. */
            QTextEdit:disabled { background:#f0e8e8; color:#7a6a6a;
                                 border:1.5px solid #f0c0c0; }
        """)
        self.input.submit.connect(self.send_prompt)
        self.input.textChanged.connect(self._clear_status_on_type)

        ishadow = QGraphicsDropShadowEffect()
        ishadow.setBlurRadius(18); ishadow.setOffset(0,4); ishadow.setColor(QColor(0,0,0,55))
        self.input.setGraphicsEffect(ishadow)

        self._input_anim = QPropertyAnimation(self.input, b"maximumWidth")
        self._input_anim.setDuration(350)
        self._input_anim.setEasingCurve(QEasingCurve.InOutCubic)

        # Mode toggle: "control" (default, voodo acts) vs "guide" (voodo only
        # highlights where to click). Click cycles between the two; tooltip
        # and emoji show the current mode.
        self.mode = "control"
        self.mode_btn = QPushButton("🤖")
        self.mode_btn.setFixedSize(44, 44)
        self.mode_btn.setToolTip("Click: Control My Computer (voodo acts)\nClick again: Show Me What to Click")
        self.mode_btn.setStyleSheet("""
            QPushButton {
                background: white; color: #111;
                border-radius: 22px; font-size: 20px; border: none;
            }
            QPushButton:hover { background: #e8edf5; }
        """)
        self.mode_btn.clicked.connect(self._toggle_mode)

        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setFixedSize(44, 44)
        self.stop_btn.setToolTip("Stop")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background: #fde8e8; color: #c0392b;
                border-radius: 22px; font-size: 20px; border: none;
            }
            QPushButton:hover { background: #fad1d1; }
        """)
        self.stop_btn.hide()
        self.stop_btn.clicked.connect(self._on_stop_clicked)

        # Pause / resume. Glyph and tooltip flip when _paused toggles.
        # Stays hidden until a session is running.
        self._paused = False
        self.pause_btn = QPushButton("⏸")
        self.pause_btn.setFixedSize(44, 44)
        self.pause_btn.setToolTip("Pause — interrupt the agent now")
        self.pause_btn.setStyleSheet("""
            QPushButton {
                background: #fff7e0; color: #b07000;
                border-radius: 22px; font-size: 20px; border: none;
            }
            QPushButton:hover { background: #ffe9b3; }
        """)
        self.pause_btn.hide()
        self.pause_btn.clicked.connect(self._on_pause_clicked)

        self.hist_btn = QPushButton("💬")
        self.hist_btn.setFixedSize(44, 44)
        self.hist_btn.setToolTip("Open the full chat in your browser")
        self.hist_btn.setStyleSheet("""
            QPushButton {
                background: white; color: #111;
                border-radius: 22px; font-size: 20px; border: none;
            }
            QPushButton:hover { background: #e8edf5; }
        """)
        self.hist_btn.clicked.connect(self._open_browser_chat)

        # Close button
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(44, 44)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: white; color: #111;
                border-radius: 22px; font-size: 18px; font-weight: bold; border: none;
            }
            QPushButton:hover { background: #fde8e8; color: #c0392b; }
        """)
        self.close_btn.clicked.connect(self._on_close_clicked)

        in_row.addWidget(self.input)
        in_row.addWidget(self.pause_btn, 0, Qt.AlignBottom)
        in_row.addWidget(self.stop_btn, 0, Qt.AlignBottom)
        in_row.addWidget(self.mode_btn, 0, Qt.AlignBottom)
        in_row.addWidget(self.hist_btn, 0, Qt.AlignBottom)
        in_row.addWidget(self.close_btn, 0, Qt.AlignBottom)
        right_col.addLayout(in_row)

        bar.addWidget(self.robot_box, 0, Qt.AlignBottom)
        bar.addLayout(right_col)
        bar.addStretch(1)  # Push everything to the left so they don't drift apart
        root.addLayout(bar)

    # ── Position ──────────────────────────────────────────────────────────────

    def _load_pos(self):
        try:
            if os.path.exists(CONFIG_FILE):
                d = json.load(open(CONFIG_FILE))
                self.move(d['x'], d['y']); return
        except Exception: pass
        self.adjustSize()
        sc = QApplication.desktop().availableGeometry()
        self.move(20, sc.height() - self.height() - 20)

    def _save_pos(self):
        try: json.dump({'x': self.x(), 'y': self.y()}, open(CONFIG_FILE,'w'))
        except Exception: pass

    # ── Drag ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            child = self.childAt(e.pos())
            if not isinstance(child, (QPushButton, QTextEdit)):
                self.drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self.drag_pos:
            self.move(e.globalPos() - self.drag_pos)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.drag_pos:
            self.drag_pos = None; self._save_pos()

    # ── History toggle (animated) ─────────────────────────────────────────────

    def _toggle_history(self):
        self.hist_open = not self.hist_open
        target = (self.scroll.minimumHeight() + 44) if self.hist_open else 0
        self._hist_anim.stop()
        self._hist_prev_h = self.hist_panel.maximumHeight()
        self._hist_anim.setStartValue(self._hist_prev_h)
        self._hist_anim.setEndValue(target)
        self._hist_anim.start()

    def _add_bubble(self, role, text):
        # Remove trailing stretch, add bubble, re-add stretch.
        # Returns the inner QLabel so callers can mutate it (used for streaming
        # thought_delta into a bubble that was added empty).
        n = self.bubbles_l.count()
        if n > 0 and self.bubbles_l.itemAt(n-1).spacerItem():
            self.bubbles_l.removeItem(self.bubbles_l.itemAt(n-1))
        bubble = ChatBubble(role, text)
        self.bubbles_l.addWidget(bubble)
        self.bubbles_l.addStretch()
        QTimer.singleShot(60, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))
        return bubble.lbl

    # ── Status ────────────────────────────────────────────────────────────────

    def _set_status(self, txt):
        self.status_lbl.setText(txt)
        self.status_lbl.setVisible(bool(txt))

    def _flash_status(self, txt: str, hold_ms: int = 1500):
        """Show a status line, then auto-clear after `hold_ms`. Used for
        ephemeral things like connect/disconnect that shouldn't crowd out
        the live thought stream."""
        self._set_status(txt)
        QTimer.singleShot(hold_ms, lambda t=txt: (
            self.status_lbl.text() == t and self._set_status("")
        ))

    def _clear_status_on_type(self):
        if self.status_lbl.text():
            self.status_lbl.setText("")
            self.status_lbl.setVisible(False)

    def _next_sim(self):
        if self._sim_idx < len(self._sim_steps):
            self._set_status(self._sim_steps[self._sim_idx])
            self._sim_idx += 1
        else:
            self._sim_timer.stop()

    # ── Blink + thinking animation ────────────────────────────────────────────

    def _redraw_robot(self):
        """Single rendering chokepoint — blink frames + glow ticks both
        mutate per-eye state, then call this to re-emit the SVG."""
        self.robot_lbl.load(bytearray(_make_robot_svg(
            ry_left=self._eye_ry_left,
            ry_right=self._eye_ry_right,
            thinking=self._is_thinking,
            glow=self._eye_glow,
        ), "utf-8"))

    def _set_left_eye(self, ry: float):
        self._eye_ry_left = ry
        self._redraw_robot()

    def _set_right_eye(self, ry: float):
        self._eye_ry_right = ry
        self._redraw_robot()

    # ── Eye blink (per-eye, staggered) ────────────────────────────────────────

    def _schedule_blink(self):
        delay = int(random.uniform(2500, 5000))
        QTimer.singleShot(delay, self._do_blink)

    def _do_blink(self):
        if self._is_thinking:
            self._schedule_blink()
            return
        # Left eye closes and reopens; right eye does the same ~80ms later.
        frames = [(0, 5.8), (70, 1.2), (130, 0.3), (200, 1.2), (260, 5.8)]
        for delay, ry in frames:
            QTimer.singleShot(delay, lambda r=ry: self._set_left_eye(r))
        STAGGER = 80
        for delay, ry in frames:
            QTimer.singleShot(delay + STAGGER, lambda r=ry: self._set_right_eye(r))
        QTimer.singleShot(260 + STAGGER, self._schedule_blink)

    # ── Float bob (subtle Y-axis) ─────────────────────────────────────────────

    def _start_float_anim(self):
        """4s sinusoidal Y bob between (0, 28) and (0, 32). 2px amplitude
        keeps it subliminal, matching the web UI's robotFloat keyframe."""
        from PyQt5.QtCore import QPoint
        self._float_anim = QPropertyAnimation(self.robot_lbl, b"pos")
        self._float_anim.setDuration(4000)
        self._float_anim.setLoopCount(-1)
        self._float_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._float_anim.setKeyValueAt(0.0, QPoint(0, 30))
        self._float_anim.setKeyValueAt(0.5, QPoint(0, 28))
        self._float_anim.setKeyValueAt(1.0, QPoint(0, 30))
        self._float_anim.start()

    # ── Eye glow pulse (continuous) ───────────────────────────────────────────

    def _start_glow_pulse(self):
        """Drive `self._eye_glow` along a 2.5s sin wave (0.82 → 1.0)
        at ~12 fps. Same shape as the web UI's eyeGlow keyframe."""
        self._glow_timer = QTimer(self)
        self._glow_timer.setInterval(80)  # ~12.5 fps — smooth enough, cheap
        self._glow_timer.timeout.connect(self._tick_glow)
        self._glow_timer.start()

    def _tick_glow(self):
        import math
        # 2.5s cycle, advance phase by interval / period each tick.
        self._glow_phase = (self._glow_phase + 0.08 / 2.5) % 1.0
        # Sin curve 0..1 → glow 0.82..1.0 (web UI uses 0.82 min, 1.0 max).
        s = (math.sin(self._glow_phase * 2 * math.pi - math.pi / 2) + 1) / 2
        self._eye_glow = 0.82 + 0.18 * s
        self._redraw_robot()

    def _set_thinking(self, thinking: bool):
        self._is_thinking = thinking
        # Thinking = squinted eyes (both eyes equal — no stagger while
        # the agent is busy; the float + glow loops keep running).
        ry = 2.0 if thinking else 5.8
        self._eye_ry_left = ry
        self._eye_ry_right = ry
        self._redraw_robot()

        self._input_anim.stop()
        if thinking:
            # Force the chat history panel closed during a session — the
            # status line shows the live state, the bubble history is
            # noisy while events stream in. User can re-open with 💬.
            if self.hist_open:
                self._toggle_history()
            self.robot_box.raise_()
            self.thought_lbl.show()
            self.thought_lbl.raise_()
            self._thought_anim.start()

            # Fold the input entirely while the agent is running —
            # animate maximumWidth down to 0 then hide it. Status line +
            # robot + stop/pause buttons remain visible as the surface.
            self._input_anim.setStartValue(self.input.maximumWidth() or 280)
            self._input_anim.setEndValue(0)
            try:
                self._input_anim.finished.disconnect()
            except TypeError:
                pass
            self._input_anim.finished.connect(self.input.hide)
            self._input_anim.start()

            self.mode_btn.hide()
            self.stop_btn.show()
            # Reset pause UI to a fresh "Pause" state for every new run.
            self._paused = False
            self.pause_btn.setText("⏸")
            self.pause_btn.setToolTip("Pause — interrupt the agent now")
            self.pause_btn.show()
        else:
            self.thought_lbl.hide()
            self._thought_anim.stop()

            self.input.clear()
            self.input.setPlaceholderText("voo, what can I help you do?")
            # Unfold the input: show first, then animate width back.
            self.input.show()
            self._input_anim.setStartValue(0)
            self._input_anim.setEndValue(280)
            try:
                self._input_anim.finished.disconnect()
            except TypeError:
                pass
            self._input_anim.start()

            self.stop_btn.hide()
            self.pause_btn.hide()
            self.mode_btn.show()

    # ── Send prompt ───────────────────────────────────────────────────────────

    def _toggle_mode(self):
        if self.mode == "control":
            self.mode = "guide"
            self.mode_btn.setText("👆")  # finger = "show me what to click"
            self.mode_btn.setToolTip("Mode: Show Me What to Click\nClick to switch back to Control My Computer")
            self._set_status("mode: Show Me What to Click")
        else:
            self.mode = "control"
            self.mode_btn.setText("🤖")
            self.mode_btn.setToolTip("Mode: Control My Computer (voodo acts)\nClick to switch to Show Me What to Click")
            self._set_status("mode: Control My Computer")

    def _on_stop_clicked(self):
        # Tell the backend to cancel the in-flight run; the agent loop
        # observes the cancel Event and emits its own `result` event,
        # which flows back through _on_result. We do NOT fake a local
        # result here — that's lossy if the agent already finished a
        # tool call we'd like reflected in the DB.
        msg = json.dumps({"type": "stop"})
        with self._ws_lock:
            if self._ws is not None:
                try:
                    self._ws.send(msg)
                except Exception:  # noqa: BLE001
                    pass
        # Show immediate UI feedback while we wait for the server result.
        self._set_status("⏹ stopping…")

    def _open_browser_chat(self):
        """Open the full chat UI in the default browser. The chat lives
        at the HTTP equivalent of BACKEND_WS_URL (we just swap the ws[s]
        scheme for http[s] and keep host:port)."""
        import webbrowser
        u = BACKEND_WS_URL.rstrip("/")
        if u.startswith("wss://"):
            u = "https://" + u[len("wss://"):]
        elif u.startswith("ws://"):
            u = "http://" + u[len("ws://"):]
        webbrowser.open(u + "/")

    def _on_close_clicked(self):
        """Closing the widget pauses the in-flight chat (the backend also
        auto-pauses on widget WS-disconnect; this is the cooperative
        path that fires before we drop the socket)."""
        try:
            with self._ws_lock:
                if self._ws is not None:
                    self._ws.send(json.dumps({"type": "pause"}))
        except Exception:  # noqa: BLE001
            pass
        QApplication.quit()

    def _on_pause_clicked(self):
        """Toggle pause / resume. Sends {pause|resume} to the backend.
        The status line update on round-trip will arrive via _on_status."""
        self._paused = not self._paused
        msg_type = "pause" if self._paused else "resume"
        with self._ws_lock:
            if self._ws is None:
                self._paused = not self._paused   # revert toggle
                return
            try:
                self._ws.send(json.dumps({"type": msg_type}))
            except Exception:  # noqa: BLE001
                self._paused = not self._paused
                return
        if self._paused:
            self.pause_btn.setText("▶")
            self.pause_btn.setToolTip("Resume the agent")
            self._set_status("⏸ paused — click ▶ to resume")
        else:
            self.pause_btn.setText("⏸")
            self.pause_btn.setToolTip("Pause — interrupt the agent now")
            self._set_status("▶ resuming…")

    def send_prompt(self):
        prompt = self.input.toPlainText().strip()
        if not prompt: return

        self._last_prompt = prompt
        self._add_bubble("You", prompt)
        self.input.setPlainText(prompt)
        self.input.setEnabled(False)
        self._streaming_thought = ""
        self._streaming_label = None
        self._set_status("Thinking…")
        self._set_thinking(True)

        msg = json.dumps({"type": "message", "text": prompt, "mode": self.mode})
        with self._ws_lock:
            if self._ws is None:
                self._on_err("Not connected to voodo backend yet — try again in a sec.")
                return
            try:
                self._ws.send(msg)
            except Exception as e:  # noqa: BLE001
                self._on_err(f"Send failed: {e}")

    # ── WebSocket plumbing ───────────────────────────────────────────────────

    def _ws_thread(self):
        """Maintain a persistent WebSocket connection to the backend /ws.
        Reconnect with backoff on disconnect. Lives for the app's lifetime."""
        backoff = 1.0
        while True:
            ws_url = f"{BACKEND_WS_URL.rstrip('/')}/ws"
            try:
                def _on_open(_ws):
                    # Identify ourselves so the backend can distinguish
                    # widget vs browser subscribers (used to auto-pause
                    # the in-flight run when the widget closes).
                    try:
                        _ws.send(json.dumps({"type": "hello", "client": "widget"}))
                    except Exception:  # noqa: BLE001
                        pass
                    self.signals.connected.emit()

                self._ws = websocket.WebSocketApp(
                    ws_url,
                    on_open=_on_open,
                    on_message=lambda _ws, raw: self._on_ws_msg(raw),
                    on_error=lambda _ws, err: self.signals.error.emit(str(err)),
                    on_close=lambda _ws, *_a: self.signals.disconnected.emit(),
                )
                self._ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:  # noqa: BLE001
                self.signals.error.emit(f"WS error: {e}")
            with self._ws_lock:
                self._ws = None
            time.sleep(backoff)
            backoff = min(backoff * 1.5, 10.0)

    def _on_ws_msg(self, raw: str):
        try:
            evt = json.loads(raw)
        except json.JSONDecodeError:
            return
        kind = evt.get("kind", "")
        payload = evt.get("payload", {}) or {}
        # The backend echoes the originating user prompt as a status
        # event with `user_prompt` set. Intercept that to render a "You"
        # bubble, mirroring what send_prompt() would have done locally.
        if kind == "status" and "user_prompt" in payload:
            self.signals.user_prompt.emit(str(payload.get("user_prompt", "")))
            return
        # Keyboard/mouse permission gate from the agent. Surface as a
        # modal Allow/Deny dialog inside the widget — after open_assistant
        # minimizes everything, the widget is the only thing the user
        # can interact with, so the browser-side popup is invisible.
        if kind == "status" and payload.get("permission") == "keyboard":
            self.signals.permission_req.emit(str(payload.get("tool", "keyboard/mouse")))
            return
        sig_map = {
            "status":        lambda p: self.signals.status.emit(p.get("msg", "")),
            "thought":       lambda p: self.signals.thought.emit(p.get("text", ""), bool(p.get("stream"))),
            "thought_delta": lambda p: self.signals.thought_delta.emit(p.get("text", "")),
            "tool_call":     lambda p: self.signals.tool_call.emit(p.get("name", ""), p.get("args", {}) or {}),
            "observation":   lambda p: self.signals.observation.emit(p),
            "result":        lambda p: self.signals.result.emit(bool(p.get("success")), p.get("summary", "")),
            "error":         lambda p: self.signals.error.emit(p.get("msg", "")),
        }
        fn = sig_map.get(kind)
        if fn: fn(payload)

    # ── Event handlers (run on Qt thread via signals) ────────────────────────

    def _on_status(self, msg: str):
        # Backend `status` events double as pause-state confirmations —
        # keep the pause_btn glyph in sync with what the server thinks.
        low = msg.lower()
        if "paused" in low:
            self._paused = True
            self.pause_btn.setText("▶")
            self.pause_btn.setToolTip("Resume the agent")
        elif "resuming" in low:
            self._paused = False
            self.pause_btn.setText("⏸")
            self.pause_btn.setToolTip("Pause — interrupt the agent now")
        # Cap at ~140 — fits comfortably in the 2-line wrapped status box.
        self._set_status(msg[:140])

    def _ensure_session_ui(self):
        """A session is in progress somewhere (maybe started in the browser).
        Flip the widget into 'thinking' UI if we weren't already — shows
        the Stop/Pause buttons and red-bordered locked input. The status
        line mirrors the live thought / action so the user sees what's
        happening; the chat history panel stays collapsed (user can open
        it manually via 💬 if they want the full transcript)."""
        if self._is_thinking:
            return
        self.input.setEnabled(False)
        self._streaming_thought = ""
        self._streaming_label = None
        self._set_thinking(True)

    def _on_permission_request(self, tool: str):
        """Modal Allow/Deny dialog for keyboard/mouse approval. The
        widget stays on top via Qt.WindowStaysOnTopHint so this is
        visible even when MinimizeAll just minimized everything else.
        """
        # Guard: ignore duplicate requests if a dialog is already open.
        if getattr(self, "_perm_dialog_open", False):
            return
        self._perm_dialog_open = True
        try:
            box = QMessageBox(self)
            box.setWindowFlags(box.windowFlags() | Qt.WindowStaysOnTopHint)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("voodo — permission required")
            box.setText("🖱️⌨️  Allow voodo to use the keyboard and mouse?")
            box.setInformativeText(
                f"The agent wants to call <b>{tool}</b>.\n\n"
                "Allowing covers the rest of this session. "
                "Deny stops the agent."
            )
            allow_btn = box.addButton("Allow", QMessageBox.AcceptRole)
            box.addButton("Deny && Stop", QMessageBox.RejectRole)
            box.setDefaultButton(allow_btn)
            box.exec_()
            approved = box.clickedButton() is allow_btn

            msg_type = "approve_keyboard" if approved else "stop"
            with self._ws_lock:
                if self._ws is not None:
                    try:
                        self._ws.send(json.dumps({"type": msg_type}))
                    except Exception:  # noqa: BLE001
                        pass
            self._set_status(
                "✓ keyboard/mouse approved" if approved
                else "⏹ stopped — keyboard/mouse denied"
            )
        finally:
            self._perm_dialog_open = False

    def _on_peer_user_prompt(self, prompt: str):
        """A prompt was submitted from another subscriber (e.g. the
        browser chat). Render it as a "You" bubble and enter session UI."""
        if not prompt:
            return
        self._last_prompt = prompt
        self._add_bubble("You", prompt)
        self._ensure_session_ui()
        self._set_status("Thinking…")

    def _on_thought(self, text: str, stream: bool):
        self._ensure_session_ui()
        if stream:
            self._streaming_thought = ""
            # Add an empty bubble that thought_delta will fill in.
            self._streaming_label = self._add_bubble("Voodo", "💭 ")
        else:
            self._streaming_label = None
            self._add_bubble("Voodo", f"💭 {text}")

    def _on_thought_delta(self, chunk: str):
        self._ensure_session_ui()
        if not self._streaming_label:
            # Late join — create a bubble on the fly so deltas have somewhere
            # to land (happens when the widget connects mid-session).
            self._streaming_label = self._add_bubble("Voodo", "💭 ")
        self._streaming_thought += chunk
        safe = self._streaming_thought.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
        self._streaming_label.setText(f"💭 {safe}")
        # Mirror the live tail of the thought into the always-visible status
        # line so the popup feels alive with the history collapsed. Take
        # the last sentence/clause; the label wraps to 2 lines, so ~140
        # chars actually fit on screen.
        tail = self._streaming_thought.replace("\n", " ").strip()
        tail = tail.rsplit(". ", 1)[-1]
        if len(tail) > 140:
            tail = "…" + tail[-139:]
        self._set_status(f"💭 {tail}")

    def _on_tool_call(self, name: str, args: dict):
        self._ensure_session_ui()
        # Compact one-liner so the bubble stack stays readable.
        arg_str = json.dumps(args)[:120]
        self._add_bubble("Voodo", f"▶ {name}({arg_str})")
        # Tool calls override the thought tail in the status line — what the
        # agent is *doing* is more important than what it was thinking.
        # Status wraps to 2 lines, so 120 chars of args fit comfortably.
        status_arg = json.dumps(args)[:120]
        self._set_status(f"▶ {name}({status_arg})")

    def _on_observation(self, payload: dict):
        if payload.get("ok") is False:
            self._set_status(f"× {str(payload.get('error',''))[:60]}")
        # Don't bubble observations — too noisy. Status line only.

    def _on_result(self, success: bool, summary: str):
        self._set_thinking(False)
        self._set_status("✨ Done" if success else "× Failed")
        role = "Voodo" if success else "System"
        prefix = "✓ " if success else "✗ "
        self._add_bubble(role, f"{prefix}{summary}")
        self._add_feedback_row(success, summary)
        self._unlock()

    def _add_feedback_row(self, success: bool, summary: str):
        """Append a 👍/👎 row to the bubble list. Click sends a
        {"type":"feedback"} WS frame to the backend; the row then
        collapses to a "Thanks!" confirmation so it can't be
        double-submitted."""
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 0, 8, 0)
        rl.setSpacing(8)
        ask = QLabel("Was this helpful?")
        ask.setStyleSheet("color:#5a6a80; font-size:11px; font-family:'Segoe UI';")
        rl.addWidget(ask)

        def _make_btn(glyph: str, rating: str) -> QPushButton:
            b = QPushButton(glyph)
            b.setFixedSize(34, 28)
            b.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.85); color:#111;
                    border-radius: 14px; font-size: 14px; border: none;
                }
                QPushButton:hover { background: #e8edf5; }
            """)
            b.clicked.connect(lambda _=False, r=rating: self._send_feedback(row, r, success, summary))
            return b

        rl.addWidget(_make_btn("👍", "like"))
        rl.addWidget(_make_btn("👎", "dislike"))
        rl.addStretch()

        # Insert above the bottom stretch like _add_bubble does.
        n = self.bubbles_l.count()
        if n > 0 and self.bubbles_l.itemAt(n - 1).spacerItem():
            self.bubbles_l.removeItem(self.bubbles_l.itemAt(n - 1))
        self.bubbles_l.addWidget(row)
        self.bubbles_l.addStretch()
        QTimer.singleShot(60, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def _send_feedback(self, row: "QWidget", rating: str, success: bool, summary: str):
        with self._ws_lock:
            if self._ws is not None:
                try:
                    self._ws.send(json.dumps({
                        "type": "feedback", "rating": rating,
                        "success": success, "summary": summary,
                    }))
                except Exception:  # noqa: BLE001
                    pass
        # Replace the row content with a thanks label so it can't be re-submitted.
        layout = row.layout()
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        msg = "Thanks for the 👍" if rating == "like" else "Thanks — we'll do better 👎"
        thanks = QLabel(msg)
        thanks.setStyleSheet("color:#374151; font-size:11px; font-style:italic; font-family:'Segoe UI';")
        layout.addWidget(thanks)
        layout.addStretch()

    def _on_err(self, msg: str):
        self._set_thinking(False)
        self._set_status(f"❌ {msg[:70]}")
        self._add_bubble("System", f"Error: {msg}")
        self._unlock()

    def _unlock(self):
        self.input.setEnabled(True)
        self.input.setFocus()


def _crash_to_messagebox(exc_type, exc, tb):
    """Show a native error dialog instead of dying silently when launched
    via pythonw.exe. Logs to %TEMP%\\voodo_assistant.log."""
    import traceback, tempfile
    msg = "".join(traceback.format_exception(exc_type, exc, tb))
    log = os.path.join(tempfile.gettempdir(), "voodo_assistant.log")
    try:
        with open(log, "a", encoding="utf-8") as f:
            f.write("\n=== crash ===\n" + msg)
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, msg[:1500] + f"\n\nFull log: {log}",
            "voodo assistant — error", 0x10,  # MB_ICONERROR
        )
    except Exception:
        sys.__excepthook__(exc_type, exc, tb)

sys.excepthook = _crash_to_messagebox


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    try:
        import ctypes; ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass

    app = QApplication(sys.argv)
    w = VoodoAssistant()
    w.show()
    sys.exit(app.exec_())
