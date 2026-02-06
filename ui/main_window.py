import threading
import pyperclip
from PyQt6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget, QPushButton, 
                             QTextEdit, QLabel, QHBoxLayout, QSystemTrayIcon, QMenu, QApplication, QMessageBox,
                             QStackedWidget, QProgressBar, QFrame)
from PyQt6.QtCore import Qt, QSize, QPoint, QTimer
from PyQt6.QtGui import QIcon, QAction, QCursor, QColor

from ui.settings_dialog import SettingsDialog
from ui.visualizer import RecordingOverlay
from logic.backend import get_asset_path

class MainWindow(QMainWindow):
    def __init__(self, config, transcriber, hk_manager):
        super().__init__()
        self.config = config
        self.transcriber = transcriber
        self.hk_manager = hk_manager
        
        self.shown_tray_message = False
        
        self.transcriber.signals.finished.connect(self.on_transcription_finished)
        self.transcriber.signals.status.connect(self.update_status)
        self.transcriber.signals.progress.connect(self.handle_progress)
        self.transcriber.signals.amplitude.connect(self.update_visualizer)
        
        self.hk_manager.registration_failed.connect(self.on_hotkey_error)

        self.init_ui()
        self.init_tray()

    def init_ui(self):
        self.setWindowTitle("SnapScribe")
        self.setFixedWidth(420)
        
        icon_path = get_asset_path("icon.ico")
        if icon_path: self.setWindowIcon(QIcon(icon_path))

        container = QWidget()
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(15, 15, 15, 15)

        # 1. Header
        header = QHBoxLayout()
        self.lbl_status = QLabel("Bereit")
        self.lbl_status.setStyleSheet("color: #666;")
        header.addWidget(self.lbl_status)
        
        btn_settings = QPushButton("⚙")
        btn_settings.setFixedSize(30, 30)
        btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_settings.setStyleSheet("QPushButton { border: none; color: #888; font-size: 16px; } QPushButton:hover { color: #333; }")
        btn_settings.clicked.connect(self.open_settings)
        header.addWidget(btn_settings)
        self.layout.addLayout(header)

        # 2. Main Area (Stack)
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: white; border-radius: 8px; border: 1px solid #e0e0e0;")
        
        # Seite 1: Text Area
        self.text_area = QTextEdit()
        self.text_area.setPlaceholderText("Transkription erscheint hier...")
        self.text_area.setMinimumHeight(80)
        self.text_area.setFrameShape(QFrame.Shape.NoFrame)
        self.text_area.textChanged.connect(self.adjust_text_height)
        self.stack.addWidget(self.text_area)
        
        # Seite 2: Recording Overlay
        self.rec_overlay = RecordingOverlay()
        self.stack.addWidget(self.rec_overlay)
        
        self.layout.addWidget(self.stack)

        # 3. Loading Bar
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setFixedHeight(4)
        self.loading_bar.setStyleSheet("QProgressBar { border: 0px; background: #eee; } QProgressBar::chunk { background: #4CAF50; }")
        self.loading_bar.hide()
        self.layout.addWidget(self.loading_bar)

        # 4. Controls
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 10, 0, 0)
        
        # LINKS: Abbrechen
        self.btn_cancel = QPushButton("✕")
        self.btn_cancel.setFixedSize(50, 50)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setStyleSheet("""
            QPushButton { background-color: transparent; color: #888; border-radius: 25px; font-weight: bold; font-size: 20px; border: 1px solid #eee; }
            QPushButton:hover { background-color: #ffebee; color: #f44336; border-color: #ffcdd2; }
        """)
        self.btn_cancel.clicked.connect(self.cancel_process)
        self.btn_cancel.hide()
        controls_layout.addWidget(self.btn_cancel)
        
        controls_layout.addStretch()

        # MITTE: REC Indikator
        self.rec_indicator = QLabel("🔴 REC")
        self.rec_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rec_indicator.setStyleSheet("""
            font-weight: bold; color: #d32f2f; font-size: 14px; padding: 5px 15px; background-color: #ffebee; border-radius: 15px;
        """)
        self.rec_indicator.hide()
        controls_layout.addWidget(self.rec_indicator)
        
        controls_layout.addStretch()

        # RECHTS: Aktion
        self.action_container = QStackedWidget()
        self.action_container.setFixedSize(50, 50)
        
        # Mic
        self.btn_mic = QPushButton("🎤")
        self.btn_mic.setFixedSize(50, 50)
        self.btn_mic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mic.setStyleSheet("""
            QPushButton { background-color: transparent; color: #00205b; border-radius: 25px; font-size: 24px; border: 1px solid #eee; }
            QPushButton:hover { background-color: #e3f2fd; border-color: #bbdefb; }
        """)
        self.btn_mic.clicked.connect(self.toggle_record)
        self.action_container.addWidget(self.btn_mic)
        
        # Confirm
        self.btn_confirm = QPushButton("✓")
        self.btn_confirm.setFixedSize(50, 50)
        self.btn_confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm.setStyleSheet("""
            QPushButton { background-color: transparent; color: #4CAF50; border-radius: 25px; font-weight: bold; font-size: 24px; border: 1px solid #eee; }
            QPushButton:hover { background-color: #e8f5e9; border-color: #c8e6c9; }
        """)
        self.btn_confirm.clicked.connect(self.finish_recording)
        self.action_container.addWidget(self.btn_confirm)
        
        controls_layout.addWidget(self.action_container)

        self.layout.addLayout(controls_layout)

        container.setLayout(self.layout)
        self.setCentralWidget(container)
        self.adjust_text_height()

    # --- Logik ---

    def toggle_record(self):
        if not self.transcriber.recording:
            self.transcriber.start_recording()
            
            self.stack.setCurrentWidget(self.rec_overlay)
            self.rec_overlay.start()
            
            self.btn_cancel.show()
            self.rec_indicator.show()
            self.action_container.setCurrentWidget(self.btn_confirm)
            
            self.lbl_status.setText("Aufnahme läuft...")
            self.stack.setFixedHeight(120) 

    def finish_recording(self):
        if self.transcriber.recording:
            self.transcriber.stop_recording()
            self.rec_overlay.stop()
            self.reset_ui_state_to_loading()

    def cancel_process(self):
        """Bricht alles ab"""
        # 1. Backend stoppen
        self.transcriber.cancel_process()
        
        # 2. GUI Elemente HART stoppen
        self.rec_overlay.stop() # Timer aus, Daten löschen
        self.loading_bar.hide()
        
        # 3. Ansicht erzwingen
        self.stack.setCurrentWidget(self.text_area)
        
        # 4. Buttons resetten
        self.reset_buttons_default()
        self.lbl_status.setText("Abgebrochen")
        self.adjust_text_height()

    def reset_ui_state_to_loading(self):
        self.action_container.hide()
        self.rec_indicator.hide()
        self.btn_cancel.show()
        
        self.stack.setCurrentWidget(self.text_area)
        self.lbl_status.setText("Warte auf Transkription...")

    def reset_buttons_default(self):
        self.btn_cancel.hide()
        self.rec_indicator.hide()
        self.action_container.show()
        self.action_container.setCurrentWidget(self.btn_mic)

    def handle_progress(self, text, val):
        if val == -1: 
            self.loading_bar.show()
            self.lbl_status.setText(text)
        else:
            self.lbl_status.setText(f"{text} ({val}%)")

    def update_visualizer(self, amp):
        # WICHTIG: Nur updaten, wenn wir wirklich im Aufnahme-Screen sind!
        # Das verhindert den "Mix-State", falls ein spätes Signal reinfliegt.
        if self.transcriber.recording and self.stack.currentWidget() == self.rec_overlay:
            self.rec_overlay.update_amplitude(amp)

    def on_transcription_finished(self, text):
        self.loading_bar.hide()
        self.reset_buttons_default()
        
        if text: 
            self.lbl_status.setText("✅ Fertig")
            self.text_area.setPlainText(text)
            if self.config.get("auto_copy"): pyperclip.copy(text)
        else:
            self.lbl_status.setText("Bereit")
            
        self.adjust_text_height()
        self.showNormal()
        self.activateWindow()
        self.raise_()

    # --- Rest bleibt gleich ---
    
    def on_hotkey_error(self, msg, key_type):
        QMessageBox.warning(self, "Hotkey Konflikt", msg)
        if self.settings_dlg and self.settings_dlg.isVisible():
            self.settings_dlg.revert_change(key_type)
            self.hk_manager.update_hotkeys()

    def closeEvent(self, event):
        if self.config.get("minimize_to_tray"):
            event.ignore()
            self.hide()
            if not self.shown_tray_message:
                self.tray.showMessage("SnapScribe", "Läuft im Hintergrund weiter", QSystemTrayIcon.MessageIcon.Information, 2000)
                self.shown_tray_message = True
        else:
            self.close_app()
            event.accept()

    def update_status(self, msg):
        self.lbl_status.setText(msg)

    def adjust_text_height(self):
        if self.transcriber.recording: return 
        doc_height = self.text_area.document().size().height()
        new_h = int(min(max(80, doc_height + 10), 400))
        self.stack.setFixedHeight(new_h)
        self.adjustSize()

    def open_settings(self):
        self.settings_dlg = SettingsDialog(self.config, self)
        self.settings_dlg.settings_saved.connect(self.on_settings_changed)
        self.settings_dlg.exec()

    def on_settings_changed(self):
        self.update_status("Einstellungen gespeichert.")
        self.hk_manager.update_hotkeys()
        threading.Thread(target=self._reload_model_thread, daemon=True).start()

    def _reload_model_thread(self):
        self.transcriber.model = None 
        self.transcriber.load_model(progress_callback=self.transcriber.signals.progress)
        self.transcriber.signals.status.emit("Bereit")

    def init_tray(self):
        self.tray = QSystemTrayIcon(self)
        icon_path = get_asset_path("icon.ico")
        if icon_path: self.tray.setIcon(QIcon(icon_path))
        self.tray_menu = QMenu()
        title_action = QAction("SnapScribe", self)
        title_action.setEnabled(False)
        self.tray_menu.addAction(title_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction("Öffnen", self.showNormal)
        self.tray_menu.addAction("Beenden", self.close_app)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Context:
            cursor_pos = QCursor.pos()
            menu_size = self.tray_menu.sizeHint()
            new_pos = QPoint(cursor_pos.x(), cursor_pos.y() - menu_size.height())
            self.tray_menu.exec(new_pos)
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.showNormal()
            self.activateWindow()
            self.raise_()

    def close_app(self):
        self.tray.hide()
        QApplication.instance().quit()