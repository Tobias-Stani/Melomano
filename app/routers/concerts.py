import base64
import datetime

from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models.concert import Concert
from app.models.concert_photo import ConcertPhoto
from app.models.featured import FeaturedItem
from app.auth import get_current_user

router    = APIRouter()
templates = Jinja2Templates(directory="app/templates")

EMOJIS = {1:'😞',2:'😔',3:'😐',4:'🙂',5:'😊',6:'😁',7:'🤩',8:'🔥',9:'💫',10:'🌟'}


@router.get("/concerts", response_class=HTMLResponse)
async def concerts_list(request: Request, db: Session = Depends(get_db)):
    user     = get_current_user(request)
    concerts = db.query(Concert).order_by(desc(Concert.date)).all()
    return templates.TemplateResponse("concerts.html", {
        "request": request, "user": user, "concerts": concerts, "emojis": EMOJIS,
    })


@router.get("/concerts/new", response_class=HTMLResponse)
async def concert_new(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("concert_form.html", {
        "request": request, "user": user, "concert": None, "today": datetime.date.today().isoformat(),
    })


@router.post("/concerts/new")
async def concert_create(
    request: Request,
    artist: str    = Form(...),
    date: str      = Form(...),
    venue: str     = Form(""),
    city: str      = Form(""),
    country: str   = Form(""),
    tour_name: str = Form(""),
    score: int     = Form(None),
    review: str    = Form(""),
    setlist: str   = Form(""),
    highlights: str = Form(""),
    cover_url: str = Form(""),
    db: Session    = Depends(get_db),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)

    concert = Concert(
        artist=artist,
        date=datetime.date.fromisoformat(date),
        venue=venue or None,
        city=city or None,
        country=country or None,
        tour_name=tour_name or None,
        score=score,
        review=review or None,
        setlist=setlist or None,
        highlights=highlights or None,
        cover_url=cover_url or None,
    )
    db.add(concert)
    db.commit()
    db.refresh(concert)
    return RedirectResponse(url=f"/concerts/{concert.id}", status_code=303)


@router.get("/concerts/{concert_id}", response_class=HTMLResponse)
async def concert_detail(concert_id: int, request: Request, db: Session = Depends(get_db)):
    user    = get_current_user(request)
    concert = db.query(Concert).filter(Concert.id == concert_id).first()
    if not concert:
        raise HTTPException(status_code=404)
    is_featured = db.query(FeaturedItem).filter(
        FeaturedItem.type == "concert", FeaturedItem.item_id == concert_id
    ).first() is not None
    active_photos = [p for p in concert.photos if p.deleted_at is None]
    return templates.TemplateResponse("concert_detail.html", {
        "request":      request,
        "user":         user,
        "concert":      concert,
        "emoji":        EMOJIS.get(concert.score, "") if concert.score else "",
        "is_featured":  is_featured,
        "active_photos": active_photos,
    })


@router.get("/concerts/{concert_id}/edit", response_class=HTMLResponse)
async def concert_edit(concert_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    concert = db.query(Concert).filter(Concert.id == concert_id).first()
    if not concert:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("concert_form.html", {
        "request": request, "user": user, "concert": concert,
        "today": datetime.date.today().isoformat(),
    })


@router.post("/concerts/{concert_id}/edit")
async def concert_update(
    concert_id: int, request: Request,
    artist: str    = Form(...),
    date: str      = Form(...),
    venue: str     = Form(""),
    city: str      = Form(""),
    country: str   = Form(""),
    tour_name: str = Form(""),
    score: int     = Form(None),
    review: str    = Form(""),
    setlist: str   = Form(""),
    highlights: str = Form(""),
    cover_url: str = Form(""),
    db: Session    = Depends(get_db),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    concert = db.query(Concert).filter(Concert.id == concert_id).first()
    if not concert:
        raise HTTPException(status_code=404)

    concert.artist     = artist
    concert.date       = datetime.date.fromisoformat(date)
    concert.venue      = venue or None
    concert.city       = city or None
    concert.country    = country or None
    concert.tour_name  = tour_name or None
    concert.score      = score
    concert.review     = review or None
    concert.setlist    = setlist or None
    concert.highlights = highlights or None
    concert.cover_url  = cover_url or None
    db.commit()
    return RedirectResponse(url=f"/concerts/{concert_id}", status_code=303)


@router.get("/concerts/{concert_id}/delete")
async def concert_delete(concert_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    concert = db.query(Concert).filter(Concert.id == concert_id).first()
    if concert:
        db.delete(concert)
        db.commit()
    return RedirectResponse(url="/concerts", status_code=303)


# ── Fotos ─────────────────────────────────────────────────

@router.post("/concerts/{concert_id}/photos")
async def upload_photos(
    concert_id: int,
    request: Request,
    photos: list[UploadFile] = File(...),
    captions: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    concert = db.query(Concert).filter(Concert.id == concert_id).first()
    if not concert:
        raise HTTPException(status_code=404)

    for i, photo in enumerate(photos):
        raw = await photo.read()
        if not raw:
            continue
        encoded = base64.b64encode(raw).decode("utf-8")
        caption = captions[i] if i < len(captions) else None
        db.add(ConcertPhoto(
            concert_id=concert_id,
            data=encoded,
            mime_type=photo.content_type or "image/jpeg",
            caption=caption or None,
        ))

    db.commit()
    return RedirectResponse(url=f"/concerts/{concert_id}#fotos", status_code=303)


@router.get("/concerts/{concert_id}/photos/{photo_id}/set-cover")
async def set_cover_photo(concert_id: int, photo_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    photo = db.query(ConcertPhoto).filter(
        ConcertPhoto.id == photo_id,
        ConcertPhoto.concert_id == concert_id,
        ConcertPhoto.deleted_at == None,
    ).first()
    concert = db.query(Concert).filter(Concert.id == concert_id).first()
    if photo and concert:
        concert.cover_url = f"data:{photo.mime_type};base64,{photo.data}"
        db.commit()
    return RedirectResponse(url=f"/concerts/{concert_id}", status_code=303)


@router.get("/concerts/{concert_id}/photos/{photo_id}/delete")
async def delete_photo(concert_id: int, photo_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    photo = db.query(ConcertPhoto).filter(
        ConcertPhoto.id == photo_id,
        ConcertPhoto.concert_id == concert_id,
        ConcertPhoto.deleted_at == None,
    ).first()
    if photo:
        from datetime import datetime, timezone
        photo.deleted_at = datetime.now(timezone.utc)
        db.commit()
    return RedirectResponse(url=f"/concerts/{concert_id}#fotos", status_code=303)
