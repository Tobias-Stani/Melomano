from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.auth import get_current_user
from app.services.ai_chat import get_rate_limit_status, AIChatError, AI_MODEL, AI_BASE_URL


router    = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _require_admin(request: Request, db: Session):
    username = get_current_user(request)
    if not username:
        return None
    return db.query(User).filter(User.username == username, User.is_admin == True).first()


@router.get("/admin/ia", response_class=HTMLResponse)
async def ia_dashboard(request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/", status_code=302)

    status = None
    error  = None
    try:
        status = await get_rate_limit_status()
    except AIChatError as e:
        error = str(e)

    return templates.TemplateResponse("admin/ia.html", {
        "request":  request,
        "user":     admin.username,
        "status":   status,
        "error":    error,
        "model":    AI_MODEL,
        "base_url": AI_BASE_URL,
    })
