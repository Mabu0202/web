from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..auth import verify_password, get_user_id

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def root(request: Request):
    uid = get_user_id(request)
    return RedirectResponse("/tables" if uid else "/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
):
    q = text(
        "SELECT id, password_hash, is_active FROM admin_users WHERE username=:u LIMIT 1"
    )
    row = db.execute(q, {"u": username}).mappings().first()

    if (
        not row
        or not row["is_active"]
        or not verify_password(password, row["password_hash"])
    ):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Login fehlgeschlagen."}
        )

    request.session["user_id"] = int(row["id"])
    return RedirectResponse("/tables", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
