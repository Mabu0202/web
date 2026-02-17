from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..auth import get_user_id, hash_password
from ..flash import flash

# WICHTIG: is_admin bleibt "Superuser" fürs Admin-Panel (vorkonfiguriert),
# aber du kannst die Admin-Panel-Rechte trotzdem im UI setzen.
from ..permissions import is_admin, can_admin_panel

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def require_admin(db: Session, request: Request) -> int:
    """
    Zugriff aufs Admin Panel:
      - Rolle 'admin' darf immer (und ist per SQL vorkonfiguriert)
      - alle anderen brauchen admin_access=true in admin_panel_permissions
    """
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(status_code=401)

    uid = int(uid)

    # Sicherheitsnetz: echte admin Rolle darf immer ins Admin Panel
    if is_admin(db, uid):
        return uid

    if not can_admin_panel(db, uid, "admin_access"):
        raise HTTPException(status_code=403, detail="Kein Zugriff aufs Admin Panel.")
    return uid


# -------------------------
# Admin Dashboard
# -------------------------

@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    require_admin(db, request)

    users_count = db.execute(text("SELECT COUNT(*) FROM admin_users")).scalar() or 0
    roles_count = db.execute(text("SELECT COUNT(*) FROM admin_roles")).scalar() or 0
    tables_count = db.execute(text("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_type='BASE TABLE'
          AND table_name NOT LIKE 'admin_%'
    """)).scalar() or 0

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "users_count": users_count,
            "roles_count": roles_count,
            "tables_count": tables_count,
        },
    )


# -------------------------
# USERS
# -------------------------

@router.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, db: Session = Depends(get_db)):
    uid = require_admin(db, request)

    users = db.execute(text("""
        SELECT id, username, is_active, created_at
        FROM admin_users
        ORDER BY username
    """)).mappings().all()

    roles = db.execute(text("""
        SELECT id, name
        FROM admin_roles
        ORDER BY name
    """)).mappings().all()

    user_roles = db.execute(text("""
        SELECT ur.user_id, r.id as role_id, r.name
        FROM admin_user_roles ur
        JOIN admin_roles r ON r.id = ur.role_id
        ORDER BY r.name
    """)).mappings().all()

    role_map = {}
    for ur in user_roles:
        role_map.setdefault(int(ur["user_id"]), []).append({
            "id": int(ur["role_id"]),
            "name": ur["name"]
        })

    # Admin-Panel Rechte für UI (Buttons aus-/einblenden)
    panel_perms = {
        "user_create": is_admin(db, uid) or can_admin_panel(db, uid, "user_create"),
        "user_toggle": is_admin(db, uid) or can_admin_panel(db, uid, "user_toggle"),
        "user_role_add": is_admin(db, uid) or can_admin_panel(db, uid, "user_role_add"),
        "user_role_remove": is_admin(db, uid) or can_admin_panel(db, uid, "user_role_remove"),
    }

    return templates.TemplateResponse(
        "admin_users.html",
        {
            "request": request,
            "users": users,
            "roles": roles,
            "role_map": role_map,
            "panel_perms": panel_perms,
        },
    )


@router.post("/admin/users/create")
def create_user(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
):
    uid = require_admin(db, request)
    if not (is_admin(db, uid) or can_admin_panel(db, uid, "user_create")):
        flash(request, "Keine Berechtigung: User anlegen.", "danger")
        return RedirectResponse("/admin/users", status_code=303)

    username = username.strip()
    if len(username) < 3:
        flash(request, "Username zu kurz (min. 3).", "danger")
        return RedirectResponse("/admin/users", status_code=303)
    if len(password) < 8:
        flash(request, "Passwort zu kurz (min. 8).", "danger")
        return RedirectResponse("/admin/users", status_code=303)

    exists = db.execute(
        text("SELECT 1 FROM admin_users WHERE username=:u LIMIT 1"),
        {"u": username},
    ).first()
    if exists:
        flash(request, "Username existiert bereits.", "danger")
        return RedirectResponse("/admin/users", status_code=303)

    db.execute(
        text("""
            INSERT INTO admin_users (username, password_hash, is_active)
            VALUES (:u, :p, 1)
        """),
        {"u": username, "p": hash_password(password)},
    )
    db.commit()
    flash(request, "User erfolgreich angelegt.", "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/toggle")
def toggle_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    uid = require_admin(db, request)
    if not (is_admin(db, uid) or can_admin_panel(db, uid, "user_toggle")):
        flash(request, "Keine Berechtigung: Aktiv/Inaktiv.", "danger")
        return RedirectResponse("/admin/users", status_code=303)

    db.execute(text("""
        UPDATE admin_users
        SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END
        WHERE id=:id
    """), {"id": user_id})
    db.commit()
    flash(request, "User-Status geändert.", "info")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/roles/add")
def add_role(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    role_id: int = Form(...),
):
    uid = require_admin(db, request)
    if not (is_admin(db, uid) or can_admin_panel(db, uid, "user_role_add")):
        flash(request, "Keine Berechtigung: Rolle hinzufügen.", "danger")
        return RedirectResponse("/admin/users", status_code=303)

    db.execute(text("""
        INSERT IGNORE INTO admin_user_roles (user_id, role_id)
        VALUES (:u, :r)
    """), {"u": user_id, "r": role_id})
    db.commit()
    flash(request, "Rolle hinzugefügt.", "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/roles/remove")
def remove_role(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    role_id: int = Form(...),
):
    uid = require_admin(db, request)
    if not (is_admin(db, uid) or can_admin_panel(db, uid, "user_role_remove")):
        flash(request, "Keine Berechtigung: Rolle entfernen.", "danger")
        return RedirectResponse("/admin/users", status_code=303)

    db.execute(text("""
        DELETE FROM admin_user_roles
        WHERE user_id=:u AND role_id=:r
    """), {"u": user_id, "r": role_id})
    db.commit()
    flash(request, "Rolle entfernt.", "warning")
    return RedirectResponse("/admin/users", status_code=303)


# -------------------------
# ROLES
# -------------------------

@router.get("/admin/roles", response_class=HTMLResponse)
def admin_roles(request: Request, db: Session = Depends(get_db)):
    require_admin(db, request)

    roles = db.execute(text("""
        SELECT id, name
        FROM admin_roles
        ORDER BY name
    """)).mappings().all()

    return templates.TemplateResponse(
        "admin_roles.html",
        {"request": request, "roles": roles},
    )


@router.post("/admin/roles/create")
def create_role(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
):
    uid = require_admin(db, request)
    if not (is_admin(db, uid) or can_admin_panel(db, uid, "role_create")):
        flash(request, "Keine Berechtigung: Rollen anlegen.", "danger")
        return RedirectResponse("/admin/roles", status_code=303)

    name = name.strip()
    if not name:
        flash(request, "Rollenname fehlt.", "danger")
        return RedirectResponse("/admin/roles", status_code=303)

    db.execute(text("INSERT IGNORE INTO admin_roles (name) VALUES (:n)"), {"n": name})
    db.commit()
    flash(request, "Rolle erstellt.", "success")
    return RedirectResponse("/admin/roles", status_code=303)


# -------------------------
# PERMISSIONS (Tabellenrechte + Admin-Panel-Rechte)
# -------------------------

@router.get("/admin/permissions", response_class=HTMLResponse)
def admin_permissions(
    request: Request,
    db: Session = Depends(get_db),
    role_id: int | None = None
):
    uid = require_admin(db, request)
    if not (is_admin(db, uid) or can_admin_panel(db, uid, "permissions_edit")):
        raise HTTPException(status_code=403, detail="Keine Berechtigung: Rechte bearbeiten.")

    roles = db.execute(text("""
        SELECT id, name
        FROM admin_roles
        ORDER BY name
    """)).mappings().all()

    if role_id is None and roles:
        role_id = int(roles[0]["id"])

    # Tabellenrechte
    tables = db.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_type='BASE TABLE'
          AND table_name NOT LIKE 'admin_%'
        ORDER BY table_name
    """)).all()
    tables = [t[0] for t in tables]

    perms = {}
    if role_id is not None:
        rows = db.execute(text("""
            SELECT table_name, can_view, can_create, can_update, can_delete
            FROM admin_permissions
            WHERE role_id=:rid
        """), {"rid": role_id}).mappings().all()

        for r in rows:
            perms[r["table_name"]] = {
                "view": bool(r["can_view"]),
                "create": bool(r["can_create"]),
                "update": bool(r["can_update"]),
                "delete": bool(r["can_delete"]),
            }

    # Admin-Panel-Rechte (Punkt 5.1)
    admin_panel_perms = None
    if role_id is not None:
        panel_row = db.execute(text("""
            SELECT can_admin_access, can_user_create, can_user_toggle, can_user_role_add, can_user_role_remove,
                   can_role_create, can_permissions_edit
            FROM admin_panel_permissions
            WHERE role_id=:rid
            LIMIT 1
        """), {"rid": role_id}).mappings().first()

        admin_panel_perms = {
            "admin_access": bool(panel_row["can_admin_access"]) if panel_row else False,
            "user_create": bool(panel_row["can_user_create"]) if panel_row else False,
            "user_toggle": bool(panel_row["can_user_toggle"]) if panel_row else False,
            "user_role_add": bool(panel_row["can_user_role_add"]) if panel_row else False,
            "user_role_remove": bool(panel_row["can_user_role_remove"]) if panel_row else False,
            "role_create": bool(panel_row["can_role_create"]) if panel_row else False,
            "permissions_edit": bool(panel_row["can_permissions_edit"]) if panel_row else False,
        }

    return templates.TemplateResponse(
        "admin_permissions.html",
        {
            "request": request,
            "roles": roles,
            "selected_role_id": role_id,
            "tables": tables,
            "perms": perms,
            "admin_panel_perms": admin_panel_perms,
        },
    )


@router.post("/admin/permissions/save")
async def save_permissions(request: Request, db: Session = Depends(get_db)):
    uid = require_admin(db, request)
    if not (is_admin(db, uid) or can_admin_panel(db, uid, "permissions_edit")):
        raise HTTPException(status_code=403, detail="Keine Berechtigung: Rechte speichern.")

    form = dict(await request.form())
    if "role_id" not in form:
        flash(request, "role_id fehlt.", "danger")
        return RedirectResponse("/admin/permissions", status_code=303)

    role_id = int(form["role_id"])

    # --- Admin-Panel-Rechte speichern (Punkt 5.2) ---
    def ap_checked(key: str) -> int:
        return 1 if key in form else 0

    db.execute(text("""
        INSERT INTO admin_panel_permissions
          (role_id, can_admin_access, can_user_create, can_user_toggle, can_user_role_add, can_user_role_remove,
           can_role_create, can_permissions_edit)
        VALUES
          (:rid, :a, :uc, :ut, :ura, :urr, :rc, :pe)
        ON DUPLICATE KEY UPDATE
          can_admin_access=VALUES(can_admin_access),
          can_user_create=VALUES(can_user_create),
          can_user_toggle=VALUES(can_user_toggle),
          can_user_role_add=VALUES(can_user_role_add),
          can_user_role_remove=VALUES(can_user_role_remove),
          can_role_create=VALUES(can_role_create),
          can_permissions_edit=VALUES(can_permissions_edit)
    """), {
        "rid": role_id,
        "a": ap_checked("ap__admin_access"),
        "uc": ap_checked("ap__user_create"),
        "ut": ap_checked("ap__user_toggle"),
        "ura": ap_checked("ap__user_role_add"),
        "urr": ap_checked("ap__user_role_remove"),
        "rc": ap_checked("ap__role_create"),
        "pe": ap_checked("ap__permissions_edit"),
    })

    # --- Tabellenrechte speichern (wie vorher) ---
    tables = db.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_type='BASE TABLE'
          AND table_name NOT LIKE 'admin_%'
    """)).all()
    tables = [t[0] for t in tables]

    def checked(key: str) -> int:
        return 1 if key in form else 0

    for tname in tables:
        db.execute(text("""
            INSERT INTO admin_permissions
              (role_id, table_name, can_view, can_create, can_update, can_delete)
            VALUES
              (:rid, :t, :v, :c, :u, :d)
            ON DUPLICATE KEY UPDATE
              can_view=VALUES(can_view),
              can_create=VALUES(can_create),
              can_update=VALUES(can_update),
              can_delete=VALUES(can_delete)
        """), {
            "rid": role_id,
            "t": tname,
            "v": checked(f"{tname}__view"),
            "c": checked(f"{tname}__create"),
            "u": checked(f"{tname}__update"),
            "d": checked(f"{tname}__delete"),
        })

    db.commit()
    flash(request, "Rechte gespeichert.", "success")
    return RedirectResponse(f"/admin/permissions?role_id={role_id}", status_code=303)
