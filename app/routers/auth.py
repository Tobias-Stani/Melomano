from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import check_credentials, create_session_token, get_current_user, COOKIE_NAME, COOKIE_MAX_AGE

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    if check_credentials(username, password):
        token    = create_session_token(username)
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key=COOKIE_NAME, value=token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax")
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Usuario o contrasena incorrectos"}, status_code=401)


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response
