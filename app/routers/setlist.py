import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.album import Album
from app.models.crate import Crate
from app.models.user import User
from app.auth import get_current_user
from app.services.discogs import fetch_release_details

router    = APIRouter(prefix="/setlist")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def setlist_index(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user_obj = db.query(User).filter(User.username == username).first()
    albums = (
        db.query(Album)
        .filter(Album.user_id == user_obj.id, Album.deleted_at == None)
        .order_by(Album.artist, Album.title)
        .all()
    )
    crates = (
        db.query(Crate)
        .filter(Crate.user_id == user_obj.id)
        .order_by(Crate.position)
        .all()
    )
    return templates.TemplateResponse("setlist/index.html", {
        "request": request,
        "user":    username,
        "albums":  albums,
        "crates":  crates,
    })


@router.post("/videos")
async def setlist_videos(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"videos": []}, status_code=401)

    body      = await request.json()
    album_ids = body.get("album_ids", [])
    user_obj  = db.query(User).filter(User.username == username).first()
    albums    = db.query(Album).filter(
        Album.id.in_(album_ids), Album.user_id == user_obj.id, Album.deleted_at == None
    ).all()

    extras = await asyncio.gather(*[
        fetch_release_details(a.discogs_id) if a.discogs_id else asyncio.sleep(0, result=None)
        for a in albums
    ])

    videos = []
    for album, extra in zip(albums, extras):
        if not extra or not extra.get("videos"):
            continue
        for v in extra["videos"]:
            url = v.get("url", "")
            if "youtube" in url or "youtu.be" in url:
                videos.append({
                    "album":  album.title,
                    "artist": album.artist,
                    "title":  v.get("title", ""),
                    "url":    url,
                })

    return JSONResponse({"videos": videos})
