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
from openai import OpenAI
from pynput import keyboard
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, 
                             QWidget, QPushButton, QTextEdit, QLabel, 
                             QLineEdit, QCheckBox, QSystemTrayIcon, QMenu, QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

SETTINGS_FILE = "settings.json"

class AppSignals(QObject):
    finished = pyqtSignal(str)
    status = pyqtSignal(str)
    trigger_record = pyqtSignal()
    show_window = pyqtSignal()

class SnapScribe(QMainWindow):
    def __init__(self):
        super().__init__()
        self.load_settings()
        
        self.is_recording = False
        self.recording_data = []
        self.sample_rate = 16000
        self.local_model = None
        self.current_model_name = None

        self.signals = AppSignals()
        self.signals.finished.connect(self.process_result)
        self.signals.status.connect(self.update_status_ui)
        self.signals.trigger_record.connect(self.toggle_recording)
        self.signals.show_window.connect(self.show_normal)

        self.init_ui()
        self.init_tray()

        # Hotkey Listener in separatem Thread
        self.hotkey_listener = None
        self.start_hotkey_listener()

        # Modell-Initialisierung
        threading.Thread(target=self.manage_model_loading, daemon=True).start()

    def load_settings(self):
        default_settings = {
            "api_key": "",
            "active_mode": "local", # "local" oder "api"
            "auto_copy": True,
            "minimize_to_tray": True,
            "hotkey_record": "<ctrl>+<alt>+s",
            "hotkey_show": "<ctrl>+<alt>+o",
            "local_model_size": "base"
        }
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    content = f.read().strip()
                    self.settings = {**default_settings, **json.loads(content)} if content else default_settings
            except Exception:
                self.settings = default_settings
        else:
            self.settings = default_settings
        self.save_settings()

    def save_settings(self):
        with open(SETTINGS_FILE, "w") as f:
            json.dump(self.settings, f, indent=4)

    def init_ui(self):
        self.setWindowTitle("SnapScribe Pro")
        self.setGeometry(100, 100, 450, 600)
        
        container = QWidget()
        layout = QVBoxLayout()

        self.status_label = QLabel("Initialisierung...")
        self.status_label.setStyleSheet("font-weight: bold; color: #0078d7;")
        layout.addWidget(self.status_label)

        self.text_area = QTextEdit()
        self.text_area.setPlaceholderText("Transkribierter Text erscheint hier...")
        layout.addWidget(self.text_area)

        # Modus Auswahl
        layout.addWidget(QLabel("Transkriptions-Quelle:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Lokal: Base (Schnell)", "Lokal: Small (Besser)", "Lokal: Medium (Sehr gut)", "OpenAI API (Perfekt)"])
        
        # Mapping für Settings
        self.mode_map = {
            0: ("local", "base"),
            1: ("local", "small"),
            2: ("local", "medium"),
            3: ("api", "")
        }
        
        # Aktuellen Index setzen
        if self.settings["active_mode"] == "api":
            self.mode_combo.setCurrentIndex(3)
        else:
            size = self.settings["local_model_size"]
            idx = 0 if size == "base" else 1 if size == "small" else 2
            self.mode_combo.setCurrentIndex(idx)
            
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        layout.addWidget(self.mode_combo)

        # API Key
        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText("OpenAI API Key einfügen...")
        self.api_input.setText(self.settings["api_key"])
        self.api_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_input.textChanged.connect(self.on_api_key_changed)
        layout.addWidget(self.api_input)

        # Checkboxes
        self.cb_copy = QCheckBox("Auto-Copy in Zwischenablage")
        self.cb_copy.setChecked(self.settings["auto_copy"])
        self.cb_copy.stateChanged.connect(lambda: self.update_setting("auto_copy", self.cb_copy.isChecked()))
        layout.addWidget(self.cb_copy)

        self.cb_tray = QCheckBox("In Tray minimieren statt schließen")
        self.cb_tray.setChecked(self.settings["minimize_to_tray"])
        self.cb_tray.stateChanged.connect(lambda: self.update_setting("minimize_to_tray", self.cb_tray.isChecked()))
        layout.addWidget(self.cb_tray)

        # Buttons
        self.record_btn = QPushButton("Aufnahme Starten/Stoppen (Ctrl+Alt+S)")
        self.record_btn.setFixedHeight(50)
        self.record_btn.clicked.connect(self.toggle_recording)
        layout.addWidget(self.record_btn)

        container.setLayout(layout)
        self.setCentralWidget(container)

    def on_mode_changed(self, index):
        mode, size = self.mode_map[index]
        self.settings["active_mode"] = mode
        if size: self.settings["local_model_size"] = size
        self.save_settings()
        threading.Thread(target=self.manage_model_loading, daemon=True).start()

    def on_api_key_changed(self, text):
        self.settings["api_key"] = text
        self.save_settings()

    def update_setting(self, key, value):
        self.settings[key] = value
        self.save_settings()

    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
        menu = QMenu()
        menu.addAction("Öffnen", self.show_normal)
        menu.addSeparator()
        menu.addAction("Beenden", QApplication.instance().quit)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def closeEvent(self, event):
        if self.settings["minimize_to_tray"]:
            event.ignore()
            self.hide()
        else:
            event.accept()

    def show_normal(self):
        self.show()
        self.activateWindow()

    def start_hotkey_listener(self):
        def run():
            with keyboard.GlobalHotkeys({
                self.settings["hotkey_record"]: lambda: self.signals.trigger_record.emit(),
                self.settings["hotkey_show"]: lambda: self.signals.show_window.emit()
            }) as h:
                h.join()
        threading.Thread(target=run, daemon=True).start()

    def manage_model_loading(self):
        if self.settings["active_mode"] == "api":
            self.signals.status.emit("Modus: OpenAI API bereit")
        else:
            size = self.settings["local_model_size"]
            if self.local_model is not None and self.current_model_name == size:
                self.signals.status.emit(f"Bereit (Lokal: {size})")
                return
                
            self.signals.status.emit(f"Lade Modell {size}...")
            try:
                self.local_model = whisper.load_model(size)
                self.current_model_name = size
                self.signals.status.emit(f"Bereit (Lokal: {size})")
            except Exception as e:
                self.signals.status.emit(f"Ladefehler: {e}")

    def toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True
            self.recording_data = []
            self.record_btn.setStyleSheet("background-color: #ff4d4d; color: white; font-weight: bold;")
            self.signals.status.emit("Aufnahme läuft...")
            threading.Thread(target=self.record_loop, daemon=True).start()
        else:
            self.is_recording = False
            self.record_btn.setStyleSheet("")
            self.signals.status.emit("Verarbeite Audio...")

    def record_loop(self):
        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=1, callback=self.audio_callback):
                while self.is_recording:
                    sd.sleep(100)
            self.run_transcription()
        except Exception as e:
            self.signals.status.emit(f"Mikro-Fehler: {e}")

    def audio_callback(self, indata, frames, time, status):
        if self.is_recording:
            self.recording_data.append(indata.copy())

    def run_transcription(self):
        try:
            if not self.recording_data: return
            audio_np = np.concatenate(self.recording_data, axis=0).astype(np.float32).flatten()
            
            if self.settings["active_mode"] == "api" and self.settings["api_key"]:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    temp_fn = tmp.name
                sf.write(temp_fn, audio_np, self.sample_rate)
                client = OpenAI(api_key=self.settings["api_key"])
                with open(temp_fn, "rb") as f:
                    transcript = client.audio.transcriptions.create(model="whisper-1", file=f)
                text = transcript.text
                os.remove(temp_fn)
            else:
                result = self.local_model.transcribe(audio_np, language="de")
                text = result["text"]

            self.signals.finished.emit(text.strip())
        except Exception as e:
            self.signals.finished.emit(f"Fehler: {str(e)}")

    def process_result(self, text):
        if text:
            self.text_area.append(f"<b>Transkript:</b> {text}")
            if self.settings["auto_copy"]:
                pyperclip.copy(text)
                self.signals.status.emit("Kopiert!")
            else:
                self.signals.status.emit("Fertig.")
        else:
            self.signals.status.emit("Keine Sprache erkannt.")

    def update_status_ui(self, text):
        self.status_label.setText(text)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = SnapScribe()
    window.show()
    sys.exit(app.exec())