import threading
import time
from ctypes import windll, wintypes, byref, get_last_error
from PyQt6.QtCore import QObject, pyqtSignal

# Windows Konstanten
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312

class GlobalHotkeyManager(QObject):
    trigger_record = pyqtSignal()
    trigger_show = pyqtSignal()
    # ÄNDERUNG: Signal sendet jetzt (Fehlernachricht, Key-Typ)
    registration_failed = pyqtSignal(str, str) 

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.running = True
        self.user32 = windll.user32
        self.reload_event = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
    
    def start(self):
        self.thread.start()

    def stop(self):
        self.running = False

    def update_hotkeys(self):
        self.reload_event.set()

    def _parse_hotkey(self, hotkey_str):
        mods = 0; key = 0
        if not hotkey_str: return 0, 0
        
        parts = hotkey_str.lower().replace(" ", "").split("+")
        for p in parts:
            if "win" in p: mods |= MOD_WIN
            elif "alt" in p: mods |= MOD_ALT
            elif "ctrl" in p or "strg" in p: mods |= MOD_CONTROL
            elif "shift" in p: mods |= MOD_SHIFT
            elif len(p) == 1: key = ord(p.upper())
            elif p == "space": key = 0x20
            elif p == "enter": key = 0x0D
            elif p == "tab": key = 0x09
            elif p == "esc": key = 0x1B
            elif p.startswith("f") and p[1:].isdigit():
                f_val = int(p[1:])
                if 1 <= f_val <= 24: key = 0x70 + (f_val - 1)
        return mods, key

    def _register_current(self):
        hk_rec = self.config.get("hotkey_record")
        hk_show = self.config.get("hotkey_show")
        
        m1, k1 = self._parse_hotkey(hk_rec)
        m2, k2 = self._parse_hotkey(hk_show)
        
        self.user32.UnregisterHotKey(None, 1)
        self.user32.UnregisterHotKey(None, 2)
        
        # 1. Record Hotkey
        if k1:
            if not self.user32.RegisterHotKey(None, 1, m1, k1):
                # ÄNDERUNG: Neutrale Meldung ohne Python-Hinweis
                msg = f"Der Hotkey '{hk_rec}' für die Aufnahme konnte nicht registriert werden.\nEr wird bereits von einem anderen Programm verwendet."
                self.registration_failed.emit(msg, "hotkey_record")
        
        # 2. Show Hotkey
        if k2:
            if not self.user32.RegisterHotKey(None, 2, m2, k2):
                msg = f"Der Hotkey '{hk_show}' für das Fenster konnte nicht registriert werden.\nEr wird bereits von einem anderen Programm verwendet."
                self.registration_failed.emit(msg, "hotkey_show")

    def _loop(self):
        msg = wintypes.MSG()
        self._register_current()

        while self.running:
            if self.reload_event.is_set():
                self._register_current()
                self.reload_event.clear()

            if self.user32.PeekMessageW(byref(msg), None, 0, 0, 1):
                if msg.message == WM_HOTKEY:
                    if int(msg.wParam) == 1:
                        self.trigger_record.emit()
                    elif int(msg.wParam) == 2:
                        self.trigger_show.emit()
                self.user32.TranslateMessage(byref(msg))
                self.user32.DispatchMessageW(byref(msg))
            time.sleep(0.05)