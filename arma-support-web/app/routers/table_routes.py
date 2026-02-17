from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db, engine
from ..auth import get_user_id
from ..permissions import can
from ..config import TABLE_UI_RULES
from ..crud_dynamic import (
    get_table,
    list_rows,
    create_row,
    update_row,
    delete_row,
    primary_key_columns,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ---------------------------------
# Login Pflicht
# ---------------------------------

def require_login(request: Request) -> int:
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(status_code=401)
    return int(uid)


# ---------------------------------
# Tabellen Übersicht
# ---------------------------------

@router.get("/tables", response_class=HTMLResponse)
def tables(request: Request, db: Session = Depends(get_db)):
    uid = require_login(request)

    q = text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_type='BASE TABLE'
          AND table_name NOT LIKE 'admin_%'
        ORDER BY table_name
    """)

    all_tables = [r[0] for r in db.execute(q).all()]
    visible_tables = [t for t in all_tables if can(db, uid, t, "view")]

    return templates.TemplateResponse(
        "tables.html",
        {
            "request": request,
            "tables": visible_tables,
        },
    )


# ---------------------------------
# Einzelne Tabelle anzeigen
# ---------------------------------

@router.get("/table/{table_name}", response_class=HTMLResponse)
def table_view(table_name: str, request: Request, db: Session = Depends(get_db)):
    uid = require_login(request)

    if not can(db, uid, table_name, "view"):
        raise HTTPException(status_code=403)

    t = get_table(engine, table_name)
    rows = list_rows(db, t)
    cols = [c.name for c in t.columns]
    pks = [c.name for c in primary_key_columns(t)]

    rules = TABLE_UI_RULES.get(table_name, {})
    print("DEBUG CONFIG:", table_name, rules)

    can_view = can(db, uid, table_name, "view")
    can_create = can(db, uid, table_name, "create")
    can_update = can(db, uid, table_name, "update")
    can_delete = can(db, uid, table_name, "delete")

    edit_ui_disabled = rules.get("disable_edit_ui", False)

    perms = {
        "view": can_view,

        "create": (
            can_create
            and not rules.get("disable_create", False)
        ),

        # Wichtig: disable_update ODER disable_edit_ui => kein Speichern + keine Inputs
        "update": (
            can_update
            and bool(pks)
            and not rules.get("disable_update", False)
            and not edit_ui_disabled
        ),

        "delete": (
            can_delete
            and bool(pks)
            and not rules.get("disable_delete", False)
        ),
    }

    return templates.TemplateResponse(
        "table.html",
        {
            "request": request,
            "table": table_name,
            "cols": cols,
            "rows": rows,
            "pks": pks,
            "perms": perms,
        },
    )


# ---------------------------------
# Create
# ---------------------------------

@router.post("/table/{table_name}/create")
async def table_create(table_name: str, request: Request, db: Session = Depends(get_db)):
    uid = require_login(request)

    rules = TABLE_UI_RULES.get(table_name, {})
    print("DEBUG CONFIG:", table_name, rules)

    if (
        not can(db, uid, table_name, "create")
        or rules.get("disable_create", False)
    ):
        raise HTTPException(status_code=403)

    t = get_table(engine, table_name)
    data = dict(await request.form())

    create_row(db, t, data)

    return RedirectResponse(f"/table/{table_name}", status_code=303)


# ---------------------------------
# Update
# ---------------------------------

@router.post("/table/{table_name}/update")
async def table_update(table_name: str, request: Request, db: Session = Depends(get_db)):
    uid = require_login(request)

    rules = TABLE_UI_RULES.get(table_name, {})
    print("DEBUG CONFIG:", table_name, rules)

    if (
        not can(db, uid, table_name, "update")
        or rules.get("disable_update", False)
    ):
        raise HTTPException(status_code=403)

    t = get_table(engine, table_name)
    form = dict(await request.form())

    pks = [c.name for c in primary_key_columns(t)]
    pk_values = {pk: form[f"pk_{pk}"] for pk in pks}
    data = {k: v for k, v in form.items() if not k.startswith("pk_")}

    update_row(db, t, pk_values, data)

    return RedirectResponse(f"/table/{table_name}", status_code=303)


# ---------------------------------
# Delete
# ---------------------------------

@router.post("/table/{table_name}/delete")
async def table_delete(table_name: str, request: Request, db: Session = Depends(get_db)):
    uid = require_login(request)

    rules = TABLE_UI_RULES.get(table_name, {})
    print("DEBUG CONFIG:", table_name, rules)

    if (
        not can(db, uid, table_name, "delete")
        or rules.get("disable_delete", False)
    ):
        raise HTTPException(status_code=403)

    t = get_table(engine, table_name)
    form = dict(await request.form())

    pks = [c.name for c in primary_key_columns(t)]
    pk_values = {pk: form[f"pk_{pk}"] for pk in pks}

    delete_row(db, t, pk_values)

    return RedirectResponse(f"/table/{table_name}", status_code=303)
