import json
import os
import threading
import time
from PyQt6.QtCore import QObject, pyqtSignal

SETTINGS_FILE = "settings.json"

class WorkerSignals(QObject):
    finished = pyqtSignal(str)
    status = pyqtSignal(str)
    progress = pyqtSignal(str, int)
    error = pyqtSignal(str)
    amplitude = pyqtSignal(float)  # <--- NEU: Sendet Lautstärkepegel an GUI

class ConfigManager:
    def __init__(self):
        self.default = {
            "api_key": "", "active_mode": "local", "auto_copy": True,
            "minimize_to_tray": True, "hotkey_record": "windows+shift+q",
            "hotkey_show": "windows+shift+d", "local_model_size": "base",
            "language": "en"
        }
        self.settings = self.load()

    def load(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    return {**self.default, **json.loads(f.read())}
            except: pass
        return self.default.copy()

    def save(self):
        with open(SETTINGS_FILE, "w") as f:
            json.dump(self.settings, f, indent=4)
            
    def get(self, key): return self.settings.get(key)
    def set(self, key, val): self.settings[key] = val; self.save()

class AudioTranscriber:
    def __init__(self, config):
        self.config = config
        self.model = None
        self.recording = False
        self.transcribing = False # NEU: Status für Transkription
        self.cancel_flag = False    # NEU: Abbruch-Flag
        self.data = []
        self.signals = WorkerSignals()
        
        self.sd = None
        self.np = None
        self.whisper = None

    def load_model(self, progress_callback=None):
        mode = self.config.get("active_mode")
        
        if self.sd is None:
            if progress_callback: progress_callback.emit("Lade Audio-Treiber...", 10)
            import sounddevice; self.sd = sounddevice
            import numpy; self.np = numpy
            import soundfile; self.sf = soundfile

        if mode == "api": return
        
        if self.whisper is None:
            if progress_callback: progress_callback.emit("Lade AI-Engine...", 30)
            import whisper; self.whisper = whisper
        
        size = self.config.get("local_model_size")
        if not self.model:
            if progress_callback: progress_callback.emit(f"Lade Modell {size}...", 50)
            self.model = self.whisper.load_model(size)
            
        if progress_callback: progress_callback.emit("Bereit!", 100)

    def start_recording(self):
        if self.sd is None: 
            import sounddevice; self.sd = sounddevice
            import numpy; self.np = numpy

        self.recording = True
        self.cancel_flag = False
        self.data = []
        threading.Thread(target=self._record_loop, daemon=True).start()

    def stop_recording(self):
        self.recording = False

    def cancel_process(self):
        """Bricht Aufnahme ODER Transkription ab"""
        self.cancel_flag = True
        self.recording = False
        # Info: Die Transkription selbst (whisper.transcribe) läuft im C++ Kern und lässt sich schwer
        # "sofort" killen, aber wir ignorieren das Ergebnis danach einfach.

    def _record_loop(self):
        def callback(indata, frames, time, status):
            if self.recording:
                self.data.append(indata.copy())
                # Lautstärke berechnen (RMS) und an GUI senden für Visualisierung
                volume_norm = self.np.linalg.norm(indata) * 10
                self.signals.amplitude.emit(volume_norm)

        with self.sd.InputStream(samplerate=16000, channels=1, callback=callback):
            while self.recording:
                self.sd.sleep(50)
        
        # Wenn abgebrochen wurde, gar nicht erst transkribieren
        if not self.cancel_flag:
            self._transcribe()
        else:
            self.signals.status.emit("Abgebrochen")
            self.signals.finished.emit("") # Leeres Ergebnis senden zum Resetten

    def _transcribe(self):
        self.transcribing = True
        self.signals.status.emit("Verarbeite...")
        # Startsignal für Ladeanimation (wir nutzen progress mit -1 als Code für "Indeterminate/Laden")
        self.signals.progress.emit("Transkribiere...", -1) 
        
        try:
            if not self.data: return

            audio = self.np.concatenate(self.data, axis=0).astype(self.np.float32).flatten()
            
            # API oder Lokal
            if self.config.get("active_mode") == "api":
                # ... API Logik ...
                text = "API Dummy Text"
                time.sleep(2) # Simuliere Ladezeit
            else:
                if not self.model: self.load_model()
                # Hier läuft die Berechnung. Wir checken danach, ob abgebrochen wurde.
                result = self.model.transcribe(audio, language="de")
                text = result["text"]
            
            self.transcribing = False
            
            # Check ob USER währenddessen abgebrochen hat
            if self.cancel_flag:
                self.signals.status.emit("Abgebrochen")
                self.signals.finished.emit("")
            else:
                self.signals.finished.emit(text.strip())
                
        except Exception as e:
            self.transcribing = False
            self.signals.finished.emit(f"Fehler: {e}")

def get_asset_path(filename):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, 'assets', filename)