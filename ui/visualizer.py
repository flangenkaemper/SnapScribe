from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QBrush

class AudioVisualizer(QWidget):
    """Zeichnet die Audio-Wellenform live"""
    def __init__(self):
        super().__init__()
        self.setFixedHeight(60)
        self.amplitudes = [0.0] * 50
        
        self.bar_color = QColor("#4CAF50")
        self.bg_color = QColor("#f0f0f0")

    def add_amplitude(self, val):
        val = min(val, 100.0) / 5.0 
        self.amplitudes.pop(0)
        self.amplitudes.append(val)
        self.update()

    # NEU: Methode zum Zurücksetzen
    def clear(self):
        self.amplitudes = [0.0] * 50
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        # Sicherheit: Division durch Null verhindern
        if len(self.amplitudes) == 0: return
        
        bar_width = w / len(self.amplitudes)
        
        painter.setBrush(QBrush(self.bar_color))
        painter.setPen(Qt.PenStyle.NoPen)

        for i, amp in enumerate(self.amplitudes):
            bar_h = max(2, amp * (h * 0.8))
            x = i * bar_width
            y = (h - bar_h) / 2
            
            gap = 1
            painter.drawRoundedRect(QRectF(x + gap, y, bar_width - gap*2, bar_h), 2, 2)

class RecordingOverlay(QWidget):
    """Kombiniert Visualizer und Timer"""
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        
        self.lbl_timer = QLabel("00:00")
        self.lbl_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_timer.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        layout.addWidget(self.lbl_timer)
        
        self.viz = AudioVisualizer()
        layout.addWidget(self.viz)
        
        self.setLayout(layout)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timer)
        self.seconds = 0

    def start(self):
        self.seconds = 0
        self.lbl_timer.setText("00:00")
        self.viz.clear() # Sicherstellen dass wir sauber starten
        self.timer.start(1000)

    def stop(self):
        self.timer.stop()
        self.viz.clear() # NEU: Sofort leeren beim Stoppen

    def update_timer(self):
        self.seconds += 1
        m, s = divmod(self.seconds, 60)
        self.lbl_timer.setText(f"{m:02d}:{s:02d}")

    def update_amplitude(self, val):
        self.viz.add_amplitude(val)