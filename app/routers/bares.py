import base64
import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models.hifi_bar import HifiBar
from app.models.bar_visit import BarVisit
from app.models.bar_photo import BarPhoto
from app.auth import get_current_user

router    = APIRouter()
templates = Jinja2Templates(directory="app/templates")

EMOJIS = {1:'😞',2:'😔',3:'😐',4:'🙂',5:'😊',6:'😁',7:'🤩',8:'🔥',9:'💫',10:'🌟'}


def _maps_embed(bar: HifiBar) -> str:
    if bar.maps_url:
        url = bar.maps_url.strip()
        if "output=embed" in url:
            return url
        if "google.com/maps" in url:
            sep = "&" if "?" in url else "?"
            return url + sep + "output=embed"
    if bar.address:
        q = quote(f"{bar.address}, {bar.city or ''} {bar.country or ''}".strip(", "))
        return f"https://maps.google.com/maps?q={q}&output=embed&hl=es"
    return ""


# ── Lista ─────────────────────────────────────────────────

@router.get("/bares", response_class=HTMLResponse)
async def bares_list(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    bars = db.query(HifiBar).order_by(HifiBar.name).all()
    return templates.TemplateResponse("bares.html", {
        "request": request, "user": user, "bars": bars,
    })


# ── Nuevo ─────────────────────────────────────────────────

@router.get("/bares/nuevo", response_class=HTMLResponse)
async def bar_new(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("bar_form.html", {
        "request": request, "user": user, "bar": None, "error": None,
    })


@router.post("/bares/nuevo")
async def bar_create(
    request: Request,
    name: str        = Form(...),
    address: str     = Form(""),
    city: str        = Form(""),
    country: str     = Form(""),
    maps_url: str    = Form(""),
    description: str = Form(""),
    db: Session      = Depends(get_db),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    bar = HifiBar(
        name=name,
        address=address or None,
        city=city or None,
        country=country or None,
        maps_url=maps_url or None,
        description=description or None,
    )
    db.add(bar)
    db.commit()
    db.refresh(bar)
    return RedirectResponse(url=f"/bares/{bar.id}", status_code=303)


# ── Detalle ───────────────────────────────────────────────

@router.get("/bares/{bar_id}", response_class=HTMLResponse)
async def bar_detail(bar_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    bar  = db.query(HifiBar).filter(HifiBar.id == bar_id).first()
    if not bar:
        raise HTTPException(status_code=404)
    active_photos = [p for p in bar.photos if p.deleted_at is None]
    return templates.TemplateResponse("bar_detail.html", {
        "request":       request,
        "user":          user,
        "bar":           bar,
        "active_photos": active_photos,
        "emojis":        EMOJIS,
        "maps_embed":    _maps_embed(bar),
        "today":         datetime.date.today().isoformat(),
    })


# ── Editar ────────────────────────────────────────────────

@router.get("/bares/{bar_id}/editar", response_class=HTMLResponse)
async def bar_edit(bar_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    bar = db.query(HifiBar).filter(HifiBar.id == bar_id).first()
    if not bar:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("bar_form.html", {
        "request": request, "user": get_current_user(request), "bar": bar, "error": None,
    })


@router.post("/bares/{bar_id}/editar")
async def bar_update(
    bar_id: int, request: Request,
    name: str        = Form(...),
    address: str     = Form(""),
    city: str        = Form(""),
    country: str     = Form(""),
    maps_url: str    = Form(""),
    description: str = Form(""),
    db: Session      = Depends(get_db),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    bar = db.query(HifiBar).filter(HifiBar.id == bar_id).first()
    if not bar:
        raise HTTPException(status_code=404)
    bar.name        = name
    bar.address     = address or None
    bar.city        = city or None
    bar.country     = country or None
    bar.maps_url    = maps_url or None
    bar.description = description or None
    db.commit()
    return RedirectResponse(url=f"/bares/{bar_id}", status_code=303)


@router.get("/bares/{bar_id}/delete")
async def bar_delete(bar_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    bar = db.query(HifiBar).filter(HifiBar.id == bar_id).first()
    if bar:
        db.delete(bar)
        db.commit()
    return RedirectResponse(url="/bares", status_code=303)


# ── Visitas ───────────────────────────────────────────────

@router.post("/bares/{bar_id}/visitas")
async def visit_add(
    bar_id: int, request: Request,
    date: str    = Form(...),
    drinks: str  = Form(""),
    notes: str   = Form(""),
    score: int   = Form(None),
    db: Session  = Depends(get_db),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    visit = BarVisit(
        bar_id=bar_id,
        date=datetime.date.fromisoformat(date),
        drinks=drinks or None,
        notes=notes or None,
        score=score,
    )
    db.add(visit)
    db.commit()
    return RedirectResponse(url=f"/bares/{bar_id}#visitas", status_code=303)


@router.get("/bares/{bar_id}/visitas/{visit_id}/delete")
async def visit_delete(bar_id: int, visit_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    visit = db.query(BarVisit).filter(BarVisit.id == visit_id, BarVisit.bar_id == bar_id).first()
    if visit:
        db.delete(visit)
        db.commit()
    return RedirectResponse(url=f"/bares/{bar_id}#visitas", status_code=303)


# ── Fotos ─────────────────────────────────────────────────

@router.post("/bares/{bar_id}/fotos")
async def photos_upload(
    bar_id: int, request: Request,
    photos: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    for photo in photos:
        raw = await photo.read()
        if not raw:
            continue
        db.add(BarPhoto(
            bar_id=bar_id,
            data=base64.b64encode(raw).decode(),
            mime_type=photo.content_type or "image/jpeg",
        ))
    db.commit()
    return RedirectResponse(url=f"/bares/{bar_id}#fotos", status_code=303)


@router.get("/bares/{bar_id}/fotos/{photo_id}/set-cover")
async def photo_set_cover(bar_id: int, photo_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    photo = db.query(BarPhoto).filter(BarPhoto.id == photo_id, BarPhoto.bar_id == bar_id, BarPhoto.deleted_at == None).first()
    bar   = db.query(HifiBar).filter(HifiBar.id == bar_id).first()
    if photo and bar:
        bar.cover_url = f"data:{photo.mime_type};base64,{photo.data}"
        db.commit()
    return RedirectResponse(url=f"/bares/{bar_id}", status_code=303)


@router.get("/bares/{bar_id}/fotos/{photo_id}/delete")
async def photo_delete(bar_id: int, photo_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    photo = db.query(BarPhoto).filter(BarPhoto.id == photo_id, BarPhoto.bar_id == bar_id, BarPhoto.deleted_at == None).first()
    if photo:
        from datetime import datetime, timezone
        photo.deleted_at = datetime.now(timezone.utc)
        db.commit()
    return RedirectResponse(url=f"/bares/{bar_id}#fotos", status_code=303)
