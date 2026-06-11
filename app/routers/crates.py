import os
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import asc

from app.database import get_db
from app.models.crate import Crate
from app.models.album import Album
from app.models.user import User
from app.auth import get_current_user

router    = APIRouter(prefix="/bateas")
templates = Jinja2Templates(directory="app/templates")

ACCENT_COLORS = [
    "#c49268", "#a97348", "#8a5a35", "#6b4328",
    "#4a7c8a", "#2e6b7a", "#3d7a5a", "#2d6b4a",
    "#7a5a8a", "#9a4a7a", "#b05a8a", "#7a3a6a",
    "#c05a4a", "#a04535", "#c4705a", "#b06050",
    "#b89a30", "#a07a20", "#c4a040", "#8a6a18",
    "#5a6a7a", "#4a5a6a", "#6a7a6a", "#5a6a5a",
]

FORMAT_ORDER = ["Vinyl", "CD", "Cassette", "Digital", "SACD", "Blu-ray Audio"]


def _require_user(request: Request, db: Session):
    username = get_current_user(request)
    if not username:
        return None, None
    user = db.query(User).filter(User.username == username).first()
    return username, user


def _public_user(db: Session):
    admin_name = os.getenv("APP_USERNAME", "admin")
    user = db.query(User).filter(User.username == admin_name).first()
    return user or db.query(User).first()


def _fmt_key(k):
    try:
        return (0, FORMAT_ORDER.index(k))
    except ValueError:
        return (1, k)


# ── Vista principal ────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
async def crates_view(request: Request, db: Session = Depends(get_db)):
    username, user = _require_user(request, db)
    is_owner = bool(user)
    if not user:
        user = _public_user(db)
    if not user:
        return templates.TemplateResponse("crates/index.html", {
            "request": request, "user": None, "is_owner": False,
            "crates": [], "crate_previews": {}, "unassigned_by_format": {},
            "unassigned_total": 0, "accent_colors": ACCENT_COLORS,
        })

    crates = (
        db.query(Crate)
        .filter(Crate.user_id == user.id)
        .order_by(asc(Crate.position))
        .all()
    )

    # Solo las primeras 4 portadas por batea para el preview
    crate_previews = {}
    crate_counts   = {}
    for c in crates:
        albums = (
            db.query(Album)
            .filter(Album.crate_id == c.id, Album.deleted_at == None)
            .order_by(Album.artist)
            .all()
        )
        crate_previews[c.id] = albums[:4]
        crate_counts[c.id]   = len(albums)

    # Sin ubicar (solo para el dueño)
    unassigned_by_format = {}
    unassigned_total = 0
    if is_owner:
        unassigned_raw = (
            db.query(Album)
            .filter(Album.user_id == user.id, Album.crate_id == None,
                    Album.deleted_at == None, Album.owned == True)
            .order_by(Album.format_type, Album.artist)
            .all()
        )
        unassigned_total = len(unassigned_raw)
        for album in unassigned_raw:
            fmt = album.format_type or "Sin formato"
            unassigned_by_format.setdefault(fmt, []).append(album)
        unassigned_by_format = dict(
            sorted(unassigned_by_format.items(), key=lambda kv: _fmt_key(kv[0]))
        )

    return templates.TemplateResponse("crates/index.html", {
        "request":              request,
        "user":                 username,
        "is_owner":             is_owner,
        "crates":               crates,
        "crate_previews":       crate_previews,
        "crate_counts":         crate_counts,
        "unassigned_by_format": unassigned_by_format,
        "unassigned_total":     unassigned_total,
        "accent_colors":        ACCENT_COLORS,
    })


# ── Vista detalle de batea ─────────────────────────────────
@router.get("/{crate_id}", response_class=HTMLResponse)
async def crate_detail(crate_id: int, request: Request, db: Session = Depends(get_db)):
    username, user = _require_user(request, db)
    is_owner = bool(user)
    if not user:
        user = _public_user(db)
    if not user:
        return RedirectResponse(url="/bateas", status_code=302)

    crate = db.query(Crate).filter(Crate.id == crate_id, Crate.user_id == user.id).first()
    if not crate:
        return RedirectResponse(url="/bateas", status_code=302)

    albums = (
        db.query(Album)
        .filter(Album.crate_id == crate_id, Album.deleted_at == None)
        .order_by(Album.crate_position.asc().nullslast(), Album.artist)
        .all()
    )

    # Sin ubicar para poder agregar (solo dueño)
    unassigned = []
    if is_owner:
        unassigned = (
            db.query(Album)
            .filter(Album.user_id == user.id, Album.crate_id == None,
                    Album.deleted_at == None, Album.owned == True)
            .order_by(Album.format_type, Album.artist)
            .all()
        )

    return templates.TemplateResponse("crates/detail.html", {
        "request":    request,
        "user":       username,
        "is_owner":   is_owner,
        "crate":      crate,
        "albums":     albums,
        "unassigned": unassigned,
    })


# ── Crear batea ────────────────────────────────────────────
@router.post("")
async def create_crate(
    request: Request,
    name: str = Form(...),
    color: str = Form(""),
    db: Session = Depends(get_db),
):
    username, user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    max_pos = db.query(Crate).filter(Crate.user_id == user.id).count()
    crate = Crate(
        user_id=user.id,
        name=name,
        color=color or ACCENT_COLORS[max_pos % len(ACCENT_COLORS)],
        position=max_pos,
    )
    db.add(crate)
    db.commit()
    return RedirectResponse(url="/bateas", status_code=303)


# ── Renombrar batea ────────────────────────────────────────
@router.post("/{crate_id}/rename")
async def rename_crate(
    crate_id: int, request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    username, user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    crate = db.query(Crate).filter(Crate.id == crate_id, Crate.user_id == user.id).first()
    if crate:
        crate.name = name
        db.commit()
    return RedirectResponse(url=f"/bateas/{crate_id}", status_code=303)


# ── Eliminar batea ─────────────────────────────────────────
@router.get("/{crate_id}/delete")
async def delete_crate(crate_id: int, request: Request, db: Session = Depends(get_db)):
    username, user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    crate = db.query(Crate).filter(Crate.id == crate_id, Crate.user_id == user.id).first()
    if crate:
        db.query(Album).filter(Album.crate_id == crate_id).update({"crate_id": None})
        db.delete(crate)
        db.commit()
    return RedirectResponse(url="/bateas", status_code=303)


# ── Asignar / desasignar album ─────────────────────────────
@router.post("/assign")
async def assign_album(
    request: Request,
    album_id: int = Form(...),
    crate_id: int = Form(None),
    db: Session = Depends(get_db),
):
    username, user = _require_user(request, db)
    if not user:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    album = db.query(Album).filter(Album.id == album_id, Album.user_id == user.id).first()
    if album:
        album.crate_id = crate_id or None
        db.commit()
    return JSONResponse({"ok": True})


# ── Reordenar bateas ───────────────────────────────────────
@router.post("/reorder")
async def reorder_crates(request: Request, db: Session = Depends(get_db)):
    username, user = _require_user(request, db)
    if not user:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    data = await request.json()
    for i, cid in enumerate(data.get("order", [])):
        db.query(Crate).filter(Crate.id == cid, Crate.user_id == user.id).update({"position": i})
    db.commit()
    return JSONResponse({"ok": True})


# ── Reordenar álbumes dentro de una batea ─────────────────
@router.post("/{crate_id}/reorder-albums")
async def reorder_albums(crate_id: int, request: Request, db: Session = Depends(get_db)):
    username, user = _require_user(request, db)
    if not user:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    data = await request.json()
    for i, album_id in enumerate(data.get("order", [])):
        db.query(Album).filter(
            Album.id == album_id,
            Album.crate_id == crate_id,
            Album.user_id == user.id,
        ).update({"crate_position": i})
    db.commit()
    return JSONResponse({"ok": True})


# ── Guardar tamaño ─────────────────────────────────────────
@router.post("/{crate_id}/size")
async def save_size(crate_id: int, request: Request, db: Session = Depends(get_db)):
    username, user = _require_user(request, db)
    if not user:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    data    = await request.json()
    updates = {}
    if "height" in data:
        updates["height"]   = max(80, min(int(data["height"]), 800))
    if "col_span" in data:
        updates["col_span"] = max(1, min(int(data["col_span"]), 3))
    if updates:
        db.query(Crate).filter(Crate.id == crate_id, Crate.user_id == user.id).update(updates)
        db.commit()
    return JSONResponse({"ok": True, **updates})
