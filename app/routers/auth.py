from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import verify_password, create_session_token, get_current_user, COOKIE_NAME, COOKIE_MAX_AGE
from app.database import get_db
from app.models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    if get_current_user(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": None, "next": next})


@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if user and verify_password(password, user.password_hash):
        token    = create_session_token(username)
        response = RedirectResponse(url=next or "/", status_code=303)
        response.set_cookie(key=COOKIE_NAME, value=token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax")
        return response
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": "Usuario o contrasena incorrectos", "next": next}, status_code=401)


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response
