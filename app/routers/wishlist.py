import re
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.album import Album
from app.models.wishlist_category import WishlistCategory
from app.models.wishlist_item import WishlistItem
from app.services.discogs import search_discogs, fetch_release_details

router    = APIRouter(prefix="/wishlist")
templates = Jinja2Templates(directory="app/templates")


def _user_obj(username: str, db: Session) -> User | None:
    return db.query(User).filter(User.username == username).first()


# ── Board principal ───────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def wishlist_board(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user = _user_obj(username, db)

    categories = (
        db.query(WishlistCategory)
        .filter(WishlistCategory.user_id == user.id)
        .order_by(WishlistCategory.position)
        .all()
    )
    uncategorized = (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == user.id, WishlistItem.category_id == None)
        .order_by(WishlistItem.created_at)
        .all()
    )
    return templates.TemplateResponse("wishlist/index.html", {
        "request":      request,
        "user":         username,
        "user_obj":     user,
        "categories":   categories,
        "uncategorized": uncategorized,
    })


# ── Búsqueda Discogs (JSON) ───────────────────────────────

@router.get("/search")
async def wishlist_search(request: Request, q: str = "", db: Session = Depends(get_db)):
    if not get_current_user(request):
        return JSONResponse({"results": []}, status_code=401)
    if not q or len(q) < 2:
        return JSONResponse({"results": []})
    results = await search_discogs(q)
    return JSONResponse({"results": results[:10]})


# ── Agregar item ──────────────────────────────────────────

@router.post("/items")
async def wishlist_add(
    request: Request,
    discogs_id: int    = Form(None),
    title: str         = Form(...),
    artist: str        = Form(...),
    year: int          = Form(None),
    genre: str         = Form(""),
    label: str         = Form(""),
    cover_url: str     = Form(""),
    discogs_url: str   = Form(""),
    format_type: str   = Form(""),
    category_id: int   = Form(None),
    db: Session        = Depends(get_db),
):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    user = _user_obj(username, db)

    item = WishlistItem(
        user_id     = user.id,
        category_id = category_id or None,
        discogs_id  = discogs_id or None,
        title       = title,
        artist      = artist,
        year        = year or None,
        genre       = genre or None,
        label       = label or None,
        cover_url   = cover_url or None,
        discogs_url = discogs_url or None,
        format_type = format_type or None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return JSONResponse({
        "ok": True,
        "item": {
            "id":          item.id,
            "category_id": item.category_id,
            "discogs_id":  item.discogs_id,
            "title":       item.title,
            "artist":      item.artist,
            "year":        item.year,
            "format_type": item.format_type,
            "cover_url":   item.cover_url,
            "discogs_url": item.discogs_url,
            "notes":       item.notes,
        }
    })


# ── Resolver URL de Discogs ───────────────────────────────

@router.get("/resolve-discogs")
async def resolve_discogs_url(url: str, request: Request):
    if not get_current_user(request):
        return JSONResponse({"error": "no autorizado"}, status_code=401)

    m = re.search(r'/release(?:s)?/(\d+)', url)
    if not m:
        try:
            discogs_id = int(url.strip())
        except ValueError:
            return JSONResponse({"error": "URL o ID no válido. Pegá el link de Discogs, ej: https://www.discogs.com/release/12345"}, status_code=400)
    else:
        discogs_id = int(m.group(1))

    data = await fetch_release_details(discogs_id)
    if not data:
        return JSONResponse({"error": "No se pudo obtener info de Discogs. Verificá el link."}, status_code=404)

    return JSONResponse({
        "discogs_id":  discogs_id,
        "title":       data.get("title", ""),
        "artist":      data.get("artist", ""),
        "year":        data.get("year"),
        "genre":       data.get("genre"),
        "label":       data.get("label"),
        "cover_url":   data.get("cover_url"),
        "discogs_url": data.get("discogs_url"),
        "format_type": data.get("format_type"),
    })


# ── Detalle de un item (Discogs extra) ───────────────────

@router.get("/items/{item_id}/detail")
async def wishlist_item_detail(item_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    item = db.query(WishlistItem).filter(WishlistItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404)
    extra = await fetch_release_details(item.discogs_id) if item.discogs_id else None
    return JSONResponse({
        "id":          item.id,
        "discogs_id":  item.discogs_id,
        "title":       item.title,
        "artist":      item.artist,
        "year":        item.year,
        "genre":       item.genre,
        "label":       item.label,
        "cover_url":   item.cover_url,
        "discogs_url": item.discogs_url,
        "format_type": item.format_type,
        "notes":       item.notes,
        "extra":       extra,
    })


# ── Mover item a categoría (drag & drop) ─────────────────

@router.post("/items/{item_id}/move")
async def wishlist_move(item_id: int, request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    user = _user_obj(username, db)

    item = db.query(WishlistItem).filter(
        WishlistItem.id == item_id, WishlistItem.user_id == user.id
    ).first()
    if not item:
        raise HTTPException(status_code=404)

    body = await request.json()
    cat_id = body.get("category_id")
    item.category_id = int(cat_id) if cat_id else None
    db.commit()
    return JSONResponse({"ok": True})


# ── Editar notas del item ─────────────────────────────────

@router.post("/items/{item_id}/notes")
async def wishlist_notes(item_id: int, request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    user = _user_obj(username, db)

    item = db.query(WishlistItem).filter(
        WishlistItem.id == item_id, WishlistItem.user_id == user.id
    ).first()
    if not item:
        raise HTTPException(status_code=404)

    body = await request.json()
    item.notes = body.get("notes", "")
    db.commit()
    return JSONResponse({"ok": True})


# ── Eliminar item ─────────────────────────────────────────

@router.delete("/items/{item_id}")
async def wishlist_delete(item_id: int, request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    user = _user_obj(username, db)

    item = db.query(WishlistItem).filter(
        WishlistItem.id == item_id, WishlistItem.user_id == user.id
    ).first()
    if not item:
        raise HTTPException(status_code=404)
    db.delete(item)
    db.commit()
    return JSONResponse({"ok": True})


# ── Promover a colección ──────────────────────────────────

@router.post("/items/{item_id}/promote")
async def wishlist_promote(item_id: int, request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    user = _user_obj(username, db)

    item = db.query(WishlistItem).filter(
        WishlistItem.id == item_id, WishlistItem.user_id == user.id
    ).first()
    if not item:
        raise HTTPException(status_code=404)

    existing = db.query(Album).filter(
        Album.discogs_id == item.discogs_id,
        Album.user_id == user.id,
        Album.deleted_at == None,
    ).first() if item.discogs_id else None

    if not existing:
        album = Album(
            user_id     = user.id,
            discogs_id  = item.discogs_id,
            title       = item.title,
            artist      = item.artist,
            year        = item.year,
            genre       = item.genre,
            label       = item.label,
            cover_url   = item.cover_url,
            discogs_url = item.discogs_url,
            format_type = item.format_type,
            owned       = True,
            listened    = False,
            wishlist    = False,
        )
        db.add(album)

    db.delete(item)
    db.commit()
    return JSONResponse({"ok": True})


# ── Crear categoría ───────────────────────────────────────

@router.post("/categories")
async def category_create(
    request: Request,
    name: str    = Form(...),
    color: str   = Form("#c49268"),
    db: Session  = Depends(get_db),
):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user = _user_obj(username, db)

    max_pos = db.query(WishlistCategory).filter(
        WishlistCategory.user_id == user.id
    ).count()
    cat = WishlistCategory(user_id=user.id, name=name, color=color, position=max_pos)
    db.add(cat)
    db.commit()
    return RedirectResponse(url="/wishlist", status_code=303)


# ── Editar categoría ──────────────────────────────────────

@router.post("/categories/{cat_id}/edit")
async def category_edit(
    cat_id: int, request: Request,
    name: str   = Form(...),
    color: str  = Form("#c49268"),
    db: Session = Depends(get_db),
):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user = _user_obj(username, db)

    cat = db.query(WishlistCategory).filter(
        WishlistCategory.id == cat_id, WishlistCategory.user_id == user.id
    ).first()
    if not cat:
        raise HTTPException(status_code=404)
    cat.name  = name
    cat.color = color
    db.commit()
    return RedirectResponse(url="/wishlist", status_code=303)


# ── Eliminar categoría ────────────────────────────────────

@router.delete("/categories/{cat_id}")
async def category_delete(cat_id: int, request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    user = _user_obj(username, db)

    cat = db.query(WishlistCategory).filter(
        WishlistCategory.id == cat_id, WishlistCategory.user_id == user.id
    ).first()
    if not cat:
        raise HTTPException(status_code=404)

    # Mover items a sin categoría
    db.query(WishlistItem).filter(WishlistItem.category_id == cat_id).update(
        {"category_id": None}
    )
    db.delete(cat)
    db.commit()
    return JSONResponse({"ok": True})


# ── Reordenar columnas ────────────────────────────────────

@router.post("/categories/reorder")
async def category_reorder(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    user = _user_obj(username, db)

    body  = await request.json()
    order = body.get("order", [])
    cats  = {c.id: c for c in db.query(WishlistCategory).filter(
        WishlistCategory.user_id == user.id
    ).all()}
    for pos, cat_id in enumerate(order):
        if cat_id in cats:
            cats[cat_id].position = pos
    db.commit()
    return JSONResponse({"ok": True})
