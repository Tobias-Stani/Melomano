from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.featured import FeaturedItem
from app.models.album import Album
from app.models.concert import Concert
from app.auth import get_current_user

router    = APIRouter()
templates = Jinja2Templates(directory="app/templates")

EMOJIS = {1:'😞',2:'😔',3:'😐',4:'🙂',5:'😊',6:'😁',7:'🤩',8:'🔥',9:'💫',10:'🌟'}


def _load_featured(db: Session):
    rows = db.query(FeaturedItem).all()
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


@router.get("/perfil", response_class=HTMLResponse)
async def perfil(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    albums, concerts = _load_featured(db)
    return templates.TemplateResponse("perfil.html", {
        "request":  request,
        "user":     user,
        "albums":   albums,
        "concerts": concerts,
        "emojis":   EMOJIS,
    })


@router.get("/perfil/editar", response_class=HTMLResponse)
async def perfil_edit(request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    user = get_current_user(request)
    albums, concerts = _load_featured(db)
    all_albums   = db.query(Album).order_by(Album.artist, Album.title).all()
    all_concerts = db.query(Concert).order_by(Concert.date.desc()).all()
    return templates.TemplateResponse("perfil_edit.html", {
        "request":      request,
        "user":         user,
        "albums":       albums,
        "concerts":     concerts,
        "all_albums":   all_albums,
        "all_concerts": all_concerts,
    })


@router.post("/perfil/toggle")
async def perfil_toggle(
    request: Request,
    type: str = Form(...),
    item_id: int = Form(...),
    redirect_to: str = Form("/perfil"),
    db: Session = Depends(get_db),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)

    existing = db.query(FeaturedItem).filter(
        FeaturedItem.type == type,
        FeaturedItem.item_id == item_id,
    ).first()

    if existing:
        db.delete(existing)
    else:
        max_slot = 5 if type == "album" else 3
        used_slots = {r.slot for r in db.query(FeaturedItem).filter(FeaturedItem.type == type).all()}
        free_slot = next((s for s in range(1, max_slot + 1) if s not in used_slots), None)
        if free_slot:
            db.add(FeaturedItem(type=type, item_id=item_id, slot=free_slot))
        else:
            # Reemplaza el slot mas antiguo
            oldest = db.query(FeaturedItem).filter(FeaturedItem.type == type).order_by(FeaturedItem.created_at).first()
            if oldest:
                oldest.item_id = item_id

    db.commit()
    return RedirectResponse(url=redirect_to, status_code=303)


@router.post("/perfil/editar")
async def perfil_save(request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)

    form = await request.form()

    db.query(FeaturedItem).delete()

    for slot in range(1, 6):
        val = form.get(f"album_{slot}", "").strip()
        if val:
            db.add(FeaturedItem(type="album", item_id=int(val), slot=slot))

    for slot in range(1, 4):
        val = form.get(f"concert_{slot}", "").strip()
        if val:
            db.add(FeaturedItem(type="concert", item_id=int(val), slot=slot))

    db.commit()
    return RedirectResponse(url="/perfil", status_code=303)
