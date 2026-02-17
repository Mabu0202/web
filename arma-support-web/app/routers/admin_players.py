from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db, engine
from ..auth import get_user_id
from ..flash import flash
from ..permissions import is_admin, can_admin_panel, can_kv_field

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

SIDE_LABEL = {0: "Ziv", 1: "Cop", 2: "UNCDA"}


# =====================================================
# Admin Zugriff
# =====================================================

def require_admin(db: Session, request: Request) -> int:
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(status_code=401)

    uid = int(uid)

    if is_admin(db, uid):
        return uid

    if not can_admin_panel(db, uid, "admin_access"):
        raise HTTPException(status_code=403)

    return uid


def require_current_uid(request: Request) -> int:
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(status_code=401)
    return int(uid)


# =====================================================
# Spielerliste
# =====================================================

@router.get("/admin/players", response_class=HTMLResponse)
def players_list(request: Request, db: Session = Depends(get_db)):
    require_admin(db, request)

    q = text("""
        SELECT
          pid AS uid,
          COALESCE(
            MAX(CASE WHEN side=0 AND k='name' THEN v END),
            MAX(CASE WHEN side=1 AND k='name' THEN v END),
            MAX(CASE WHEN side=2 AND k='name' THEN v END)
          ) AS name
        FROM kvstore
        WHERE k='name'
        GROUP BY pid
        ORDER BY name
        LIMIT 2000
    """)

    players = db.execute(q).mappings().all()

    return templates.TemplateResponse(
        "players_list.html",
        {"request": request, "players": players},
    )


# =====================================================
# Player Detail
# =====================================================

@router.get("/admin/players/{uid}", response_class=HTMLResponse)
def player_detail(uid: str, request: Request, db: Session = Depends(get_db), tab: str = "info"):
    require_admin(db, request)

    if tab not in ("info", "support", "gear", "vehicles"):
        tab = "info"

    name_q = text("""
        SELECT COALESCE(
            MAX(CASE WHEN side=0 AND k='name' THEN v END),
            MAX(CASE WHEN side=1 AND k='name' THEN v END),
            MAX(CASE WHEN side=2 AND k='name' THEN v END)
        ) AS name
        FROM kvstore
        WHERE pid=:uid AND k='name'
    """)

    info_q = text("""
        SELECT
          side,
          MAX(CASE WHEN k='name' THEN v END) AS name,
          MAX(CASE WHEN k='level' THEN v END) AS level,
          MAX(CASE WHEN k='pt' THEN v END) AS pt,
          MAX(CASE WHEN k='cash' THEN v END) AS cash,
          MAX(CASE WHEN k='bank' THEN v END) AS bank,
          MAX(CASE WHEN k='address' THEN v END) AS address,
          MAX(CASE WHEN k='town' THEN v END) AS town,
          MAX(CASE WHEN k='birthday' THEN v END) AS birthday,
          MAX(CASE WHEN k='birthlocation' THEN v END) AS birthlocation,
          MAX(CASE WHEN k='eyecolor' THEN v END) AS eyecolor,
          MAX(CASE WHEN k='height' THEN v END) AS height
        FROM kvstore
        WHERE pid = :uid
        GROUP BY side
        ORDER BY side
    """)

    gear_q = text("""
        SELECT
          side,
          MAX(CASE WHEN k='licenses' THEN v END) AS licenses,
          MAX(CASE WHEN k='gear' THEN v END) AS gear
        FROM kvstore
        WHERE pid = :uid
        GROUP BY side
        ORDER BY side
    """)

    support_list_q = text("""
        SELECT id, player_pid, player_name, case_type, area, supporter_name, scn, content, status, created_at, updated_at
        FROM support_cases
        WHERE player_pid = :uid
        ORDER BY created_at DESC
        LIMIT 500
    """)

    vehicles_q = text("""
        SELECT
          id, side, classname, type, pid,
          alive, active, sold, locked,
          color, trunk, chip, ts_bought, ts_modified
        FROM vehicles
        WHERE pid = :uid
        ORDER BY ts_modified DESC, id DESC
        LIMIT 500
    """)

    player_name = db.execute(name_q, {"uid": uid}).scalar() or uid
    info_rows = db.execute(info_q, {"uid": uid}).mappings().all()
    gear_rows = db.execute(gear_q, {"uid": uid}).mappings().all()
    support_cases = db.execute(support_list_q, {"uid": uid}).mappings().all()
    vehicles = db.execute(vehicles_q, {"uid": uid}).mappings().all()

    info_map = {int(r["side"]): r for r in info_rows}
    gear_map = {int(r["side"]): r for r in gear_rows}

    # Feldrechte pro Side berechnen
    current_uid = require_current_uid(request)
    fields = ["name","level","pt","cash","bank","address","town","birthday","birthlocation","eyecolor","height"]
    editable = {0: {}, 1: {}, 2: {}}
    for s in (0, 1, 2):
        for f in fields:
            editable[s][f] = can_kv_field(db, current_uid, s, f)

    return templates.TemplateResponse(
        "player_detail.html",
        {
            "request": request,
            "uid": uid,
            "player_name": player_name,
            "tab": tab,
            "side_label": SIDE_LABEL,
            "info_map": info_map,
            "gear_map": gear_map,
            "support_cases": support_cases,
            "vehicles": vehicles,
            "editable": editable,
        },
    )


# =====================================================
# Info speichern (pro Side)
# =====================================================

@router.post("/admin/players/{uid}/info/save/{side}")
async def save_player_info_side(
    uid: str,
    side: int,
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin(db, request)

    if side not in (0, 1, 2):
        raise HTTPException(status_code=400)

    current_uid = require_current_uid(request)
    form = await request.form()

    fields = ["name","level","pt","cash","bank","address","town","birthday","birthlocation","eyecolor","height"]
    wrote_any = False

    with engine.begin() as conn:
        for f in fields:
            # Rechte prüfen
            if not can_kv_field(db, current_uid, side, f):
                continue

            val = (form.get(f) or "").strip()

            # leere Felder NICHT überschreiben
            if val == "":
                continue

            conn.execute(text("""
                INSERT INTO kvstore (pid, k, side, v, t)
                VALUES (:pid, :k, :side, :v, 'STRING')
                ON DUPLICATE KEY UPDATE
                  v = VALUES(v),
                  t = VALUES(t)
            """), {"pid": uid, "k": f, "side": side, "v": val})

            wrote_any = True

    if wrote_any:
        flash(request, f"Info gespeichert ({SIDE_LABEL.get(side)}).", "success")
    else:
        flash(request, f"Keine Änderungen gespeichert ({SIDE_LABEL.get(side)}).", "warning")

    return RedirectResponse(f"/admin/players/{uid}?tab=info", status_code=303)


# =====================================================
# Support Cases CRUD
# =====================================================

@router.post("/admin/players/{uid}/support/create")
def support_create(
    uid: str,
    request: Request,
    db: Session = Depends(get_db),
    case_type: str = Form(...),
    supporter_name: str = Form(...),
    area: str = Form("Support"),
    scn: str = Form(""),
    content: str = Form(""),
):
    require_admin(db, request)

    name_q = text("""
        SELECT COALESCE(
            MAX(CASE WHEN side=0 AND k='name' THEN v END),
            MAX(CASE WHEN side=1 AND k='name' THEN v END),
            MAX(CASE WHEN side=2 AND k='name' THEN v END)
        ) AS name
        FROM kvstore
        WHERE pid=:uid AND k='name'
    """)
    player_name = db.execute(name_q, {"uid": uid}).scalar() or uid

    db.execute(text("""
        INSERT INTO support_cases
          (player_pid, player_name, case_type, area, supporter_name, scn, content, status)
        VALUES
          (:pid, :pname, :ctype, :area, :sname, :scn, :content, 'open')
    """), {
        "pid": uid,
        "pname": player_name,
        "ctype": case_type.strip(),
        "area": (area or "Support").strip(),
        "sname": supporter_name.strip(),
        "scn": (scn or "").strip(),
        "content": content or "",
    })
    db.commit()

    flash(request, "Supportfall erstellt.", "success")
    return RedirectResponse(f"/admin/players/{uid}?tab=support", status_code=303)


@router.get("/admin/players/{uid}/support/{case_id}/edit", response_class=HTMLResponse)
def support_edit(uid: str, case_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(db, request)

    row = db.execute(text("""
        SELECT *
        FROM support_cases
        WHERE id=:id AND player_pid=:pid
        LIMIT 1
    """), {"id": case_id, "pid": uid}).mappings().first()

    if not row:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        "support_edit.html",
        {"request": request, "uid": uid, "case": row},
    )


@router.post("/admin/players/{uid}/support/{case_id}/update")
def support_update(
    uid: str,
    case_id: int,
    request: Request,
    db: Session = Depends(get_db),
    case_type: str = Form(...),
    supporter_name: str = Form(...),
    area: str = Form("Support"),
    scn: str = Form(""),
    content: str = Form(""),
    status: str = Form("open"),
):
    require_admin(db, request)

    if status not in ("open", "closed"):
        status = "open"

    db.execute(text("""
        UPDATE support_cases
        SET case_type=:ctype,
            area=:area,
            supporter_name=:sname,
            scn=:scn,
            content=:content,
            status=:status
        WHERE id=:id AND player_pid=:pid
    """), {
        "ctype": case_type.strip(),
        "area": (area or "Support").strip(),
        "sname": supporter_name.strip(),
        "scn": (scn or "").strip(),
        "content": content or "",
        "status": status,
        "id": case_id,
        "pid": uid,
    })
    db.commit()

    flash(request, "Supportfall gespeichert.", "success")
    return RedirectResponse(f"/admin/players/{uid}?tab=support", status_code=303)


@router.post("/admin/players/{uid}/support/{case_id}/toggle-status")
def support_toggle_status(uid: str, case_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(db, request)

    db.execute(text("""
        UPDATE support_cases
        SET status = CASE WHEN status='open' THEN 'closed' ELSE 'open' END
        WHERE id=:id AND player_pid=:pid
    """), {"id": case_id, "pid": uid})
    db.commit()

    flash(request, "Status geändert.", "info")
    return RedirectResponse(f"/admin/players/{uid}?tab=support", status_code=303)


@router.post("/admin/players/{uid}/support/{case_id}/delete")
def support_delete(uid: str, case_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(db, request)

    db.execute(text("DELETE FROM support_cases WHERE id=:id AND player_pid=:pid"), {"id": case_id, "pid": uid})
    db.commit()

    flash(request, "Supportfall gelöscht.", "warning")
    return RedirectResponse(f"/admin/players/{uid}?tab=support", status_code=303)


# =====================================================
# Vehicle Edit + Quick Actions
# =====================================================

@router.get("/admin/players/vehicles/{vehicle_id}", response_class=HTMLResponse)
def vehicle_edit(vehicle_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(db, request)

    v = db.execute(text("SELECT * FROM vehicles WHERE id=:id LIMIT 1"), {"id": vehicle_id}).mappings().first()
    if not v:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse("vehicle_edit.html", {"request": request, "v": v})


@router.post("/admin/players/vehicles/{vehicle_id}/update")
def vehicle_update(
    vehicle_id: int,
    request: Request,
    db: Session = Depends(get_db),
    alive: str = Form("0"),
    active: str = Form("0"),
    sold: str = Form("0"),
    locked: str = Form("0"),
    color: int = Form(0),
    trunk: str = Form(""),
):
    require_admin(db, request)

    def cb(v: str) -> int:
        return 1 if str(v).lower() in ("1", "true", "on", "yes") else 0

    db.execute(text("""
        UPDATE vehicles
        SET alive=:alive,
            active=:active,
            sold=:sold,
            locked=:locked,
            color=:color,
            trunk=:trunk,
            ts_modified=CURRENT_TIMESTAMP
        WHERE id=:id
    """), {
        "alive": cb(alive),
        "active": cb(active),
        "sold": cb(sold),
        "locked": cb(locked),
        "color": int(color),
        "trunk": trunk or "",
        "id": vehicle_id,
    })
    db.commit()

    pid = db.execute(text("SELECT pid FROM vehicles WHERE id=:id"), {"id": vehicle_id}).scalar()
    flash(request, "Fahrzeug gespeichert.", "success")
    return RedirectResponse(f"/admin/players/{pid}?tab=vehicles", status_code=303)


@router.post("/admin/players/vehicles/{vehicle_id}/qa/{action}")
def vehicle_quick_action(vehicle_id: int, action: str, request: Request, db: Session = Depends(get_db)):
    require_admin(db, request)

    allowed = {"restore", "lock", "unlock", "sell", "unsell", "kill", "revive"}
    if action not in allowed:
        raise HTTPException(status_code=400)

    sets = {
        "restore": "active=1, sold=0, alive=1",
        "lock": "locked=1",
        "unlock": "locked=0",
        "sell": "sold=1",
        "unsell": "sold=0",
        "kill": "alive=0",
        "revive": "alive=1",
    }[action]

    db.execute(text(f"""
        UPDATE vehicles
        SET {sets},
            ts_modified=CURRENT_TIMESTAMP
        WHERE id=:id
    """), {"id": vehicle_id})
    db.commit()

    pid = db.execute(text("SELECT pid FROM vehicles WHERE id=:id"), {"id": vehicle_id}).scalar()
    flash(request, f"Quick-Action: {action}", "info")
    return RedirectResponse(f"/admin/players/{pid}?tab=vehicles", status_code=303)
