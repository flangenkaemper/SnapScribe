import sys
import threading
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal

from ui.splash import SplashScreen
from ui.main_window import MainWindow
from logic.backend import ConfigManager, AudioTranscriber
from logic.hotkeys import GlobalHotkeyManager

class Launcher(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(str, int)

    def __init__(self, splash, transcriber):
        super().__init__()
        self.splash = splash
        self.transcriber = transcriber
        self.progress.connect(self.splash.update_progress)

    def run(self):
        self.transcriber.load_model(progress_callback=self.progress)
        self.finished.emit()

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    config = ConfigManager()
    transcriber = AudioTranscriber(config)

    hk_manager = GlobalHotkeyManager(config)
    hk_manager.start()

    splash = SplashScreen()
    splash.show()
    
    # WICHTIG: Hier übergeben wir jetzt hk_manager!
    main_window = MainWindow(config, transcriber, hk_manager)

    hk_manager.trigger_record.connect(main_window.toggle_record)
    
    def toggle_window_visibility():
        if main_window.isVisible() and main_window.isActiveWindow():
            main_window.hide()
        else:
            main_window.showNormal()
            main_window.activateWindow()
            main_window.raise_()
            
    hk_manager.trigger_show.connect(toggle_window_visibility)

    launcher = Launcher(splash, transcriber)
    
    def on_loaded():
        splash.close()
        if config.get("minimize_to_tray"):
             # Optional: Nur Tray, oder einmal zeigen beim Start.
             # Hier zeigen wir es einmal, damit der User weiß "es lebt".
             main_window.show()
        else:
             main_window.show()

    launcher.finished.connect(on_loaded)
    
    t = threading.Thread(target=launcher.run, daemon=True)
    t.start()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()