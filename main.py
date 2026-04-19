import sys, os, threading, math, time, urllib.request
import requests, psutil, pyautogui, pyttsx3, re, json
import xml.etree.ElementTree as ET
import speech_recognition as sr
import subprocess, webbrowser
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# ── Clipboard: prefer pyperclip, fall back to Qt ──────────────
try:
    import pyperclip
    def _set_clipboard(text):
        pyperclip.copy(text)
except ImportError:
    pyperclip = None
    def _set_clipboard(text):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QStackedWidget, QSizePolicy, QTextEdit
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QRectF, QPoint
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QImage, QPixmap, QTextCursor
from PyQt6.QtWebEngineWidgets import QWebEngineView

# ═══════════════════════════════════════════════════════════════
#  ENV / AI CLIENT
# ═══════════════════════════════════════════════════════════════
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "You are J.A.R.V.I.S. — Just A Rather Very Intelligent System. "
        "Your creator and sole administrator is Aditya. "
        "Keep answers punchy, analytical, and highly structured. "
        "Use markdown formatting: **bold** for key terms, bullet points for lists, "
        "and code blocks for code. Address Aditya directly. "
        "Limit responses to what is asked — no padding."
    )
}
chat_history = []

# ═══════════════════════════════════════════════════════════════
#  THEME
# ═══════════════════════════════════════════════════════════════
BG_DEEP   = "#020508"
BG_PANEL  = "#040a12"
BG_CARD   = "#081525"
CYAN      = "#00e5ff"
DIM_CYAN  = "#004455"
ORANGE    = "#ff6600"
GREEN     = "#00ff88"
TEXT_BRI  = "#e0ffff"
TEXT_MID  = "#88aacc"
TEXT_DIM  = "#3a5f7a"
BORDER    = "#0a2535"
SOLID_BG  = "#050b14"

# ═══════════════════════════════════════════════════════════════
#  BACKGROUND THREADS
# ═══════════════════════════════════════════════════════════════
class TTSThread(QThread):
    started_speaking  = pyqtSignal()
    finished_speaking = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._queue    = []
        self._running  = True
        self.engine    = None

    def run(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except ImportError:
            pass

        try:
            self.engine = pyttsx3.init()
            for v in self.engine.getProperty('voices'):
                if any(k in v.name for k in ("Hazel", "David", "Mark")) or "GB" in v.id:
                    self.engine.setProperty('voice', v.id)
                    break
            self.engine.setProperty('rate', 172)
            self.engine.setProperty('volume', 0.95)
        except Exception as e:
            print(f"[TTS] Init failed: {e}")
            return

        while self._running:
            if self._queue:
                text = self._queue.pop(0)
                self.started_speaking.emit()
                try:
                    self.engine.say(text)
                    self.engine.runAndWait()
                except Exception:
                    pass
                self.finished_speaking.emit()
            else:
                time.sleep(0.08)

        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except ImportError:
            pass

    def speak(self, text: str):
        # Strip markdown noise before speaking
        clean = re.sub(r'```[\w]*\n?|```', '', text)
        clean = re.sub(r'[*#_`>]', '', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        if clean:
            self._queue.append(clean)

    def stop(self):
        self._running = False


class GroqThread(QThread):
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, prompt: str, is_code_request: bool = False):
        super().__init__()
        self.prompt          = prompt
        self.is_code_request = is_code_request

    def run(self):
        if not self.is_code_request:
            chat_history.append({"role": "user", "content": self.prompt})
        try:
            messages = (
                [SYSTEM_PROMPT] + chat_history[-16:]
                if not self.is_code_request
                else [SYSTEM_PROMPT, {"role": "user", "content": self.prompt}]
            )
            r = client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                max_tokens=2048 if self.is_code_request else 900,
                temperature=0.7,
            )
            reply = r.choices[0].message.content
            if not self.is_code_request:
                chat_history.append({"role": "assistant", "content": reply})
            self.response_ready.emit(reply)
        except Exception as e:
            self.error_occurred.emit(f"⚠ API Failure: {e}")

# ═══════════════════════════════════════════════════════════════
#  SYSTEM COMMAND EXECUTOR
# ═══════════════════════════════════════════════════════════════
def execute_system_command(cmd: str):
    c = cmd.lower().strip()

    # ── Todo ──────────────────────────────────────────────────
    if re.search(r'\b(add to.?do|remember)\b', c):
        item = re.sub(r'\b(add to.?do|remember)\b', '', c).strip()
        with open("jarvis_tasks.txt", "a") as f:
            f.write(f"[{datetime.now().strftime('%d/%m %H:%M')}] {item}\n")
        return ("text", f"✓ Directive logged: *{item}*")

    if re.search(r'\b(read to.?do|my tasks|task list)\b', c):
        try:
            with open("jarvis_tasks.txt", "r") as f:
                data = f.read().strip()
            return ("text", f"**Pending Directives:**\n{data}" if data else "No active directives.")
        except FileNotFoundError:
            return ("text", "No task database found.")

    # ── Volume ────────────────────────────────────────────────
    m = re.search(r'volume\D*(\d+)', c)
    if m:
        vol = int(m.group(1))
        for _ in range(50): pyautogui.press("volumedown")
        for _ in range(vol // 2): pyautogui.press("volumeup")
        return ("text", f"🔊 Audio recalibrated → {vol}%")

    if "mute" in c:
        pyautogui.press("volumemute")
        return ("text", "🔇 Acoustics muted.")

    # ── Screenshot ────────────────────────────────────────────
    if "screenshot" in c:
        path = os.path.expanduser(f"~/Desktop/jarvis_{int(time.time())}.png")
        pyautogui.screenshot(path)
        return ("text", f"📸 Visual capture saved → `{path}`")

    # ── Window management ─────────────────────────────────────
    if "close window" in c or "close app" in c:
        pyautogui.hotkey('alt', 'f4')
        return ("text", "Window terminated.")
    if "switch window" in c or "alt tab" in c:
        pyautogui.hotkey('alt', 'tab')
        return ("text", "Context switched.")
    if "minimize" in c:
        pyautogui.hotkey('win', 'down')
        return ("text", "Window minimized.")
    if "maximize" in c:
        pyautogui.hotkey('win', 'up')
        return ("text", "Window maximized.")
    if "show desktop" in c:
        pyautogui.hotkey('win', 'd')
        return ("text", "Desktop exposed.")

    # ── Mouse & keyboard ──────────────────────────────────────
    if "scroll down" in c: pyautogui.scroll(-600); return ("text", "Scrolled ↓")
    if "scroll up"   in c: pyautogui.scroll(600);  return ("text", "Scrolled ↑")
    if "right click" in c: pyautogui.rightClick();  return ("text", "Right-click executed.")
    if "double click" in c: pyautogui.doubleClick(); return ("text", "Double-click executed.")
    if "click" in c and "right" not in c and "double" not in c:
        pyautogui.click(); return ("text", "Clicked.")

    if "copy" in c: pyautogui.hotkey('ctrl', 'c'); return ("text", "Copied to clipboard.")
    if "paste" in c: pyautogui.hotkey('ctrl', 'v'); return ("text", "Pasted.")
    if "select all" in c: pyautogui.hotkey('ctrl', 'a'); return ("text", "All selected.")
    if "undo" in c: pyautogui.hotkey('ctrl', 'z'); return ("text", "Action undone.")
    if "redo" in c: pyautogui.hotkey('ctrl', 'y'); return ("text", "Action redone.")
    if "save" in c: pyautogui.hotkey('ctrl', 's'); return ("text", "Saved.")

    # ── System tools ──────────────────────────────────────────
    if "open settings" in c: pyautogui.hotkey('win', 'i'); return ("text", "Settings opened.")
    if "task manager" in c: pyautogui.hotkey('ctrl', 'shift', 'esc'); return ("text", "Task Manager launched.")
    if "lock" in c and ("pc" in c or "screen" in c or "workstation" in c):
        os.system("rundll32.exe user32.dll,LockWorkStation")
        return ("text", "🔒 Workstation locked.")

    # ── Media ─────────────────────────────────────────────────
    if any(k in c for k in ("play music", "pause music", "play media", "pause media")):
        pyautogui.press("playpause")
        return ("text", "Media toggled.")
    if "next track" in c: pyautogui.press("nexttrack"); return ("text", "Next track.")
    if "prev track" in c: pyautogui.press("prevtrack"); return ("text", "Previous track.")

    # ── Type / Press ──────────────────────────────────────────
    tm = re.search(r'\btype\s+(.+)', c)
    if tm:
        _set_clipboard(tm.group(1))
        pyautogui.hotkey('ctrl', 'v')
        return ("text", f"Injected: `{tm.group(1)}`")

    pm = re.search(r'\bpress\s+([a-z0-9]+)', c)
    if pm:
        try:
            pyautogui.press(pm.group(1))
            return ("text", f"Key `{pm.group(1)}` pressed.")
        except Exception:
            pass

    # ── Web & YouTube ──────────────────────────────────────────
    if "youtube" in c and any(k in c for k in ("play", "search", "find")):
        q = re.sub(r'\b(youtube|play|search|find)\b', '', c).strip()
        webbrowser.open(f"https://www.youtube.com/results?search_query={q.replace(' ', '+')}")
        return ("text", f"▶ YouTube search: *{q}*")

    if "google" in c and "search" in c:
        q = re.sub(r'\b(google|search)\b', '', c).strip()
        webbrowser.open(f"https://www.google.com/search?q={q.replace(' ', '+')}")
        return ("text", f"🔍 Google search: *{q}*")

    om = re.search(r'\b(?:open|launch)\s+(.+)', c)
    if om:
        app = om.group(1).strip()
        known = {"chrome": "chrome", "notepad": "notepad", "calculator": "calc",
                 "explorer": "explorer", "cmd": "cmd", "paint": "mspaint",
                 "word": "winword", "excel": "excel", "powerpoint": "powerpnt"}
        if app in known:
            subprocess.Popen(f"start {known[app]}", shell=True)
        else:
            pyautogui.press('win')
            time.sleep(0.6)
            pyautogui.write(app, interval=0.05)
            time.sleep(0.6)
            pyautogui.press('enter')
        return ("text", f"Launching *{app}*…")

    # ── News ───────────────────────────────────────────────────
    if any(k in c for k in ("news", "headlines", "current events")):
        try:
            url = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            xml_data = urllib.request.urlopen(req, timeout=6).read()
            items = [
                {"title": i.find('title').text}
                for i in ET.fromstring(xml_data).findall('./channel/item')[:6]
            ]
            return ("news", items)
        except Exception as e:
            return ("text", f"⚠ News feed unavailable: {e}")

    # ── Weather ────────────────────────────────────────────────
    if "weather" in c:
        parts = re.split(r'\bweather\b', c)
        city = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "Delhi"
        try:
            res = requests.get(f"https://wttr.in/{city}?format=j1", timeout=5).json()
            cur = res["current_condition"][0]
            return ("text",
                f"🌤 **{city.upper()}**\n"
                f"Temperature: `{cur['temp_C']}°C` (feels {cur['FeelsLikeC']}°C)\n"
                f"Condition: {cur['weatherDesc'][0]['value']}\n"
                f"Humidity: {cur['humidity']}%  Wind: {cur['windspeedKmph']} km/h"
            )
        except Exception:
            return ("text", "⚠ Meteorological sensors offline.")

    # ── System stats ───────────────────────────────────────────
    if any(k in c for k in ("system stats", "system status", "diagnostics")):
        cpu  = psutil.cpu_percent(interval=0.3)
        ram  = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        return ("text",
            f"**System Diagnostics**\n"
            f"CPU: `{cpu}%`\n"
            f"RAM: `{ram.percent}%` ({ram.used // 1024**2} MB / {ram.total // 1024**2} MB)\n"
            f"Disk: `{disk.percent}%` used ({disk.free // 1024**3} GB free)"
        )

    return (None, None)

# ═══════════════════════════════════════════════════════════════
#  UI COMPONENTS
# ═══════════════════════════════════════════════════════════════
class ArcReactor(QWidget):
    def __init__(self, size=220):
        super().__init__()
        self.setFixedSize(size, size)
        self.a1 = 0.0; self.a2 = 0.0; self.a3 = 0.0
        self.is_speaking = False
        self._t = 0.0

    def tick(self, t: float):
        self._t  = t
        self.a1  = (self.a1 + 1.8) % 360
        self.a2  = (self.a2 - 2.8) % 360
        self.a3  = (self.a3 + 0.4) % 360
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        p.translate(cx, cy)

        # Outer tick ring
        p.save(); p.rotate(self.a3)
        for i in range(24):
            angle = math.radians(i * 15)
            r0, r1 = 98, 105
            x0, y0 = r0 * math.cos(angle), r0 * math.sin(angle)
            x1, y1 = r1 * math.cos(angle), r1 * math.sin(angle)
            col = QColor(CYAN) if i % 3 == 0 else QColor(BORDER)
            p.setPen(QPen(col, 1.5))
            p.drawLine(int(x0), int(y0), int(x1), int(y1))
        p.restore()

        # Mid arc rings
        p.save(); p.rotate(self.a2)
        pen = QPen(QColor(CYAN), 3); pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        r = QRectF(-75, -75, 150, 150)
        p.drawArc(r, 0, 100 * 16); p.drawArc(r, 180 * 16, 100 * 16)
        pen2 = QPen(QColor(ORANGE), 1.5); pen2.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen2)
        p.drawArc(r, 90 * 16, 30 * 16); p.drawArc(r, 270 * 16, 30 * 16)
        p.restore()

        # Inner rotating arc
        p.save(); p.rotate(self.a1)
        pulse = math.sin(self._t * 6) * 30 if self.is_speaking else math.sin(self._t * 1.5) * 8
        alpha = int(min(255, 160 + pulse))
        inner_col = QColor(0, 229, 255, alpha) if self.is_speaking else QColor(0, 100, 140)
        p.setPen(QPen(inner_col, 10))
        p.drawEllipse(QRectF(-42, -42, 84, 84))
        p.restore()

        # Core dot
        core_r = 20 + (3 if self.is_speaking else 0)
        glow = QColor(0, 229, 255, 60)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QRectF(-core_r-6, -core_r-6, (core_r+6)*2, (core_r+6)*2))
        p.setBrush(QColor(CYAN if self.is_speaking else DIM_CYAN))
        p.drawEllipse(QRectF(-core_r, -core_r, core_r*2, core_r*2))

        # Label
        p.setPen(QColor(CYAN))
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.drawText(QRectF(-40, 48, 80, 16), Qt.AlignmentFlag.AlignCenter, "J.A.R.V.I.S")


class CircularProgress(QWidget):
    def __init__(self, title: str, color: str):
        super().__init__()
        self.setFixedSize(95, 95)
        self._val = 0.0; self.title = title; self.color = color

    def set_value(self, v: float):
        self._val = v; self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(10, 10, 75, 75)

        p.setPen(QPen(QColor(BORDER), 5))
        p.drawEllipse(r)

        pen = QPen(QColor(self.color), 5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        span = int((self._val / 100.0) * -360 * 16)
        p.drawArc(r, 90 * 16, span)

        p.setPen(QColor(TEXT_BRI))
        p.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, f"{int(self._val)}%")

        p.setPen(QColor(TEXT_DIM))
        p.setFont(QFont("Courier New", 7))
        p.drawText(QRectF(0, 78, 95, 14), Qt.AlignmentFlag.AlignCenter, self.title)


def _md_to_html(text: str) -> str:
    """Convert subset of markdown to HTML for QLabel."""
    # Code blocks
    text = re.sub(
        r'```[\w]*\n?(.*?)```',
        lambda m: (
            f'<pre style="background:#0a1e2e; color:#00ff88; '
            f'padding:8px 10px; border-left:3px solid #00ff88; '
            f'font-family:Consolas,monospace; font-size:10px; '
            f'border-radius:3px; white-space:pre-wrap;">{m.group(1).strip()}</pre>'
        ),
        text,
        flags=re.DOTALL
    )
    # Inline code
    text = re.sub(r'`([^`]+)`',
        r'<code style="background:#0a1e2e; color:#00ff88; '
        r'padding:1px 5px; border-radius:2px; font-family:Consolas;">\1</code>',
        text)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*',
        r'<b style="color:#e0ffff;">\1</b>', text)
    # Italic
    text = re.sub(r'\*(.+?)\*',
        r'<i style="color:#88aacc;">\1</i>', text)
    # Headers
    text = re.sub(r'^###\s+(.+)$',
        r'<p style="color:#00e5ff; font-size:13px; margin:6px 0;"><b>\1</b></p>',
        text, flags=re.MULTILINE)
    text = re.sub(r'^##\s+(.+)$',
        r'<p style="color:#00e5ff; font-size:15px; margin:6px 0;"><b>\1</b></p>',
        text, flags=re.MULTILINE)
    text = re.sub(r'^#\s+(.+)$',
        r'<p style="color:#00e5ff; font-size:17px; margin:8px 0;"><b>\1</b></p>',
        text, flags=re.MULTILINE)
    # Bullets
    text = re.sub(r'^[-*]\s+(.+)$',
        r'<p style="margin:2px 0; padding-left:14px;">◆ \1</p>',
        text, flags=re.MULTILINE)
    # Numbered list
    text = re.sub(r'^(\d+)\.\s+(.+)$',
        r'<p style="margin:2px 0; padding-left:14px;">\1. \2</p>',
        text, flags=re.MULTILINE)
    # Newlines → <br> (skip lines already wrapped in block tags)
    text = re.sub(r'\n(?!<(?:pre|p))', '<br>', text)
    return text


class MsgWidget(QFrame):
    def __init__(self, text: str, sender: str):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(0)

        bubble = QFrame()
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(12, 10, 12, 10)

        html = _md_to_html(text)
        lbl = QLabel(html)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setFont(QFont("Segoe UI", 10))
        lbl.setWordWrap(True)
        lbl.setOpenExternalLinks(False)
        bl.addWidget(lbl)

        if sender == "jarvis":
            lbl.setStyleSheet(f"color: {CYAN};")
            bubble.setStyleSheet(
                f"background: rgba(0,229,255,0.04); "
                f"border-left: 3px solid {CYAN}; border-radius: 4px;"
            )
            bubble.setMaximumWidth(820)
            outer.addWidget(bubble)
            outer.addStretch()
        else:
            lbl.setStyleSheet(f"color: {TEXT_BRI};")
            bubble.setStyleSheet(
                f"background: rgba(255,102,0,0.08); "
                f"border-right: 3px solid {ORANGE}; border-radius: 4px;"
            )
            bubble.setMaximumWidth(600)
            outer.addStretch()
            outer.addWidget(bubble)

# ═══════════════════════════════════════════════════════════════
#  BIOMETRIC BOOT SCREEN
# ═══════════════════════════════════════════════════════════════
class BiometricBoot(QWidget):
    boot_complete = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(640, 520)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl = QLabel("INITIALIZING BIOMETRIC SCAN…")
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl.setStyleSheet(
            f"color:{CYAN}; font-family:'Courier New'; font-size:18px; "
            f"border:2px solid {CYAN}; padding:10px; background:{BG_DEEP};"
        )
        lay.addWidget(self.lbl)

        if HAS_CV2:
            self.cap = cv2.VideoCapture(0)
            self._timer = QTimer()
            self._timer.timeout.connect(self._frame)
            self._timer.start(30)
        else:
            self.lbl.setText("BIOMETRIC SENSOR OFFLINE\nBYPASSING SCAN…")
            self.cap = None

        QTimer.singleShot(4000, self._grant)

    def _frame(self):
        if not (self.cap and self.cap.isOpened()): return
        ret, frame = self.cap.read()
        if not ret: return
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2
        cv2.circle(frame, (cx, cy), 160, (0, 229, 255), 2)
        cv2.rectangle(frame, (cx-100, cy-120), (cx+100, cy+120), (0, 100, 255), 1)
        # Scan line animation
        t = int(time.time() * 120) % 240 - 120
        cv2.line(frame, (cx-100, cy+t), (cx+100, cy+t), (0, 229, 255, 100), 1)
        cv2.putText(frame, "SCANNING BIOMETRICS", (cx-95, cy+170),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 229, 255), 1)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        qi = QImage(frame.data, w, h, w*3, QImage.Format.Format_RGB888)
        self.lbl.setPixmap(
            QPixmap.fromImage(qi).scaled(580, 460, Qt.AspectRatioMode.KeepAspectRatio)
        )

    def _grant(self):
        if hasattr(self, '_timer'): self._timer.stop()
        if self.cap and self.cap.isOpened(): self.cap.release()
        self.lbl.setPixmap(QPixmap())
        self.lbl.setText("✓  ACCESS GRANTED\n\nWELCOME, ADITYA")
        self.lbl.setStyleSheet(
            f"color:{GREEN}; font-family:'Courier New'; font-size:24px; "
            f"font-weight:bold; letter-spacing:4px; background:{BG_DEEP}; "
            f"border:2px solid {GREEN}; padding:20px;"
        )
        QTimer.singleShot(1600, self._launch)

    def _launch(self):
        self.close()
        self._main = JarvisUI()
        self._main.show()

# ═══════════════════════════════════════════════════════════════
#  MAIN JARVIS UI
# ═══════════════════════════════════════════════════════════════
class JarvisUI(QWidget):
    # ── Signals (thread-safe UI updates) ──────────────────────
    sig_add_msg     = pyqtSignal(str, str)
    sig_set_status  = pyqtSignal(str, bool)
    sig_set_input   = pyqtSignal(str)   # thread-safe input setter

    def __init__(self):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S. MATRIX v9.0")
        self.showMaximized()
        self.setStyleSheet(f"background:{BG_DEEP}; color:{TEXT_MID};")

        # ── State ──────────────────────────────────────────────
        self.is_analyzing    = False
        self.is_macro_typing = False
        self.ai_thread       = None
        self._float_t        = 0.0

        # ── TTS ────────────────────────────────────────────────
        self.tts = TTSThread()
        self.tts.started_speaking.connect(lambda: setattr(self.reactor, 'is_speaking', True))
        self.tts.finished_speaking.connect(lambda: setattr(self.reactor, 'is_speaking', False))
        self.tts.start()

        # ── Wire signals ───────────────────────────────────────
        self.sig_add_msg.connect(self._on_add_msg)
        self.sig_set_status.connect(self._on_set_status)
        self.sig_set_input.connect(self._on_set_input)

        self._build_ui()
        self._start_timers()

        # Boot message
        self.sig_add_msg.emit(
            "**Biometrics confirmed. Matrix v9.0 online.**\n"
            "All systems nominal. Ghost Writer and voice control armed. Awaiting directive.",
            "jarvis"
        )
        self.tts.speak("Biometrics confirmed. Matrix online. Awaiting your command, Aditya.")

    # ──────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ════ LEFT PANEL ══════════════════════════════════════
        left = QFrame()
        left.setFixedWidth(340)
        left.setStyleSheet(f"background:{BG_PANEL}; border-right:1px solid {BORDER};")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(28, 36, 28, 36)
        ll.setSpacing(14)

        self.reactor = ArcReactor()
        ll.addWidget(self.reactor, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.status_lbl = QLabel("STANDBY")
        self.status_lbl.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        self.status_lbl.setStyleSheet(f"color:{CYAN}; letter-spacing:5px;")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.addWidget(self.status_lbl)

        # CPU / RAM rings
        rings = QHBoxLayout()
        rings.setSpacing(20)
        self.cpu_ring = CircularProgress("CPU", CYAN)
        self.ram_ring = CircularProgress("RAM", ORANGE)
        rings.addWidget(self.cpu_ring); rings.addWidget(self.ram_ring)
        ll.addLayout(rings)

        # Clock
        self.time_lbl = QLabel("00:00")
        self.time_lbl.setFont(QFont("Segoe UI", 34, QFont.Weight.Bold))
        self.time_lbl.setStyleSheet(f"color:{TEXT_BRI};")
        self.time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.addWidget(self.time_lbl)

        # Date
        self.date_lbl = QLabel(datetime.now().strftime("%A, %d %B %Y"))
        self.date_lbl.setFont(QFont("Courier New", 9))
        self.date_lbl.setStyleSheet(f"color:{TEXT_DIM};")
        self.date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.addWidget(self.date_lbl)

        ll.addStretch()

        # Quick-action grid
        grid = QGridLayout(); grid.setSpacing(8)
        btns = [
            ("📋 Tasks",     "read tasks"),
            ("🌤 Weather",   "weather delhi"),
            ("📰 News",      "headlines"),
            ("📊 Diag",      "system stats"),
            ("✖ Close Sim",  "close sim"),
            ("⏻ Exit",       "exit"),
        ]
        for i, (label, cmd) in enumerate(btns):
            b = QPushButton(label); b.setFixedHeight(36)
            b.setStyleSheet(
                f"background:{SOLID_BG}; color:{CYAN}; "
                f"border:1px solid {DIM_CYAN}; font-family:'Courier New'; "
                f"font-size:10px; border-radius:3px;"
            )
            b.clicked.connect(lambda _, c=cmd: self._force_cmd(c))
            grid.addWidget(b, i // 2, i % 2)
        ll.addLayout(grid)
        root.addWidget(left)

        # ════ RIGHT PANEL ═════════════════════════════════════
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        # Header bar
        hdr = QFrame()
        hdr.setFixedHeight(56)
        hdr.setStyleSheet(f"background:{BG_PANEL}; border-bottom:1px solid {BORDER};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(24, 0, 24, 0)
        hl.addWidget(QLabel(
            f"<span style='color:{CYAN}; font-family:\"Courier New\"; "
            f"font-size:14px; letter-spacing:3px;'>"
            f"◈ UPLINK SECURE · ADITYA PROTOCOL v9</span>"
        ))
        hl.addStretch()
        self.net_lbl = QLabel("LATENCY: --ms")
        self.net_lbl.setFont(QFont("Courier New", 9))
        self.net_lbl.setStyleSheet(f"color:{ORANGE};")
        hl.addWidget(self.net_lbl)
        rl.addWidget(hdr)

        # Stack: chat / web
        self.stack = QStackedWidget()

        # Chat pane
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet("border:none; background:transparent;")
        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background:transparent;")
        self.chat_lay = QVBoxLayout(self.chat_container)
        self.chat_lay.setContentsMargins(36, 36, 36, 36)
        self.chat_lay.setSpacing(6)
        self.chat_lay.addStretch()           # messages go AFTER this
        self.chat_scroll.setWidget(self.chat_container)

        # Web / hologram pane
        self.web_view = QWebEngineView()
        self.web_view.setStyleSheet("background:transparent; border:none;")

        self.stack.addWidget(self.chat_scroll)   # index 0
        self.stack.addWidget(self.web_view)       # index 1
        rl.addWidget(self.stack)

        # Input footer
        ftr = QFrame()
        ftr.setFixedHeight(78)
        ftr.setStyleSheet(f"background:{BG_PANEL}; border-top:1px solid {BORDER};")
        fl = QHBoxLayout(ftr)
        fl.setContentsMargins(24, 14, 24, 14)
        fl.setSpacing(10)

        self.input = QLineEdit()
        self.input.setPlaceholderText(">> Enter directive or voice command…")
        self.input.setFixedHeight(44)
        self.input.setStyleSheet(
            f"background:{BG_DEEP}; color:{CYAN}; "
            f"border:1px solid {DIM_CYAN}; border-radius:3px; "
            f"font-family:Consolas; font-size:15px; padding:0 18px;"
        )
        self.input.returnPressed.connect(self.handle_text)

        self.send_btn = QPushButton("EXECUTE")
        self.send_btn.setFixedSize(115, 44)
        self.send_btn.setStyleSheet(
            f"background:#041018; color:{CYAN}; border:1px solid {CYAN}; "
            f"font-family:'Courier New'; font-weight:bold; letter-spacing:2px; border-radius:3px;"
        )
        self.send_btn.clicked.connect(self.handle_text)

        self.mic_btn = QPushButton("● MIC")
        self.mic_btn.setFixedSize(70, 44)
        self.mic_btn.setStyleSheet(
            f"background:#180600; color:{ORANGE}; border:1px solid {ORANGE}; "
            f"font-family:'Courier New'; font-weight:bold; border-radius:3px;"
        )
        self.mic_btn.clicked.connect(self.handle_voice)

        fl.addWidget(self.input)
        fl.addWidget(self.send_btn)
        fl.addWidget(self.mic_btn)
        rl.addWidget(ftr)
        root.addWidget(right)

    # ──────────────────────────────────────────────────────────
    def _start_timers(self):
        self._t_anim = QTimer(self)
        self._t_anim.timeout.connect(self._tick_anim)
        self._t_anim.start(30)

        self._t_sys = QTimer(self)
        self._t_sys.timeout.connect(self._tick_sys)
        self._t_sys.start(1000)

    def _tick_anim(self):
        self._float_t += 0.05
        self.reactor.tick(self._float_t)

    def _tick_sys(self):
        now = datetime.now()
        self.time_lbl.setText(now.strftime("%H:%M:%S"))
        self.cpu_ring.set_value(psutil.cpu_percent())
        self.ram_ring.set_value(psutil.virtual_memory().percent)

    # ── Slot implementations ───────────────────────────────────
    def _on_add_msg(self, text: str, sender: str):
        w = MsgWidget(text, sender)
        # Insert before the trailing stretch (last item)
        self.chat_lay.insertWidget(self.chat_lay.count() - 1, w)
        QTimer.singleShot(80, lambda: (
            self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum()
            )
        ))

    def _on_set_status(self, txt: str, active: bool):
        self.status_lbl.setText(txt)
        color = ORANGE if active else CYAN
        self.status_lbl.setStyleSheet(f"color:{color}; letter-spacing:5px;")

    def _on_set_input(self, text: str):
        self.input.setText(text)
        self.handle_text()

    # ── Force-commands from sidebar ────────────────────────────
    def _force_cmd(self, cmd: str):
        if cmd == "exit":
            self.tts.stop(); self.tts.wait(500)
            sys.exit(0)
        if cmd == "close sim":
            self.web_view.setHtml("")
            self.stack.setCurrentIndex(0)
            self.is_analyzing = False
            return
        self.sig_set_input.emit(cmd)

    # ──────────────────────────────────────────────────────────
    #  CORE COMMAND HANDLER
    # ──────────────────────────────────────────────────────────
    def handle_text(self):
        cmd = self.input.text().strip()
        if not cmd: return
        self.input.clear()
        self.stack.setCurrentIndex(0)
        self.sig_add_msg.emit(cmd, "user")
        self.sig_set_status.emit("PROCESSING", True)

        c = cmd.lower()

        # ── GHOST WRITER PROTOCOL ─────────────────────────────
        # Pattern A: "write/type/code/create <what> in <app>"
        # Pattern B: "open <app> and write/type/code <what>"
        prompt = app_name = None

        m2 = re.search(r'\b(?:open|launch)\s+(.+?)\s+and\s+(?:write|type|code|create)\s+(.+)', c)
        m1 = re.search(r'\b(?:write|type|code|create)\s+(.+?)\s+in\s+(.+)', c)

        if m2:
            app_name = m2.group(1).strip()
            prompt   = m2.group(2).strip()
        elif m1 and not any(k in c for k in ("visualize", "simulate", "draw")):
            prompt   = m1.group(1).strip()
            app_name = m1.group(2).strip()

        if prompt and app_name:
            self._ghost_writer(prompt, app_name, open_app=True)
            return

        # Pattern C: "ghost type / auto type <anything>" (no app, paste wherever focus is)
        m3 = re.search(r'\b(?:ghost type|auto type|inject)\s+(.+)', c)
        if m3:
            self._ghost_writer(m3.group(1).strip(), app_name=None, open_app=False)
            return

        # ── SYSTEM COMMANDS ───────────────────────────────────
        kind, result = execute_system_command(cmd)
        if kind == "text":
            self.sig_add_msg.emit(result, "jarvis")
            self.tts.speak(result)
            self.sig_set_status.emit("STANDBY", False)
            return
        elif kind == "news":
            news_md = "**Global Headlines:**\n" + "\n".join(
                f"- {n['title']}" for n in result
            )
            self.sig_add_msg.emit(news_md, "jarvis")
            self.tts.speak("Here are the latest headlines.")
            self.sig_set_status.emit("STANDBY", False)
            return

        # ── VISUALIZATION ─────────────────────────────────────
        if any(k in c for k in ("visualize", "simulate", "draw", "animate", "render")):
            self.is_analyzing = True
            self.stack.setCurrentIndex(1)
            self.tts.speak("Compiling simulation matrix.")
            ai_prompt = (
                f"Write a self-contained HTML file using p5.js CDN for: '{cmd}'. "
                f"Background must be #020508 (very dark). "
                f"Output ONLY raw HTML. No explanations, no markdown fences."
            )
            self._dispatch_ai(ai_prompt, is_code=True)
            return

        # ── GENERAL AI ────────────────────────────────────────
        self.is_analyzing = False
        self._dispatch_ai(cmd, is_code=False)

    def _dispatch_ai(self, prompt: str, is_code: bool):
        self.ai_thread = GroqThread(prompt, is_code_request=is_code)
        self.ai_thread.response_ready.connect(self._on_ai_reply)
        self.ai_thread.error_occurred.connect(self._on_ai_err)
        self.ai_thread.start()

    # ──────────────────────────────────────────────────────────
    #  GHOST WRITER  (clipboard-based → instant, reliable)
    # ──────────────────────────────────────────────────────────
    def _ghost_writer(self, prompt: str, app_name, open_app: bool):
        self.is_macro_typing = True
        self.is_analyzing    = False

        location = f"in {app_name}" if app_name else "in the active window"
        self.sig_add_msg.emit(
            f"**Ghost Writer Protocol activated.**\n"
            f"Generating content for: `{prompt}`\n"
            f"Target: *{location}*\n"
            f"⚠ Clipboard will be used — paste via Ctrl+V after injection.",
            "jarvis"
        )
        self.tts.speak(f"Ghost Writer activated. Generating content for {location}.")

        if open_app and app_name:
            def _launch():
                pyautogui.press('win')
                time.sleep(0.7)
                pyautogui.write(app_name, interval=0.06)
                time.sleep(0.7)
                pyautogui.press('enter')
            threading.Thread(target=_launch, daemon=True).start()

        ai_prompt = (
            f"Generate the following: {prompt}. "
            f"Output ONLY the raw content/code to be injected. "
            f"NO markdown code fences (no ```). NO explanations. "
            f"Just the exact text or code characters."
        )
        self._dispatch_ai(ai_prompt, is_code=True)

    def _inject_via_clipboard(self, text: str):
        """
        Copy text to clipboard, minimize JARVIS, wait for focus,
        then paste with Ctrl+V. Fast, reliable, works in any app.
        """
        # Clean residual markdown fences the LLM might slip in
        clean = re.sub(r'^```[\w]*\s*\n?', '', text, flags=re.MULTILINE)
        clean = re.sub(r'\n?```\s*$', '', clean, flags=re.MULTILINE).strip()

        COUNTDOWN = 6   # seconds for user to focus target window

        self.sig_add_msg.emit(
            f"✓ Content ready ({len(clean)} chars).\n"
            f"**Minimizing in {COUNTDOWN}s** — click inside your target window now.\n"
            f"Content will be pasted automatically via clipboard.",
            "jarvis"
        )
        self.tts.speak(
            f"Content generated. Minimizing in {COUNTDOWN} seconds. "
            f"Please click inside your target window now."
        )

        def _do_inject():
            time.sleep(COUNTDOWN)
            # 1. Set clipboard (thread-safe via signal to main thread)
            _set_clipboard(clean)
            # 2. Minimize JARVIS
            QTimer.singleShot(0, self.showMinimized)
            time.sleep(0.8)
            # 3. Paste
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.5)
            # 4. Restore
            QTimer.singleShot(0, self.showMaximized)
            QTimer.singleShot(200, lambda: self.sig_add_msg.emit(
                "✓ **Ghost Writer injection complete.** Content pasted via clipboard.", "jarvis"
            ))
            QTimer.singleShot(200, lambda: self.sig_set_status.emit("STANDBY", False))
            QTimer.singleShot(200, lambda: self.tts.speak("Injection complete, Aditya."))

        threading.Thread(target=_do_inject, daemon=True).start()

    # ──────────────────────────────────────────────────────────
    #  AI REPLY HANDLER
    # ──────────────────────────────────────────────────────────
    def _on_ai_reply(self, reply: str):
        if self.is_macro_typing:
            self.is_macro_typing = False
            self._inject_via_clipboard(reply)
            return

        if self.is_analyzing:
            # Extract HTML — try fenced block first, then raw
            html_match = re.search(r'```(?:html)?\s*\n(.*?)```', reply, re.DOTALL | re.IGNORECASE)
            clean_html = html_match.group(1).strip() if html_match else re.sub(r'```', '', reply).strip()
            self.web_view.setHtml(clean_html)
            self.sig_add_msg.emit("**[Simulation rendered]** — click *✖ Close Sim* to return.", "jarvis")
            self.tts.speak("Simulation ready, Sir.")
        else:
            self.sig_add_msg.emit(reply, "jarvis")
            self.tts.speak(reply)

        self.sig_set_status.emit("STANDBY", False)

    def _on_ai_err(self, err: str):
        self.is_macro_typing = False
        self.is_analyzing    = False
        self.sig_add_msg.emit(f"⚠ **{err}**", "jarvis")
        self.tts.speak("Network anomaly detected. API failure.")
        self.sig_set_status.emit("OFFLINE", False)

    # ──────────────────────────────────────────────────────────
    #  VOICE INPUT
    # ──────────────────────────────────────────────────────────
    def handle_voice(self):
        self.sig_set_status.emit("LISTENING…", True)
        self.mic_btn.setStyleSheet(
            f"background:{ORANGE}; color:#fff; border:1px solid {ORANGE}; "
            f"font-family:'Courier New'; font-weight:bold; border-radius:3px;"
        )
        threading.Thread(target=self._listen_worker, daemon=True).start()

    def _listen_worker(self):
        r = sr.Recognizer()
        r.energy_threshold = 300
        r.dynamic_energy_threshold = True
        try:
            with sr.Microphone() as src:
                r.adjust_for_ambient_noise(src, duration=0.4)
                audio = r.listen(src, timeout=6, phrase_time_limit=10)
            cmd = r.recognize_google(audio)
            # Thread-safe: push to input via signal then handle
            self.sig_set_input.emit(cmd)
        except sr.WaitTimeoutError:
            self.sig_add_msg.emit("⚠ Voice timeout — no audio detected.", "jarvis")
        except sr.UnknownValueError:
            self.sig_add_msg.emit("⚠ Could not parse audio — interference detected.", "jarvis")
        except Exception as e:
            self.sig_add_msg.emit(f"⚠ Voice subsystem error: {e}", "jarvis")
        finally:
            QTimer.singleShot(0, lambda: self.sig_set_status.emit("STANDBY", False))
            QTimer.singleShot(0, lambda: self.mic_btn.setStyleSheet(
                f"background:#180600; color:{ORANGE}; border:1px solid {ORANGE}; "
                f"font-family:'Courier New'; font-weight:bold; border-radius:3px;"
            ))

    def closeEvent(self, event):
        self.tts.stop()
        self.tts.wait(600)
        event.accept()

# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    if HAS_CV2:
        boot = BiometricBoot()
        boot.show()
    else:
        print("[JARVIS] OpenCV not found — bypassing biometric scan.")
        ui = JarvisUI()
        ui.show()

    sys.exit(app.exec())