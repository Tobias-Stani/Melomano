import base64

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.featured import FeaturedItem
from app.models.album import Album
from app.models.concert import Concert
from app.models.user import User
from app.auth import get_current_user

router    = APIRouter()
templates = Jinja2Templates(directory="app/templates")

EMOJIS = {1:'😞',2:'😔',3:'😐',4:'🙂',5:'😊',6:'😁',7:'🤩',8:'🔥',9:'💫',10:'🌟'}


def _get_user_obj(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def _load_featured(db: Session, user_id: int):
    rows = db.query(FeaturedItem).filter(FeaturedItem.user_id == user_id).all()
    albums   = {}
    concerts = {}
    for row in rows:
        if row.type == "album":
            album = db.query(Album).filter(Album.id == row.item_id).first()
            if album:
                albums[row.slot] = album
        elif row.type == "concert":
            concert = db.query(Concert).filter(Concert.id == row.item_id).first()
            if concert:
                concerts[row.slot] = concert
    return albums, concerts


# ── Perfil publico por usuario ────────────────────────────

@router.get("/perfil", response_class=HTMLResponse)
async def perfil_index(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if username:
        return RedirectResponse(url=f"/perfil/{username}", status_code=302)
    users = db.query(User).order_by(User.created_at).all()
    return templates.TemplateResponse("perfil_lista.html", {
        "request": request, "user": None, "users": users,
    })


@router.get("/perfil/editar", response_class=HTMLResponse)
async def perfil_edit_info(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user_obj = _get_user_obj(db, username)
    return templates.TemplateResponse("perfil_edit_info.html", {
        "request": request, "user": username, "profile": user_obj,
    })


@router.post("/perfil/editar")
async def perfil_save_info(
    request: Request,
    display_name: str = Form(""),
    bio: str = Form(""),
    avatar: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user_obj = _get_user_obj(db, username)
    if not user_obj:
        return RedirectResponse(url="/login", status_code=302)

    user_obj.display_name = display_name or None
    user_obj.bio          = bio or None

    if avatar and avatar.filename:
        raw = await avatar.read()
        if raw:
            user_obj.avatar = f"data:{avatar.content_type};base64,{base64.b64encode(raw).decode()}"

    db.commit()
    return RedirectResponse(url=f"/perfil/{username}", status_code=303)


@router.get("/perfil/seleccionar-favoritos", response_class=HTMLResponse)
async def perfil_select_favorites(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user_obj = _get_user_obj(db, username)
    albums, concerts = _load_featured(db, user_obj.id)
    all_albums   = db.query(Album).order_by(Album.artist, Album.title).all()
    all_concerts = db.query(Concert).order_by(Concert.date.desc()).all()
    return templates.TemplateResponse("perfil_edit_favorites.html", {
        "request":      request,
        "user":         username,
        "profile":      user_obj,
        "albums":       albums,
        "concerts":     concerts,
        "all_albums":   all_albums,
        "all_concerts": all_concerts,
    })


@router.post("/perfil/seleccionar-favoritos")
async def perfil_save_favorites(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user_obj = _get_user_obj(db, username)

    form = await request.form()
    db.query(FeaturedItem).filter(FeaturedItem.user_id == user_obj.id).delete()

    for slot in range(1, 6):
        val = form.get(f"album_{slot}", "").strip()
        if val:
            db.add(FeaturedItem(user_id=user_obj.id, type="album", item_id=int(val), slot=slot))

    for slot in range(1, 4):
        val = form.get(f"concert_{slot}", "").strip()
        if val:
            db.add(FeaturedItem(user_id=user_obj.id, type="concert", item_id=int(val), slot=slot))

    db.commit()
    return RedirectResponse(url=f"/perfil/{username}", status_code=303)


@router.get("/perfil/{username}", response_class=HTMLResponse)
async def perfil_usuario(username: str, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request)
    profile = _get_user_obj(db, username)
    if not profile:
        return RedirectResponse(url="/perfil", status_code=302)
    albums, concerts = _load_featured(db, profile.id)
    return templates.TemplateResponse("perfil_user.html", {
        "request":      request,
        "user":         current_user,
        "profile":      profile,
        "albums":       albums,
        "concerts":     concerts,
        "emojis":       EMOJIS,
        "is_own":       current_user == username,
    })


# ── Toggle favorito ───────────────────────────────────────

@router.post("/perfil/toggle")
async def perfil_toggle(
    request: Request,
    type: str = Form(...),
    item_id: int = Form(...),
    redirect_to: str = Form("/perfil"),
    db: Session = Depends(get_db),
):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user_obj = _get_user_obj(db, username)

    existing = db.query(FeaturedItem).filter(
        FeaturedItem.user_id == user_obj.id,
        FeaturedItem.type == type,
        FeaturedItem.item_id == item_id,
    ).first()

    if existing:
        db.delete(existing)
    else:
        max_slot  = 5 if type == "album" else 3
        used_slots = {r.slot for r in db.query(FeaturedItem).filter(
            FeaturedItem.user_id == user_obj.id, FeaturedItem.type == type
        ).all()}
        free_slot = next((s for s in range(1, max_slot + 1) if s not in used_slots), None)
        if free_slot:
            db.add(FeaturedItem(user_id=user_obj.id, type=type, item_id=item_id, slot=free_slot))
        else:
            oldest = db.query(FeaturedItem).filter(
                FeaturedItem.user_id == user_obj.id, FeaturedItem.type == type
            ).order_by(FeaturedItem.created_at).first()
            if oldest:
                oldest.item_id = item_id

    db.commit()
    return RedirectResponse(url=redirect_to, status_code=303)


# ── Reordenar ─────────────────────────────────────────────

@router.post("/perfil/reorder")
async def perfil_reorder(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    user_obj = _get_user_obj(db, username)
    body  = await request.json()
    type_ = body.get("type")
    order = body.get("order", [])
    if type_ not in ("album", "concert"):
        return JSONResponse({"error": "tipo invalido"}, status_code=400)

    rows = db.query(FeaturedItem).filter(
        FeaturedItem.user_id == user_obj.id, FeaturedItem.type == type_
    ).all()
    rows_by_id = {r.item_id: r for r in rows}
    for slot, item_id in enumerate(order, start=1):
        if item_id in rows_by_id:
            rows_by_id[item_id].slot = slot
    db.commit()
    return JSONResponse({"ok": True})
