from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.album import Album
from app.models.wishlist_category import WishlistCategory
from app.models.wishlist_item import WishlistItem

router    = APIRouter(prefix="/u")
templates = Jinja2Templates(directory="app/templates")


def _get_user_or_404(username: str, db: Session) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


@router.get("/{username}/coleccion", response_class=HTMLResponse)
async def public_collection(username: str, request: Request, db: Session = Depends(get_db)):
    user = _get_user_or_404(username, db)
    if not user.collection_public:
        return templates.TemplateResponse("public/privado.html", {
            "request": request, "owner": user, "tipo": "colección",
        }, status_code=403)
    albums = (
        db.query(Album)
        .filter(Album.user_id == user.id, Album.deleted_at == None, Album.owned == True)
        .order_by(Album.artist)
        .all()
    )
    return templates.TemplateResponse("public/coleccion.html", {
        "request":  request,
        "owner":    user,
        "albums":   albums,
    })


@router.get("/{username}/wishlist", response_class=HTMLResponse)
async def public_wishlist(username: str, request: Request, db: Session = Depends(get_db)):
    user = _get_user_or_404(username, db)
    if not user.wishlist_public:
        return templates.TemplateResponse("public/privado.html", {
            "request": request, "owner": user, "tipo": "wishlist",
        }, status_code=403)
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
    return templates.TemplateResponse("public/wishlist.html", {
        "request":       request,
        "owner":         user,
        "categories":    categories,
        "uncategorized": uncategorized,
    })
