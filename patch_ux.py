import sys
import re

path = r'client/scripts/voodo_assistant.py'
with open(path, encoding='utf-8') as f:
    text = f.read()

# 1. Replace ChatBubble
old_chatbubble = '''class ChatBubble(QWidget):
    def __init__(self, role, text):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)

        lbl = QLabel()
        lbl.setWordWrap(True)
        lbl.setMaximumWidth(300)
        lbl.setTextFormat(Qt.RichText)
        safe = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\\n', '<br>')
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
            layout.addStretch()'''

new_chatbubble = '''class ChatBubble(QWidget):
    def __init__(self, role, text):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)

        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        self.lbl.setMaximumWidth(300)
        self.lbl.setTextFormat(Qt.RichText)
        
        self.full_text = ""
        self.is_expanded = False
        self.role = role

        if role == "You":
            self.lbl.setStyleSheet("""
                QLabel { background-color:#2563eb; color:white;
                          border-radius:16px; padding:10px 14px;
                          font-size:13px; font-family:'Segoe UI'; }
            """)
            layout.addStretch()
            layout.addWidget(self.lbl)
        else:
            color = "#ef4444" if role == "System" else "#374151"
            self.lbl.setStyleSheet(f"""
                QLabel {{ background-color:#f0f2f5; color:{color};
                           border-radius:16px; padding:10px 14px;
                           font-size:13px; font-family:'Segoe UI'; }}
            """)
            layout.addWidget(self.lbl)
            layout.addStretch()

        self.eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.eff)
        self.anim = QPropertyAnimation(self.eff, b"opacity")
        self.anim.setDuration(300)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        
        self.update_text(text)

    def update_text(self, text):
        self.full_text = text
        if len(text) > 120 and not self.is_expanded and self.role != "You":
            truncated = text[:117]
            safe = truncated.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\\n', '<br>')
            safe += '... <a href="#expand" style="color:#0088bb; text-decoration:none;">(more)</a>'
            try: self.lbl.linkActivated.disconnect()
            except TypeError: pass
            self.lbl.linkActivated.connect(self._expand)
        else:
            safe = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\\n', '<br>')
            
        self.lbl.setText(safe)

    def _expand(self, link):
        self.is_expanded = True
        self.update_text(self.full_text)'''

if old_chatbubble in text:
    text = text.replace(old_chatbubble, new_chatbubble)
    print("ChatBubble patched.")
else:
    print("Could not find ChatBubble to patch!")


# 2. Modify _add_bubble to return bubble
old_add_bubble = '''    def _add_bubble(self, role, text):
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
        return bubble.lbl'''

new_add_bubble = '''    def _add_bubble(self, role, text):
        n = self.bubbles_l.count()
        if n > 0 and self.bubbles_l.itemAt(n-1).spacerItem():
            self.bubbles_l.removeItem(self.bubbles_l.itemAt(n-1))
        bubble = ChatBubble(role, text)
        self.bubbles_l.addWidget(bubble)
        self.bubbles_l.addStretch()
        QTimer.singleShot(60, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))
        return bubble'''

if old_add_bubble in text:
    text = text.replace(old_add_bubble, new_add_bubble)
    print("_add_bubble patched.")
else:
    print("Could not find _add_bubble to patch!")


# 3. Add typing queue logic in VoodoAssistant
old_init = '''        self._glow_phase: float = 0.0  # 0..1, advances each tick

        self.signals = WorkerSignals()'''

new_init = '''        self._glow_phase: float = 0.0  # 0..1, advances each tick
        self._type_queue = ""
        self._type_timer = QTimer(self)
        self._type_timer.timeout.connect(self._tick_type)

        self.signals = WorkerSignals()'''

if old_init in text:
    text = text.replace(old_init, new_init)
    print("Typing queue init patched.")

# Add _tick_type method
old_blink = '''    def _schedule_blink(self):
        """Randomized blink intervals, ~1.5 to 5.5s."""'''

new_blink = '''    def _tick_type(self):
        if not self._type_queue or not self._streaming_label:
            self._type_timer.stop()
            return
        
        # Pop a chunk of characters based on queue length to catch up if behind
        chunk_size = max(1, len(self._type_queue) // 5)
        chars = self._type_queue[:chunk_size]
        self._type_queue = self._type_queue[chunk_size:]
        
        self._streaming_thought += chars
        self._streaming_label.update_text(f"🤔 {self._streaming_thought}")
        
        tail = self._streaming_thought.replace("\\n", " ").strip()
        tail = tail.rsplit(". ", 1)[-1]
        if len(tail) > 140:
            tail = "..." + tail[-137:]
        if tail:
            self._set_status(tail)

    def _schedule_blink(self):
        """Randomized blink intervals, ~1.5 to 5.5s."""'''

if old_blink in text:
    text = text.replace(old_blink, new_blink)
    print("_tick_type added.")

# Modify _on_thought_delta to feed queue
old_thought_delta = '''    def _on_thought_delta(self, chunk: str):
        self._ensure_session_ui()
        if not self._streaming_label:
            # Late join — create a bubble on the fly so deltas have somewhere
            # to land (happens when the widget connects mid-session).
            self._streaming_label = self._add_bubble("Voodo", "🤔 ")
        self._streaming_thought += chunk
        safe = self._streaming_thought.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\\n', '<br>')
        self._streaming_label.setText(f"🤔 {safe}")
        # Mirror the live tail of the thought into the always-visible status
        # line so the popup feels alive with the history collapsed. Take
        # the last sentence/clause; the label wraps to 2 lines, so ~140
        # chars actually fit on screen.
        tail = self._streaming_thought.replace("\\n", " ").strip()
        tail = tail.rsplit(". ", 1)[-1]
        if len(tail) > 140:
            tail = "..." + tail[-137:]
        if tail:
            self._set_status(tail)'''

new_thought_delta = '''    def _on_thought_delta(self, chunk: str):
        self._ensure_session_ui()
        if not self._streaming_label:
            self._streaming_label = self._add_bubble("Voodo", "🤔 ")
        self._type_queue += chunk
        if not self._type_timer.isActive():
            self._type_timer.start(25)'''

if old_thought_delta in text:
    text = text.replace(old_thought_delta, new_thought_delta)
    print("_on_thought_delta patched.")
else:
    print("Could not find _on_thought_delta!")

# 4. Auto-collapse history when idle
# We can add an enterEvent / leaveEvent to VoodoAssistant
old_events = '''    def enterEvent(self, event):
        self.close_btn.show()
        if not self._is_thinking:
            self.input.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.close_btn.hide()
        if not self.hist_open and not self._is_thinking:
            self.input.hide()
        super().leaveEvent(event)'''

new_events = '''    def enterEvent(self, event):
        self.close_btn.show()
        if not self._is_thinking:
            self.input.show()
        if hasattr(self, '_idle_timer'):
            self._idle_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.close_btn.hide()
        if not self.hist_open and not self._is_thinking:
            self.input.hide()
        
        # Auto collapse history when thinking and mouse leaves
        if self._is_thinking and self.hist_open:
            if not hasattr(self, '_idle_timer'):
                self._idle_timer = QTimer(self)
                self._idle_timer.timeout.connect(self._auto_collapse)
            self._idle_timer.start(2000)
            
        super().leaveEvent(event)
        
    def _auto_collapse(self):
        self._idle_timer.stop()
        if self.hist_open and self._is_thinking:
            self._toggle_history()'''

if old_events in text:
    text = text.replace(old_events, new_events)
    print("Hover events patched for auto-collapse.")

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print("Done patching.")
