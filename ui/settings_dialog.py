from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLineEdit, QHBoxLayout,
                             QCheckBox, QComboBox, QPushButton, QFormLayout, QMessageBox)
from PyQt6.QtCore import pyqtSignal, QTimer
from logic.backend import ConfigManager
from ui.widgets import HotkeyLineEdit
from ui import i18n as _i18n

class SettingsDialog(QDialog):
    settings_saved = pyqtSignal()

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.current_lang = config.get("language") or "en"
        self.setWindowTitle(_i18n.t("settings_title", self.current_lang))
        self.resize(400, 380)
        
        # Hier speichern wir die funktionierenden Werte vor dem Speichern
        self.backup_values = {}
        
        self.init_ui()
        self.load_ui_values()

    def init_ui(self):
        self.layout = QVBoxLayout()
        form = QFormLayout()

        self.combo_model = QComboBox()
        self.combo_model.addItems(["base", "small", "medium", "large-v3"])
        form.addRow("Lokales Modell:", self.combo_model)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["local", "api"])
        form.addRow("Modus:", self.combo_mode)

        self.inp_api = QLineEdit()
        self.inp_api.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("OpenAI API Key:", self.inp_api)

        self.inp_hk_rec = HotkeyLineEdit("")
        self.inp_hk_rec.hotkey_detected.connect(self.on_hotkey_rec_detected)
        form.addRow(_i18n.t("hotkey_record", self.current_lang), self.inp_hk_rec)
        
        self.inp_hk_show = HotkeyLineEdit("")
        self.inp_hk_show.hotkey_detected.connect(self.on_hotkey_show_detected)
        form.addRow(_i18n.t("hotkey_show", self.current_lang), self.inp_hk_show)

        # Sprache
        self.combo_lang = QComboBox()
        self.combo_lang.addItem(_i18n.t("english", "en"), "en")
        self.combo_lang.addItem(_i18n.t("german", "en"), "de")
        form.addRow(_i18n.t("language_label", self.current_lang), self.combo_lang)

        self.layout.addLayout(form)

        self.cb_copy = QCheckBox(_i18n.t("auto_copy", self.current_lang))
        self.layout.addWidget(self.cb_copy)
        
        self.cb_tray = QCheckBox(_i18n.t("minimize_tray", self.current_lang))
        self.layout.addWidget(self.cb_tray)

        btn_layout = QHBoxLayout()
        
        self.btn_save = QPushButton(_i18n.t("save", self.current_lang))
        self.btn_save.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_save.clicked.connect(self.save_settings)
        btn_layout.addWidget(self.btn_save)

        self.btn_cancel = QPushButton(_i18n.t("cancel_reset", self.current_lang))
        self.btn_cancel.clicked.connect(self.reset_settings)
        btn_layout.addWidget(self.btn_cancel)
        
        self.layout.addLayout(btn_layout)
        self.setLayout(self.layout)

    def load_ui_values(self):
        self.combo_model.setCurrentText(self.config.get("local_model_size"))
        self.combo_mode.setCurrentText(self.config.get("active_mode"))
        self.inp_api.setText(self.config.get("api_key"))
        
        self.inp_hk_rec.setText(self.config.get("hotkey_record"))
        self.inp_hk_show.setText(self.config.get("hotkey_show"))

        # Sprache laden (Code in data role)
        lang = self.config.get("language") or "en"
        idx = 0 if lang == "en" else 1
        self.combo_lang.setCurrentIndex(idx)
        
        self.cb_copy.setChecked(self.config.get("auto_copy"))
        self.cb_tray.setChecked(self.config.get("minimize_to_tray"))
        
        self.inp_hk_rec.setStyleSheet("background: #ffffff; border: 1px solid #ccc; padding: 5px;")
        self.inp_hk_show.setStyleSheet("background: #ffffff; border: 1px solid #ccc; padding: 5px;")

    def on_hotkey_rec_detected(self, hk):
        self.inp_hk_rec.setText(hk)
        self.inp_hk_rec.setStyleSheet("background: #e8f5e9; border: 1px solid #4CAF50; padding: 5px;")

    def on_hotkey_show_detected(self, hk):
        self.inp_hk_show.setText(hk)
        self.inp_hk_show.setStyleSheet("background: #e8f5e9; border: 1px solid #4CAF50; padding: 5px;")

    def save_settings(self):
        """Speichert die Werte, macht aber vorher ein Backup für den Fall eines Fehlers"""
        
        # 1. Backup erstellen (wir holen die Werte aus der Config, BEVOR wir überschreiben)
        self.backup_values["hotkey_record"] = self.config.get("hotkey_record")
        self.backup_values["hotkey_show"] = self.config.get("hotkey_show")
        
        # 2. Neue Werte speichern
        self.config.set("local_model_size", self.combo_model.currentText())
        self.config.set("active_mode", self.combo_mode.currentText())
        self.config.set("api_key", self.inp_api.text())
        self.config.set("hotkey_record", self.inp_hk_rec.text())
        self.config.set("hotkey_show", self.inp_hk_show.text())
        self.config.set("auto_copy", self.cb_copy.isChecked())
        self.config.set("minimize_to_tray", self.cb_tray.isChecked())
        
        # Sprache speichern (Datenrolle)
        lang_code = self.combo_lang.currentData()
        if lang_code:
            self.config.set("language", lang_code)
        
        # 3. Signalisieren
        self.settings_saved.emit()
        
        # Feedback Button
        original_text = self.btn_save.text()
        saved_text = _i18n.t("saved", self.config.get("language"))
        self.btn_save.setText(saved_text)
        QTimer.singleShot(1500, lambda: self.btn_save.setText(original_text))

    def reset_settings(self):
        """Lädt die Werte neu aus der Config (Verwirft ungespeicherte UI Änderungen)"""
        self.load_ui_values()

    def revert_change(self, key_type):
        """
        Wird aufgerufen, wenn der Hotkey-Manager einen Fehler meldet.
        Setzt Config und UI auf den Backup-Wert zurück.
        """
        if key_type in self.backup_values:
            old_val = self.backup_values[key_type]
            
            # Config zurücksetzen
            self.config.set(key_type, old_val)
            
            # UI zurücksetzen
            if key_type == "hotkey_record":
                self.inp_hk_rec.setText(old_val)
            elif key_type == "hotkey_show":
                self.inp_hk_show.setText(old_val)
                
            print(f"[Settings] Revert ausgeführt für {key_type} -> {old_val}")