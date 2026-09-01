import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models.album import Album
from app.models.crate import Crate
from app.models.user import User
from app.models.saved_setlist import SavedSetlist
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
    saved = (
        db.query(SavedSetlist)
        .filter(SavedSetlist.user_id == user_obj.id)
        .order_by(desc(SavedSetlist.created_at))
        .all()
    )
    return templates.TemplateResponse("setlist/index.html", {
        "request": request,
        "user":    username,
        "albums":  albums,
        "crates":  crates,
        "saved":   saved,
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


@router.post("/save")
async def setlist_save(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body      = await request.json()
    content   = (body.get("content") or "").strip()
    if not content:
        return JSONResponse({"error": "empty content"}, status_code=400)

    user_obj = db.query(User).filter(User.username == username).first()
    setlist  = SavedSetlist(
        user_id          = user_obj.id,
        name             = (body.get("name") or "").strip() or "Setlist sin nombre",
        content          = content,
        duration_minutes = body.get("duration_minutes"),
        num_tracks       = body.get("num_tracks"),
        user_context     = body.get("user_context") or None,
    )
    db.add(setlist)
    db.commit()
    db.refresh(setlist)
    return JSONResponse({"id": setlist.id})


@router.get("/{setlist_id}/delete")
async def setlist_delete(setlist_id: int, request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user_obj = db.query(User).filter(User.username == username).first()
    item = db.query(SavedSetlist).filter(
        SavedSetlist.id == setlist_id,
        SavedSetlist.user_id == user_obj.id,
    ).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/setlist", status_code=303)
