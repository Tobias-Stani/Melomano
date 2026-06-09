import json
import hashlib
import random
from datetime import datetime, timezone, date
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, func, case

from app.database import get_db
from app.models.album import Album
from app.models.featured import FeaturedItem
from app.models.format_type import FormatType
from app.models.user import User
from app.auth import get_current_user
from app.services.discogs import sync_collection, search_discogs, fetch_release_details, search_by_barcode
from app.models.favorite_track import FavoriteTrack
from app.models.user import User


def _get_user_obj(username: str, db: Session):
    return db.query(User).filter(User.username == username).first()

router    = APIRouter()
templates = Jinja2Templates(directory="app/templates")


SORT_OPTIONS = {
    "artist":    lambda: [Album.artist, Album.year],
    "year_desc": lambda: [desc(Album.year).nulls_last(), Album.artist],
    "year_asc":  lambda: [Album.year.nulls_last(), Album.artist],
    "title":     lambda: [Album.title],
    "score":     lambda: [desc(Album.score).nulls_last(), Album.artist],
    "added":     lambda: [desc(Album.created_at)],
}


@router.get("/", response_class=HTMLResponse)
async def gallery(request: Request, q: str = None, filter: str = "all", fmt: str = "", sort: str = "added", db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        # Vista publica: mostrar la coleccion del admin
        user_obj = db.query(User).filter(User.is_admin == True).first()
    else:
        user_obj = _get_user_obj(username, db)
    uid = user_obj.id if user_obj else None

    query = db.query(Album).filter(Album.deleted_at == None, Album.user_id == uid)

    if q:
        query = query.filter(or_(Album.title.ilike(f"%{q}%"), Album.artist.ilike(f"%{q}%")))

    if filter == "owned":
        query = query.filter(Album.owned == True)
    elif filter == "listened":
        query = query.filter(Album.listened == True)
    elif filter == "wishlist":
        query = query.filter(Album.wishlist == True)

    if fmt:
        query = query.filter(Album.format_type.ilike(f"%{fmt}%"))

    order = SORT_OPTIONS.get(sort, SORT_OPTIONS["artist"])()
    albums = query.order_by(*order).all()

    base = db.query(Album).filter(Album.deleted_at == None, Album.user_id == uid)

    # Stats + total en una sola query
    stats_row = base.with_entities(
        func.count(Album.id).label("total"),
        func.sum(case((Album.owned    == True, 1), else_=0)).label("owned"),
        func.sum(case((Album.listened == True, 1), else_=0)).label("listened"),
        func.sum(case((Album.wishlist == True, 1), else_=0)).label("wishlist"),
    ).first()
    total = stats_row.total or 0
    stats = {
        "owned":    stats_row.owned    or 0,
        "listened": stats_row.listened or 0,
        "wishlist": stats_row.wishlist or 0,
    }

    # Formatos disponibles y conteos
    fmt_counts_raw = (
        base.filter(Album.format_type != None)
        .with_entities(Album.format_type, func.count(Album.id))
        .group_by(Album.format_type)
        .order_by(func.count(Album.id).desc())
        .all()
    )
    formats      = [r[0] for r in fmt_counts_raw]
    fmt_counts   = {r[0]: r[1] for r in fmt_counts_raw}

    # Géneros y conteos
    genre_counts_raw = (
        base.filter(Album.genre != None)
        .with_entities(Album.genre, func.count(Album.id))
        .group_by(Album.genre)
        .order_by(func.count(Album.id).desc())
        .limit(10)
        .all()
    )
    genre_counts = {r[0]: r[1] for r in genre_counts_raw}

    format_types = db.query(FormatType).order_by(FormatType.name).all()

    most_recent_id = (
        db.query(Album.id)
        .filter(Album.deleted_at == None)
        .order_by(desc(Album.created_at))
        .limit(1)
        .scalar()
    )

    return templates.TemplateResponse("gallery.html", {
        "request":     request,
        "user":        username,
        "user_obj":    user_obj,
        "albums":      albums,
        "total":       total,
        "q":           q or "",
        "filter":      filter,
        "fmt":         fmt,
        "sort":        sort,
        "formats":     formats,
        "fmt_counts":  fmt_counts,
        "genre_counts": genre_counts,
        "stats":        stats,
        "format_types": format_types,
        "most_recent_id": most_recent_id,
    })


@router.get("/album/{album_id}", response_class=HTMLResponse)
async def album_detail(album_id: int, request: Request, db: Session = Depends(get_db)):
    user  = get_current_user(request)
    album = db.query(Album).filter(Album.id == album_id, Album.deleted_at == None).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album no encontrado")
    is_featured  = db.query(FeaturedItem).filter(
        FeaturedItem.type == "album", FeaturedItem.item_id == album_id
    ).first() is not None
    format_types = db.query(FormatType).order_by(FormatType.name).all()
    discogs_extra = await fetch_release_details(album.discogs_id) if album.discogs_id else None
    user_obj = db.query(User).filter(User.username == user).first() if user else None
    fav_track = db.query(FavoriteTrack).filter(
        FavoriteTrack.album_id == album_id,
        FavoriteTrack.user_id == user_obj.id,
    ).first() if user_obj else None
    return templates.TemplateResponse("album_detail.html", {
        "request": request, "user": user, "album": album,
        "is_featured": is_featured, "format_types": format_types,
        "extra": discogs_extra, "fav_track": fav_track,
    })


@router.post("/album/{album_id}/review")
async def save_review(
    album_id: int, request: Request,
    score: int = Form(None), review: str = Form(""),
    owned: str = Form(None), listened: str = Form(None), wishlist: str = Form(None),
    format_type: str = Form(""),
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
    if format_type:
        album.format_type = format_type
    db.commit()
    return RedirectResponse(url=f"/album/{album_id}", status_code=303)


@router.get("/album/{album_id}/edit", response_class=HTMLResponse)
async def edit_album_form(album_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    album = db.query(Album).filter(Album.id == album_id, Album.deleted_at == None).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album no encontrado")
    format_types = db.query(FormatType).order_by(FormatType.name).all()
    return templates.TemplateResponse("album_edit.html", {
        "request": request, "user": user, "album": album, "format_types": format_types,
    })


@router.post("/album/{album_id}/edit")
async def edit_album(
    album_id: int, request: Request,
    title: str = Form(...),
    artist: str = Form(...),
    year: int = Form(None),
    genre: str = Form(""),
    label: str = Form(""),
    cover_url: str = Form(""),
    format_type: str = Form(""),
    score: int = Form(None),
    review: str = Form(""),
    owned: str = Form(None),
    listened: str = Form(None),
    wishlist: str = Form(None),
    db: Session = Depends(get_db),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    album = db.query(Album).filter(Album.id == album_id, Album.deleted_at == None).first()
    if not album:
        raise HTTPException(status_code=404)
    album.title       = title
    album.artist      = artist
    album.year        = year or None
    album.genre       = genre or None
    album.label       = label or None
    album.cover_url   = cover_url or None
    album.format_type = format_type or None
    if score is not None:
        album.score   = score
    album.review      = review
    album.owned       = owned == "on"
    album.listened    = listened == "on"
    album.wishlist    = wishlist == "on"
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
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user_obj = _get_user_obj(username, db)
    uid = user_obj.id if user_obj else None
    log = await sync_collection(db, user_id=uid)
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


@router.post("/album/{album_id}/favorite-track")
async def set_favorite_track(
    album_id: int, request: Request,
    track_pos: str = Form(...),
    track_title: str = Form(...),
    db: Session = Depends(get_db),
):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    user_obj = db.query(User).filter(User.username == username).first()

    existing = db.query(FavoriteTrack).filter(
        FavoriteTrack.album_id == album_id,
        FavoriteTrack.user_id == user_obj.id,
    ).first()

    if existing and existing.track_pos == track_pos:
        db.delete(existing)
    elif existing:
        existing.track_pos   = track_pos
        existing.track_title = track_title
    else:
        db.add(FavoriteTrack(user_id=user_obj.id, album_id=album_id, track_pos=track_pos, track_title=track_title))

    db.commit()
    return JSONResponse({"ok": True})


@router.get("/search/barcode")
async def barcode_search(request: Request, code: str = ""):
    if not get_current_user(request):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    if not code:
        return JSONResponse([])
    results = await search_by_barcode(code)
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
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user_obj = _get_user_obj(username, db)
    uid = user_obj.id if user_obj else None

    # Verificar si ya existe para este usuario
    if discogs_id:
        existing = db.query(Album).filter(
            Album.discogs_id == discogs_id, Album.user_id == uid, Album.deleted_at == None
        ).first()
        if existing:
            return RedirectResponse(url=f"/album/{existing.id}", status_code=303)

    album = Album(
        discogs_id=discogs_id,
        user_id=uid,
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


# ── Duelo de discos ──────────────────────────────────────
@router.get("/api/duel")
async def duel_albums(
    request: Request,
    fmt: str = "",
    genre: str = "",
    year_from: int = None,
    year_to: int = None,
    db: Session = Depends(get_db),
):
    username = get_current_user(request)

    base = db.query(Album).filter(Album.deleted_at == None)
    if username:
        user_obj = _get_user_obj(username, db)
        base = base.filter(Album.user_id == user_obj.id)
    else:
        admin = db.query(User).filter(User.is_admin == True).first()
        if admin:
            base = base.filter(Album.user_id == admin.id)

    if fmt:
        base = base.filter(Album.format_type.ilike(f"%{fmt}%"))
    if genre:
        base = base.filter(Album.genre.ilike(f"%{genre}%"))
    if year_from is not None:
        base = base.filter(Album.year >= year_from)
    if year_to is not None:
        base = base.filter(Album.year <= year_to)

    ids = [r[0] for r in base.with_entities(Album.id).all()]
    if len(ids) < 2:
        return JSONResponse({"error": "Se necesitan al menos 2 discos"})

    picked = random.sample(ids, 2)
    albums = db.query(Album).filter(Album.id.in_(picked)).all()
    result = []
    for a in albums:
        result.append({
            "id": a.id,
            "title": a.title,
            "artist": a.artist,
            "year": a.year,
            "cover_url": a.cover_url,
            "format_type": a.format_type,
            "score": a.score,
        })
    return JSONResponse(result)


# ── Slot machine ─────────────────────────────────────────
@router.get("/api/slot")
async def slot_machine(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)

    base = db.query(Album).filter(Album.deleted_at == None)
    if username:
        user_obj = _get_user_obj(username, db)
        base = base.filter(Album.user_id == user_obj.id)
    else:
        admin = db.query(User).filter(User.is_admin == True).first()
        if admin:
            base = base.filter(Album.user_id == admin.id)

    ids = [r[0] for r in base.with_entities(Album.id).all()]
    if len(ids) < 1:
        return JSONResponse({"error": "No hay discos"})

    # Elegir 3 discos (podría repetirse para jackpot)
    picked = [random.choice(ids) for _ in range(3)]
    albums = db.query(Album).filter(Album.id.in_(picked)).all()

    # Mapear id -> album para mantener el orden de picked (con repeticiones)
    album_map = {a.id: a for a in albums}
    result = []
    for pid in picked:
        a = album_map[pid]
        result.append({
            "id": a.id,
            "title": a.title,
            "artist": a.artist,
            "year": a.year,
            "cover_url": a.cover_url,
            "format_type": a.format_type,
            "score": a.score,
        })

    # Detectar jackpot: los 3 tienen el mismo id
    is_jackpot = len(set(picked)) == 1

    return JSONResponse({"reels": result, "jackpot": is_jackpot})


# ── Quiz: adivina la portada ────────────────────────────
@router.get("/api/quiz")
async def quiz_album(
    request: Request,
    db: Session = Depends(get_db),
):
    username = get_current_user(request)

    base = db.query(Album).filter(Album.deleted_at == None, Album.cover_url != None)
    if username:
        user_obj = _get_user_obj(username, db)
        base = base.filter(Album.user_id == user_obj.id)
    else:
        admin = db.query(User).filter(User.is_admin == True).first()
        if admin:
            base = base.filter(Album.user_id == admin.id)

    ids = [r[0] for r in base.with_entities(Album.id).all()]
    if len(ids) < 3:
        return JSONResponse({"error": "Se necesitan al menos 3 discos con portada"})

    picked = random.sample(ids, 3)
    albums = db.query(Album).filter(Album.id.in_(picked)).all()
    album_map = {a.id: a for a in albums}

    # El primero es el correcto
    correct = album_map[picked[0]]
    options = []
    for pid in picked:
        a = album_map[pid]
        options.append({
            "id": a.id,
            "title": a.title,
            "artist": a.artist,
        })

    random.shuffle(options)

    return JSONResponse({
        "cover_url": correct.cover_url,
        "options": options,
        "correct_id": correct.id,
    })


# ── Recomendación del día ───────────────────────────────
REASONS = [
    "Porque hoy merecés algo increíble 🎧",
    "Un clásico que no puede faltar en tu día ✨",
    "Para empezar el día con buen ritmo 🎶",
    "Ideal para una tarde tranquila ☕",
    "Subile el volumen a este discazo 🔊",
    "Porque este disco nunca falla 🔥",
    "Perfecto para escuchar de punta a punta 🌟",
    "Un viaje musical que tenés que hacer 🚀",
]

@router.get("/api/recommend")
async def recommend_album(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)

    base = db.query(Album).filter(Album.deleted_at == None)
    if username:
        user_obj = _get_user_obj(username, db)
        base = base.filter(Album.user_id == user_obj.id)
    else:
        admin = db.query(User).filter(User.is_admin == True).first()
        if admin:
            base = base.filter(Album.user_id == admin.id)

    ids = [r[0] for r in base.with_entities(Album.id).all()]
    if not ids:
        return JSONResponse({"error": "No hay discos"})

    # Usar la fecha como seed para que sea el mismo disco todo el dia
    today = date.today().isoformat()
    seed = hashlib.md5((today + str(ids)).encode()).hexdigest()
    rng = random.Random(seed)
    picked_id = rng.choice(ids)

    album = db.query(Album).filter(Album.id == picked_id).first()
    reason = rng.choice(REASONS)

    return JSONResponse({
        "id": album.id,
        "title": album.title,
        "artist": album.artist,
        "year": album.year,
        "cover_url": album.cover_url,
        "format_type": album.format_type,
        "reason": reason,
    })
