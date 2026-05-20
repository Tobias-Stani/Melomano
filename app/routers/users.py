from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.auth import get_current_user, hash_password

router    = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _require_admin(request: Request, db: Session):
    username = get_current_user(request)
    if not username:
        return None
    return db.query(User).filter(User.username == username, User.is_admin == True).first()


@router.get("/usuarios", response_class=HTMLResponse)
async def users_list(request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/", status_code=302)
    users = db.query(User).order_by(User.created_at).all()
    return templates.TemplateResponse("users.html", {
        "request": request, "user": admin.username, "users": users,
    })


@router.get("/usuarios/nuevo", response_class=HTMLResponse)
async def user_new(request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("user_form.html", {
        "request": request, "user": admin.username, "profile": None, "error": None,
    })


@router.post("/usuarios/nuevo")
async def user_create(
    request: Request,
    username: str     = Form(...),
    display_name: str = Form(""),
    password: str     = Form(...),
    is_admin: str     = Form(None),
    db: Session       = Depends(get_db),
):
    admin = _require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/", status_code=302)

    if db.query(User).filter(User.username == username).first():
        return templates.TemplateResponse("user_form.html", {
            "request": request, "user": admin.username, "profile": None,
            "error": "Ese nombre de usuario ya existe.",
        }, status_code=400)

    new_user = User(
        username=username,
        display_name=display_name or None,
        password_hash=hash_password(password),
        is_admin=is_admin == "on",
    )
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/usuarios", status_code=303)


@router.get("/usuarios/{username}/editar", response_class=HTMLResponse)
async def user_edit(username: str, request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/", status_code=302)
    profile = db.query(User).filter(User.username == username).first()
    if not profile:
        return RedirectResponse(url="/usuarios", status_code=302)
    return templates.TemplateResponse("user_form.html", {
        "request": request, "user": admin.username, "profile": profile, "error": None,
    })


@router.post("/usuarios/{username}/editar")
async def user_update(
    username: str,
    request: Request,
    display_name: str = Form(""),
    password: str     = Form(""),
    is_admin: str     = Form(None),
    db: Session       = Depends(get_db),
):
    admin = _require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/", status_code=302)
    profile = db.query(User).filter(User.username == username).first()
    if not profile:
        return RedirectResponse(url="/usuarios", status_code=302)

    profile.display_name = display_name or None
    profile.is_admin     = is_admin == "on"
    if password:
        profile.password_hash = hash_password(password)
    db.commit()
    return RedirectResponse(url="/usuarios", status_code=303)


@router.get("/usuarios/{username}/eliminar")
async def user_delete(username: str, request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if not admin or admin.username == username:
        return RedirectResponse(url="/usuarios", status_code=302)
    profile = db.query(User).filter(User.username == username).first()
    if profile:
        db.delete(profile)
        db.commit()
    return RedirectResponse(url="/usuarios", status_code=303)
