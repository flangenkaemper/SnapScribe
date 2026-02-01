import sys
import os
import tempfile
import threading
import sounddevice as sd
import soundfile as sf
import numpy as np
import whisper  # Wir nutzen jetzt das offizielle Whisper
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, 
                             QWidget, QPushButton, QTextEdit, QLabel)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

class TranscriberSignals(QObject):
    finished = pyqtSignal(str)
    status = pyqtSignal(str)

class TranscriptionApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SnapScribe (Robust Version)")
        self.setGeometry(100, 100, 500, 400)

        layout = QVBoxLayout()
        self.status_label = QLabel("Warte auf Modell...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        self.text_area = QTextEdit()
        layout.addWidget(self.text_area)

        self.record_btn = QPushButton("Aufnahme starten")
        self.record_btn.setFixedHeight(50)
        self.record_btn.clicked.connect(self.toggle_recording)
        self.record_btn.setEnabled(False) 
        layout.addWidget(self.record_btn)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.is_recording = False
        self.recording_data = []
        self.sample_rate = 16000
        self.model = None

        self.signals = TranscriberSignals()
        self.signals.finished.connect(self.update_text)
        self.signals.status.connect(self.status_label.setText)

        # Start loading
        threading.Thread(target=self.load_model, daemon=True).start()

    def load_model(self):
        try:
            print("Lade Whisper Modell (tiny)...")
            # tiny ist ca. 75MB und sehr schnell
            self.model = whisper.load_model("tiny")
            print("Modell geladen!")
            self.signals.status.emit("Bereit! Drücke Aufnahme.")
            self.record_btn.setEnabled(True)
        except Exception as e:
            print(f"Fehler beim Laden: {e}")
            self.signals.status.emit(f"Fehler: {str(e)}")

    def toggle_recording(self):
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        self.is_recording = True
        self.record_btn.setText("Stopp & Transkribieren")
        self.record_btn.setStyleSheet("background-color: #ffcccc;")
        self.recording_data = []
        threading.Thread(target=self.record_loop, daemon=True).start()

    def record_loop(self):
        with sd.InputStream(samplerate=self.sample_rate, channels=1, callback=self.audio_callback):
            while self.is_recording:
                sd.sleep(100)
        self.run_transcription()

    def audio_callback(self, indata, frames, time, status):
        if self.is_recording:
            self.recording_data.append(indata.copy())

    def stop_recording(self):
        self.is_recording = False
        self.record_btn.setText("Wird verarbeitet...")
        self.record_btn.setEnabled(False)

    def run_transcription(self):
        try:
            if not self.recording_data:
                self.signals.finished.emit("")
                return

            audio_np = np.concatenate(self.recording_data, axis=0).astype(np.float32).flatten()
            
            # Das offizielle Whisper kann direkt mit dem Array arbeiten!
            print("Transkription läuft...")
            result = self.model.transcribe(audio_np, language="de")
            text = result["text"]

            self.signals.finished.emit(text.strip())
        except Exception as e:
            print(f"Fehler bei Transkription: {e}")
            self.signals.finished.emit(f"Fehler: {str(e)}")

    def update_text(self, text):
        if text:
            current = self.text_area.toPlainText()
            self.text_area.setPlainText(f"{current}\n{text}".strip() if current else text)
        
        self.status_label.setText("Fertig.")
        self.record_btn.setText("Aufnahme starten")
        self.record_btn.setStyleSheet("")
        self.record_btn.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TranscriptionApp()
    window.show()
    sys.exit(app.exec())