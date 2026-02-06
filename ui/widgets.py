import threading
import time
from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtCore import Qt, pyqtSignal

class HotkeyLineEdit(QLineEdit):
    recording_started = pyqtSignal()
    hotkey_detected = pyqtSignal(str)

    def __init__(self, current_hotkey):
        super().__init__()
        self.setReadOnly(True)
        self.setText(current_hotkey)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: #ffffff; border: 1px solid #ccc; padding: 5px;")

    def mousePressEvent(self, event):
        self.recording_started.emit()
        self.clear()
        self.setText("... Drücke Tasten ...")
        self.setStyleSheet("background-color: #ffecb3; border: 2px solid #ff9800; font-weight: bold;")
        threading.Thread(target=self.record_hotkey, daemon=True).start()

    def record_hotkey(self):
        import keyboard as kb_logic
        time.sleep(0.3)
        try:
            # Deine Original-Logik:
            raw = kb_logic.read_hotkey(suppress=True)
            hk = raw.lower()
            
            # Normalisieren (englische + deutsche Bezeichner)
            hk = hk.replace("left windows", "windows").replace("right windows", "windows")
            hk = hk.replace("linke windows", "windows").replace("rechte windows", "windows")
            hk = hk.replace("umschalt", "shift").replace("strg", "ctrl").replace("steuerung", "ctrl")
            hk = hk.replace(" ", "")
            
            parts = [p for p in hk.split("+") if p]

            mods = []
            key = None
            for p in parts:
                if "win" in p or "windows" in p:
                    if "windows" not in mods: mods.append("windows")
                elif p in ("shift",):
                    if "shift" not in mods: mods.append("shift")
                elif p in ("ctrl",):
                    if "ctrl" not in mods: mods.append("ctrl")
                elif p in ("alt","altgr"):
                    if "alt" not in mods: mods.append("alt")
                elif len(p) == 1 or p in ("space","enter","tab","esc") or (p.startswith("f") and p[1:].isdigit()):
                    key = p
                else:
                    key = p
            
            if key is None:
                for p in reversed(parts):
                    if p not in ("windows","shift","ctrl","alt","altgr"):
                        key = p; break
            
            canonical = "+".join(mods + ([key] if key else []))
            
            # Fehlerfall abfangen (leerer String)
            if not canonical: 
                canonical = raw

            self.hotkey_detected.emit(canonical)
        except Exception as e:
            print(f"Fehler bei Hotkey-Aufnahme: {e}")