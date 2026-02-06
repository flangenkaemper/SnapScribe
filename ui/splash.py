# ui/splash.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon
from logic.backend import get_asset_path

class SplashScreen(QWidget):
    def __init__(self):
        super().__init__()
        # Frameless: Kein Fensterrahmen
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        
        self.resize(450, 300)
        self.center()
        
        # Layout ohne Lücken (Spacing = 0), damit alles wie aus einem Guss wirkt
        layout = QVBoxLayout()
        layout.setSpacing(0)             # Keine Lücke zwischen den Elementen
        layout.setContentsMargins(0,0,0,0) # Rand komplett füllen
        self.setLayout(layout)
        
        # Hintergrund-Style (Dunkelblau)
        # Wir setzen den Background direkt auf das Widget
        self.setStyleSheet("""
            SplashScreen { 
                background-color: #00205b; 
                border: 2px solid white; 
                border-radius: 10px; 
            }
            QLabel { color: white; background-color: #00205b; padding: 10px; }
            QProgressBar { 
                border: 2px solid white; 
                border-radius: 5px; 
                text-align: center; 
                color: black; 
                background: #eee; 
                margin: 20px; 
            }
            QProgressBar::chunk { background-color: #0099cc; }
        """)

        # 1. Logo
        self.logo_lbl = QLabel()
        self.logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Versuche Logo zu laden, sonst Text
        logo_path = get_asset_path("splash_logo.png")
        icon_path = get_asset_path("icon.ico")
        
        if icon_path: self.setWindowIcon(QIcon(icon_path))
        
        # Logo laden
        pix = QPixmap(logo_path)
        if not pix.isNull():
            # Skalieren wenn zu groß
            self.logo_lbl.setPixmap(pix.scaled(200, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.logo_lbl.setText("<h1>SnapScribe</h1>")
            
        layout.addWidget(self.logo_lbl)
        
        # 2. Status Text
        self.status_lbl = QLabel("Initialisiere...")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_lbl)
        
        # 3. Progress Bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        
        # Drag-Logic Variablen
        self.old_pos = None

    def update_progress(self, text, val):
        self.status_lbl.setText(text)
        self.progress.setValue(val)

    def center(self):
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    # --- Fix: Fenster verschieben statt schließen bei Klick ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None