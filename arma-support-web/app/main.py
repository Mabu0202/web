import os
from fastapi import FastAPI
from fastapi import Request
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from .flash import flash
from .routers import auth_routes, table_routes, admin_routes
from app.routers import admin_players

app = FastAPI()

# Session Middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-secret-change-me"),
    same_site="lax",
    https_only=False  # In Produktion auf True setzen (HTTPS)
)

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 403:
        flash(request, "⛔ Keine Berechtigung für diese Aktion.", "danger")
        return RedirectResponse(request.headers.get("referer", "/"), status_code=303)

    return await app.default_exception_handler(request, exc)

# Router registrieren
app.include_router(auth_routes.router)
app.include_router(table_routes.router)
app.include_router(admin_routes.router)
app.include_router(admin_players.router)
