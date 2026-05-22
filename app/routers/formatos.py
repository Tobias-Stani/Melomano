from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.format_type import FormatType
from app.auth import get_current_user

router    = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/formatos", response_class=HTMLResponse)
async def formatos_list(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    formats = db.query(FormatType).order_by(FormatType.name).all()
    return templates.TemplateResponse("formatos.html", {
        "request": request, "user": user, "formats": formats,
    })


@router.post("/formatos")
async def formato_create(
    request: Request,
    name: str   = Form(...),
    db: Session = Depends(get_db),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    name = name.strip()
    if name and not db.query(FormatType).filter(FormatType.name == name).first():
        db.add(FormatType(name=name))
        db.commit()
    return RedirectResponse(url="/formatos", status_code=303)


@router.get("/formatos/{fmt_id}/delete")
async def formato_delete(fmt_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    fmt = db.query(FormatType).filter(FormatType.id == fmt_id).first()
    if fmt:
        db.delete(fmt)
        db.commit()
    return RedirectResponse(url="/formatos", status_code=303)
