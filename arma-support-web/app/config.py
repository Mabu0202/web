# app/config.py

"""
Zentrale UI/Action Konfiguration für Tabellen
"""

TABLE_UI_RULES = {
    "plog": {
        "disable_create": True,
        "disable_update": True,
        "disable_delete": True,
        "disable_edit_ui": False,
    },

    "player_alias": {
        "disable_create": True,
        "disable_update": True,
        "disable_delete": True,
    },

    # Beispiel:
    # "slog": {
    #   "disable_create": True,     # deaktiviert erstellen
    #   "disable_update": True,     # deaktiviert Speichern-Button + Update
    #   "disable_delete": True,     # deaktiviert Löschen-Button
    #   "disable_edit_ui": True,    # keine Eingabefelder (nur Anzeige)
    # },
}
