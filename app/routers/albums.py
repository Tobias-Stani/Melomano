import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from app.database import get_db
from app.models.album import Album
from app.models.featured import FeaturedItem
from app.auth import get_current_user
from app.services.discogs import sync_collection, search_discogs

router    = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def gallery(request: Request, q: str = None, filter: str = "all", db: Session = Depends(get_db)):
    user  = get_current_user(request)
    if not user:
        return RedirectResponse(url="/perfil", status_code=302)
    query = db.query(Album).filter(Album.deleted_at == None)

    if q:
        query = query.filter(or_(Album.title.ilike(f"%{q}%"), Album.artist.ilike(f"%{q}%")))

    if filter == "owned":
        query = query.filter(Album.owned == True)
    elif filter == "listened":
        query = query.filter(Album.listened == True)
    elif filter == "wishlist":
        query = query.filter(Album.wishlist == True)

    albums = query.order_by(Album.artist, Album.year).all()
    total  = db.query(Album).filter(Album.deleted_at == None).count()

    return templates.TemplateResponse("gallery.html", {
        "request": request,
        "user":    user,
        "albums":  albums,
        "total":   total,
        "q":       q or "",
        "filter":  filter,
    })


@router.get("/album/{album_id}", response_class=HTMLResponse)
async def album_detail(album_id: int, request: Request, db: Session = Depends(get_db)):
    user  = get_current_user(request)
    album = db.query(Album).filter(Album.id == album_id, Album.deleted_at == None).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album no encontrado")
    is_featured = db.query(FeaturedItem).filter(
        FeaturedItem.type == "album", FeaturedItem.item_id == album_id
    ).first() is not None
    return templates.TemplateResponse("album_detail.html", {
        "request": request, "user": user, "album": album, "is_featured": is_featured,
    })


@router.post("/album/{album_id}/review")
async def save_review(
    album_id: int, request: Request,
    score: int = Form(None), review: str = Form(""),
    owned: str = Form(None), listened: str = Form(None), wishlist: str = Form(None),
    db: Session = Depends(get_db),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)

    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404)

    if score is not None:
        album.score    = score
    album.review       = review
    album.owned        = owned == "on"
    album.listened     = listened == "on"
    album.wishlist     = wishlist == "on"
    db.commit()
    return RedirectResponse(url=f"/album/{album_id}", status_code=303)


@router.get("/album/{album_id}/delete")
async def delete_album(album_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    album = db.query(Album).filter(Album.id == album_id, Album.deleted_at == None).first()
    if album:
        album.deleted_at = datetime.now(timezone.utc)
        db.commit()
    return RedirectResponse(url="/", status_code=303)


# ── Sync Discogs ─────────────────────────────────────────
@router.post("/sync/discogs")
async def trigger_sync(request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    log = await sync_collection(db)
    return RedirectResponse(url=f"/sync/status?log_id={log.id}", status_code=303)


@router.get("/sync/status", response_class=HTMLResponse)
async def sync_status(request: Request, log_id: int = None, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models.sync_log import SyncLog
    logs = db.query(SyncLog).order_by(desc(SyncLog.started_at)).limit(10).all()
    current = db.query(SyncLog).filter(SyncLog.id == log_id).first() if log_id else None
    return templates.TemplateResponse("sync_status.html", {
        "request": request, "user": user, "logs": logs, "current": current,
    })


# ── Busqueda Discogs ─────────────────────────────────────
@router.get("/search/discogs")
async def discogs_search(request: Request, q: str = "", db: Session = Depends(get_db)):
    if not get_current_user(request):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    if not q:
        return JSONResponse([])
    results = await search_discogs(q)
    return JSONResponse(results)


@router.post("/album/add")
async def add_album_manually(
    request: Request,
    discogs_id: int = Form(None),
    title: str = Form(...),
    artist: str = Form(...),
    year: int = Form(None),
    genre: str = Form(""),
    label: str = Form(""),
    cover_url: str = Form(""),
    format_type: str = Form(""),
    discogs_url: str = Form(""),
    db: Session = Depends(get_db),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)

    # Verificar si ya existe
    if discogs_id:
        existing = db.query(Album).filter(Album.discogs_id == discogs_id, Album.deleted_at == None).first()
        if existing:
            return RedirectResponse(url=f"/album/{existing.id}", status_code=303)

    album = Album(
        discogs_id=discogs_id,
        title=title,
        artist=artist,
        year=year or None,
        genre=genre or None,
        label=label or None,
        cover_url=cover_url or None,
        format_type=format_type or None,
        discogs_url=discogs_url or None,
        owned=True,
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return RedirectResponse(url=f"/album/{album.id}", status_code=303)
