# Internationalization (i18n) Module für SnapScribe
# Unterstützt multiple Sprachen mit einfacher Schlüsselwert-Struktur

from typing import Dict

_translations: Dict[str, Dict[str, str]] = {
    "en": {
        "ready": "Ready",
        "recording": "Recording...",
        "waiting_transcription": "Waiting for transcription...",
        "saved": "Saved! ✓",
        "finished": "✅ Done",
        "settings_title": "SnapScribe Settings",
        "hotkey_record": "Hotkey Record:",
        "hotkey_show": "Hotkey Window:",
        "language_label": "Language:",
        "english": "English",
        "german": "Deutsch",
        "open": "Open",
        "exit": "Exit",
        "cancel_reset": "Cancel (Reset)",
        "save": "Save",
        "auto_copy": "Auto copy text",
        "minimize_tray": "Minimize to tray",
        "settings_saved": "Settings saved.",
        "cancelled": "Cancelled",
        "placeholder_text": "Transcription appears here..."
    },
    "de": {
        "ready": "Bereit",
        "recording": "Aufnahme läuft...",
        "waiting_transcription": "Warte auf Transkription...",
        "saved": "Gespeichert! ✓",
        "finished": "✅ Fertig",
        "settings_title": "SnapScribe Einstellungen",
        "hotkey_record": "Hotkey Aufnahme:",
        "hotkey_show": "Hotkey Fenster:",
        "language_label": "Sprache:",
        "english": "English",
        "german": "Deutsch",
        "open": "Öffnen",
        "exit": "Beenden",
        "cancel_reset": "Abbrechen (Reset)",
        "save": "Speichern",
        "auto_copy": "Text automatisch kopieren",
        "minimize_tray": "In Tray minimieren",
        "settings_saved": "Einstellungen gespeichert.",
        "cancelled": "Abgebrochen",
        "placeholder_text": "Transkription erscheint hier..."
    }
}

def t(key: str, lang: str = "en") -> str:
    """
    Gibt den übersetzten Text für einen Key in der gewünschten Sprache zurück.
    Fallback auf English, wenn Key nicht gefunden.
    """
    return _translations.get(lang, _translations["en"]).get(key, key)
