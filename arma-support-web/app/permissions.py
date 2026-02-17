from sqlalchemy import text
from sqlalchemy.orm import Session


# ----------------------------
# Rollen-Check: admin
# ----------------------------

def is_admin(db: Session, user_id: int) -> bool:
    row = db.execute(text("""
        SELECT 1
        FROM admin_user_roles ur
        JOIN admin_roles r ON r.id = ur.role_id
        WHERE ur.user_id=:uid AND r.name='admin'
        LIMIT 1
    """), {"uid": user_id}).first()
    return bool(row)


# ----------------------------
# Tabellen-Rechte (CRUD)
# ----------------------------

ACTION_COL = {
    "view": "can_view",
    "create": "can_create",
    "update": "can_update",
    "delete": "can_delete",
}

def can(db: Session, user_id: int, table_name: str, action: str) -> bool:
    """
    Prüft Tabellenrechte pro Rolle aus admin_permissions.
    KEIN automatisches True (auch nicht für admin), außer du willst das explizit.
    """
    if action not in ACTION_COL:
        return False

    col = ACTION_COL[action]

    row = db.execute(text(f"""
        SELECT 1
        FROM admin_user_roles ur
        JOIN admin_permissions p ON p.role_id = ur.role_id
        WHERE ur.user_id=:uid
          AND p.table_name=:t
          AND p.{col}=1
        LIMIT 1
    """), {"uid": user_id, "t": table_name}).first()

    return bool(row)


# ----------------------------
# Admin-Panel-Rechte
# ----------------------------

ADMIN_ACTION_COL = {
    "admin_access": "can_admin_access",
    "user_create": "can_user_create",
    "user_toggle": "can_user_toggle",
    "user_role_add": "can_user_role_add",
    "user_role_remove": "can_user_role_remove",
    "role_create": "can_role_create",
    "permissions_edit": "can_permissions_edit",
}

def can_admin_panel(db: Session, user_id: int, action: str) -> bool:
    """
    Prüft Admin-Panel Rechte pro Rolle aus admin_panel_permissions.
    """
    if action not in ADMIN_ACTION_COL:
        return False

    col = ADMIN_ACTION_COL[action]

    row = db.execute(text(f"""
        SELECT 1
        FROM admin_user_roles ur
        JOIN admin_panel_permissions ap ON ap.role_id = ur.role_id
        WHERE ur.user_id=:uid
          AND ap.{col}=1
        LIMIT 1
    """), {"uid": user_id}).first()

    return bool(row)


# ----------------------------
# Spieler-Panel-Rechte (kvstore Felder)
# ----------------------------

KV_FIELDS = {
    "name", "level", "pt", "cash", "bank",
    "address", "town", "birthday", "birthlocation",
    "eyecolor", "height",
}

def can_kv_field(db: Session, user_id: int, side: int, field_name: str) -> bool:
    """
    Feld-Rechte für kvstore: pro Role + Side + Feld (admin_kv_permissions).
    Admin-Rolle: immer True.
    """
    if side not in (0, 1, 2):
        return False
    if field_name not in KV_FIELDS:
        return False

    # Admin-Rolle darf alles
    if is_admin(db, user_id):
        return True

    row = db.execute(text("""
        SELECT 1
        FROM admin_user_roles ur
        JOIN admin_kv_permissions kp ON kp.role_id = ur.role_id
        WHERE ur.user_id=:uid
          AND kp.side=:side
          AND kp.field_name=:f
          AND kp.can_edit=1
        LIMIT 1
    """), {"uid": user_id, "side": side, "f": field_name}).first()

    return bool(row)
