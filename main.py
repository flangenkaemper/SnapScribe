import sys
import json
import os
import threading
import pyperclip
import whisper
import sounddevice as sd
import numpy as np
import tempfile
import soundfile as sf
from ctypes import windll, wintypes, byref
from openai import OpenAI
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QWidget, QPushButton, QTextEdit, QLabel, 
                             QLineEdit, QCheckBox, QSystemTrayIcon, QMenu, QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
import keyboard as kb_logic

# Windows-Konstanten
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312

SETTINGS_FILE = "settings.json"

class AppSignals(QObject):
    finished = pyqtSignal(str)
    status = pyqtSignal(str)
    trigger_record = pyqtSignal()
    trigger_window = pyqtSignal()

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
        # Signalisieren, dass wir anfangen (blockiert die alten Hotkeys)
        self.recording_started.emit()
        self.clear()
        self.setText("... Drücke Tasten ...")
        self.setStyleSheet("background-color: #ffecb3; border: 2px solid #ff9800; font-weight: bold;")
        # Aufnahme in Thread starten
        threading.Thread(target=self.record_hotkey, daemon=True).start()

    def record_hotkey(self):
        import time
        # Kurzer Flush, um sicherzustellen, dass der Mausklick nicht registriert wird
        time.sleep(0.3)
        # Hotkey einlesen. suppress=True verhindert, dass Windows die Tasten währenddessen ausführt
        try:
            # Rohwert (kann lokalisiert oder mehrteilig sein, z.B. 'A+D+linke windows+umschalt')
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
                    # Fallback: wenn unbekannter Token, nehme ihn als Key
                    key = p
            # Falls mehrere Nicht-Mods vorhanden: nehme das letzte als Haupttaste
            if key is None:
                for p in reversed(parts):
                    if p not in ("windows","shift","ctrl","alt","altgr"):
                        key = p; break
            canonical = "+".join(mods + ([key] if key else []))
            print(f"[Hotkey] aufgenommen: raw='{raw}' -> canonical='{canonical}'")
            # Wir schicken nur den neuen Hotkey zurück (kein Anhängen!)
            self.hotkey_detected.emit(canonical)
        except Exception as e:
            print(f"Fehler bei Hotkey-Aufnahme: {e}")

class SnapScribe(QMainWindow):
    def __init__(self):
        super().__init__()
        self.load_settings()
        self.is_recording = False
        self.recording_data = []
        self.local_model = None
        
        self.signals = AppSignals()
        self.signals.finished.connect(self.process_result)
        self.signals.status.connect(self.update_status_ui)
        self.signals.trigger_record.connect(self.toggle_recording)
        self.signals.trigger_window.connect(self.toggle_window_visibility)

        self.init_ui()
        self.init_tray()
        
        self.hotkeys_active = True
        self.rebind_pending = True
        threading.Thread(target=self.windows_api_loop, daemon=True).start()
        threading.Thread(target=self.manage_model_loading, daemon=True).start()

    def load_settings(self):
        default = {"api_key": "", "active_mode": "local", "auto_copy": True, 
                   "minimize_to_tray": True, "hotkey_record": "windows+s", 
                   "hotkey_show": "windows+shift+d", "local_model_size": "base"}
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r") as f:
                    self.settings = {**default, **json.loads(f.read())}
            else: self.settings = default
        except: self.settings = default

    def save_settings(self):
        with open(SETTINGS_FILE, "w") as f: json.dump(self.settings, f, indent=4)

    def init_ui(self):
        self.setWindowTitle("SnapScribe Pro")
        self.setGeometry(100, 100, 450, 650)
        container = QWidget(); layout = QVBoxLayout()

        self.status_label = QLabel("Bereit"); self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        layout.addWidget(QLabel("<b>Letztes Transkript:</b>"))
        self.text_area = QTextEdit(); layout.addWidget(self.text_area)

        layout.addWidget(QLabel("<b>Modell & Quelle:</b>"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Lokal: Base", "Lokal: Small", "Lokal: Medium", "Lokal: Large-V3", "OpenAI API"])
        m_idx = {"base": 0, "small": 1, "medium": 2, "large-v3": 3}
        self.mode_combo.setCurrentIndex(4 if self.settings["active_mode"] == "api" else m_idx.get(self.settings["local_model_size"], 0))
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        layout.addWidget(self.mode_combo)

        # Hotkey Sektion
        hk_layout = QHBoxLayout()
        
        # Aufnahme-Feld
        self.hk_rec_edit = HotkeyLineEdit(self.settings["hotkey_record"])
        self.hk_rec_edit.recording_started.connect(self.pause_hotkeys)
        self.hk_rec_edit.hotkey_detected.connect(lambda v: self.update_hotkey_live("hotkey_record", v))
        
        # Fenster-Toggle-Feld
        self.hk_shw_edit = HotkeyLineEdit(self.settings["hotkey_show"])
        self.hk_shw_edit.recording_started.connect(self.pause_hotkeys)
        self.hk_shw_edit.hotkey_detected.connect(lambda v: self.update_hotkey_live("hotkey_show", v))

        v1 = QVBoxLayout(); v1.addWidget(QLabel("Aufnahme:")); v1.addWidget(self.hk_rec_edit)
        v2 = QVBoxLayout(); v2.addWidget(QLabel("Fenster Toggle:")); v2.addWidget(self.hk_shw_edit)
        hk_layout.addLayout(v1); hk_layout.addLayout(v2); layout.addLayout(hk_layout)

        self.api_input = QLineEdit(); self.api_input.setPlaceholderText("API Key..."); self.api_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_input.setText(self.settings["api_key"]); self.api_input.textChanged.connect(lambda t: self.update_setting("api_key", t))
        layout.addWidget(self.api_input)

        self.cb_copy = QCheckBox("Auto-Copy"); self.cb_copy.setChecked(self.settings["auto_copy"])
        self.cb_copy.stateChanged.connect(lambda: self.update_setting("auto_copy", self.cb_copy.isChecked()))
        layout.addWidget(self.cb_copy)

        self.cb_tray = QCheckBox("In Tray minimieren"); self.cb_tray.setChecked(self.settings["minimize_to_tray"])
        self.cb_tray.stateChanged.connect(lambda: self.update_setting("minimize_to_tray", self.cb_tray.isChecked()))
        layout.addWidget(self.cb_tray)

        self.record_btn = QPushButton("Aufnahme Start/Stopp"); self.record_btn.setFixedHeight(50)
        self.record_btn.clicked.connect(self.toggle_recording); layout.addWidget(self.record_btn)
        
        container.setLayout(layout); self.setCentralWidget(container)

    def pause_hotkeys(self):
        """Stoppt den Blocker, damit keyboard.read_hotkey sauber arbeiten kann"""
        self.hotkeys_active = False
        windll.user32.UnregisterHotKey(None, 1)
        windll.user32.UnregisterHotKey(None, 2)

    def update_hotkey_live(self, key, value):
        """Wird aufgerufen, wenn ein Feld eine neue Kombi fertig hat"""
        # Konfliktprüfung: nicht dieselbe Kombination für beide Hotkeys zulassen
        other = "hotkey_show" if key == "hotkey_record" else "hotkey_record"
        if value and value == self.settings.get(other):
            self.signals.status.emit("Hotkey-Konflikt: beide Hotkeys sind gleich. Bitte wähle eine andere Kombination.")
            # GUI zurücksetzen
            self.hk_rec_edit.setText(self.settings["hotkey_record"])
            self.hk_shw_edit.setText(self.settings["hotkey_show"])
            self.hk_rec_edit.setStyleSheet("background: #ffffff; border: 1px solid #ccc; padding: 5px;")
            self.hk_shw_edit.setStyleSheet("background: #ffffff; border: 1px solid #ccc; padding: 5px;")
            self.hotkeys_active = True
            self.rebind_pending = False
            return

        self.settings[key] = value
        self.save_settings()
        
        # GUI aktualisieren
        self.hk_rec_edit.setText(self.settings["hotkey_record"])
        self.hk_shw_edit.setText(self.settings["hotkey_show"])
        
        # Style zurücksetzen
        self.hk_rec_edit.setStyleSheet("background: #ffffff; border: 1px solid #ccc; padding: 5px;")
        self.hk_shw_edit.setStyleSheet("background: #ffffff; border: 1px solid #ccc; padding: 5px;")
        
        # Blocker wieder aktivieren
        self.rebind_pending = True
        self.hotkeys_active = True

    def parse_hotkey(self, hotkey_str):
        mods = 0; key = 0
        parts = hotkey_str.lower().replace(" ", "").split("+")
        for p in parts:
            if "win" in p: mods |= MOD_WIN
            elif "alt" in p: mods |= MOD_ALT
            elif "ctrl" in p or "strg" in p: mods |= MOD_CONTROL
            elif "shift" in p: mods |= MOD_SHIFT
            elif len(p) == 1: key = ord(p.upper())
            elif p == "space": key = 0x20
        return mods, key

    def windows_api_loop(self):
        user32 = windll.user32
        msg = wintypes.MSG()
        while True:
            if self.rebind_pending and self.hotkeys_active:
                # Clean up any old registrations
                user32.UnregisterHotKey(None, 1)
                user32.UnregisterHotKey(None, 2)
                m1, k1 = self.parse_hotkey(self.settings["hotkey_record"])
                m2, k2 = self.parse_hotkey(self.settings["hotkey_show"])
                ok1 = user32.RegisterHotKey(None, 1, m1, k1)
                # Wenn beide Hotkeys auf dieselbe Kombination aufgelöst werden, registriere nur den ersten und warne
                if (m1, k1) == (m2, k2):
                    ok2 = False
                    print(f"[Hotkey] Warning: both hotkeys resolve to same combo (mods={m1} key={k1}). Skipping registration of second.")
                    self.signals.status.emit("Hotkey-Konflikt: beide Hotkeys sind gleich. Bitte ändere einen Hotkey.")
                else:
                    ok2 = user32.RegisterHotKey(None, 2, m2, k2)

                if not ok1:
                    err = windll.kernel32.GetLastError()
                    reg_msg = f"RegisterHotKey 1 FAILED for {self.settings['hotkey_record']} (mods={m1} key={k1}) err={err}"
                    print(f"[Hotkey] {reg_msg}")
                    if err == 1409:
                        self.signals.status.emit("Hotkey 1 already registered by another app. Choose another combo.")
                    else:
                        self.signals.status.emit(f"Hotkey 1 registration failed: {err}")
                else:
                    print(f"[Hotkey] Registered 1: {self.settings['hotkey_record']} (mods={m1} key={k1})")

                if not ok2:
                    err = windll.kernel32.GetLastError()
                    print(f"[Hotkey] RegisterHotKey 2 FAILED for {self.settings['hotkey_show']} (mods={m2} key={k2}) err={err}")
                    if err == 1409:
                        self.signals.status.emit("Hotkey 2 already registered by another app. Choose another combo.")
                    else:
                        # If we skipped due to duplication, err may be 0 - handle gracefully
                        if err:
                            self.signals.status.emit(f"Hotkey 2 registration failed: {err}")
                else:
                    print(f"[Hotkey] Registered 2: {self.settings['hotkey_show']} (mods={m2} key={k2})")
                self.rebind_pending = False
            
            if not self.hotkeys_active:
                import time; time.sleep(0.1); continue

            if user32.PeekMessageW(byref(msg), None, 0, 0, 1):
                try:
                    if msg.message == WM_HOTKEY:
                        wparam = int(msg.wParam)
                        lparam = int(msg.lParam)
                        print(f"[Hotkey] WM_HOTKEY received wParam={wparam} lParam={lparam}")
                        if wparam == 1:
                            print("[Hotkey] Emitting trigger_record")
                            self.signals.trigger_record.emit()
                            self.signals.status.emit("Hotkey: Aufnahme")
                        if wparam == 2:
                            print("[Hotkey] Emitting trigger_window")
                            self.signals.trigger_window.emit()
                            self.signals.status.emit("Hotkey: Fenster Toggle")
                except Exception as e:
                    print(f"[Hotkey] Error handling message: {e}")
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))
            import time; time.sleep(0.01)

    def toggle_window_visibility(self):
        if self.isVisible() and self.isActiveWindow():
            self.hide()
        else:
            self.show(); self.showNormal(); self.activateWindow(); self.raise_()
            windll.user32.SetForegroundWindow(self.winId().__int__())

    def on_mode_changed(self, index):
        map_m = {0: ("local", "base"), 1: ("local", "small"), 2: ("local", "medium"), 3: ("local", "large-v3"), 4: ("api", "")}
        m, s = map_m[index]; self.settings["active_mode"] = m
        if s: self.settings["local_model_size"] = s
        self.save_settings(); threading.Thread(target=self.manage_model_loading, daemon=True).start()

    def manage_model_loading(self):
        if self.settings["active_mode"] == "api": self.signals.status.emit("✓ API bereit"); return
        size = self.settings["local_model_size"]; self.signals.status.emit(f"Lade {size}...")
        self.local_model = whisper.load_model(size); self.signals.status.emit(f"✓ Modell {size} bereit")

    def toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True; self.recording_data = []; self.record_btn.setText("STOPP")
            self.record_btn.setStyleSheet("background: red; color: white;"); self.signals.status.emit("🔴 Aufnahme...")
            threading.Thread(target=self.record_loop, daemon=True).start()
        else:
            self.is_recording = False; self.record_btn.setText("Aufnahme Start/Stopp")
            self.record_btn.setStyleSheet(""); self.signals.status.emit("⌛ Verarbeite...")

    def record_loop(self):
        with sd.InputStream(samplerate=16000, channels=1, callback=lambda i,f,t,s: self.recording_data.append(i.copy())):
            while self.is_recording: sd.sleep(100)
        self.run_transcription()

    def run_transcription(self):
        try:
            audio = np.concatenate(self.recording_data, axis=0).astype(np.float32).flatten()
            if self.settings["active_mode"] == "api" and self.settings["api_key"]:
                client = OpenAI(api_key=self.settings["api_key"])
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    sf.write(tmp.name, audio, 16000)
                    with open(tmp.name, "rb") as f:
                        text = client.audio.transcriptions.create(model="whisper-1", file=f).text
                os.remove(tmp.name)
            else: text = self.local_model.transcribe(audio, language="de")["text"]
            self.signals.finished.emit(text.strip())
        except Exception as e: self.signals.finished.emit(f"Fehler: {e}")

    def process_result(self, text):
        self.text_area.clear()
        self.text_area.setPlainText(text)
        if self.settings.get("auto_copy"): pyperclip.copy(text)
        self.signals.status.emit("✅ Fertig!")

    def update_setting(self, k, v): self.settings[k] = v; self.save_settings()

    def init_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
        m = QMenu(); m.addAction("Öffnen", self.showNormal); m.addAction("Beenden", QApplication.instance().quit)
        self.tray.setContextMenu(m); self.tray.show()

    def update_status_ui(self, text):
        self.status_label.setText(text)
        self.status_label.setStyleSheet("background: #e8f5e9; padding: 10px; font-weight: bold; border-radius: 5px;")

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
    window = SnapScribe(); window.show(); sys.exit(app.exec())