from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.movie import Movie, FORMATS
from app.services import tmdb
from app.utils.image import compress_to_b64

router    = APIRouter(prefix="/peliculas")
templates = Jinja2Templates(directory="app/templates")


def _user_obj(username: str, db: Session) -> User | None:
    return db.query(User).filter(User.username == username).first()


def _set_shares(movie: Movie, user_ids: list[int], db: Session):
    ids = {i for i in user_ids if i != movie.user_id}
    movie.shared_with = db.query(User).filter(User.id.in_(ids)).all() if ids else []


async def _photo_data_url(photo: UploadFile | None) -> str | None:
    if not photo or not photo.filename:
        return None
    raw = await photo.read()
    if not raw:
        return None
    encoded, mime = compress_to_b64(raw)
    return f"data:{mime};base64,{encoded}"


# ── Listado (propio o de otro usuario con ?u=) ────────────

@router.get("", response_class=HTMLResponse)
async def movies_list(request: Request, u: str = None, f: str = None, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)

    target = _user_obj(u or username, db)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    query = db.query(Movie).filter(
        (Movie.user_id == target.id) | Movie.shared_with.any(User.id == target.id)
    )
    if f in FORMATS:
        query = query.filter(Movie.format_type == f)
    movies = query.order_by(Movie.title).all()

    return templates.TemplateResponse("peliculas/index.html", {
        "request":  request,
        "user":     username,
        "target":   target,
        "is_own":   target.username == username,
        "movies":   movies,
        "formats":  FORMATS,
        "f":        f if f in FORMATS else None,
        "users":    db.query(User).order_by(User.username).all(),
    })


# ── Búsqueda TMDB (JSON) ──────────────────────────────────

@router.get("/buscar")
async def movies_search(request: Request, q: str = ""):
    if not get_current_user(request):
        return JSONResponse({"results": []}, status_code=401)
    if not tmdb.enabled() or len(q) < 2:
        return JSONResponse({"results": []})
    try:
        return JSONResponse({"results": await tmdb.search_movies(q)})
    except Exception:
        return JSONResponse({"results": [], "error": "No se pudo consultar TMDB"}, status_code=502)


@router.get("/portadas/{tmdb_id}")
async def movie_posters(tmdb_id: int, request: Request):
    if not get_current_user(request):
        return JSONResponse({"posters": []}, status_code=401)
    if not tmdb.enabled():
        return JSONResponse({"posters": []})
    try:
        return JSONResponse({"posters": await tmdb.fetch_posters(tmdb_id)})
    except Exception:
        return JSONResponse({"posters": [], "error": "No se pudo consultar TMDB"}, status_code=502)


# ── Alta ──────────────────────────────────────────────────

@router.get("/nueva", response_class=HTMLResponse)
async def movie_new(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("peliculas/form.html", {
        "request": request, "user": username, "formats": FORMATS, "tmdb_enabled": tmdb.enabled(),
        "other_users": db.query(User).filter(User.username != username).order_by(User.username).all(),
    })


@router.post("/nueva")
async def movie_create(
    request: Request,
    tmdb_id: int       = Form(None),
    title: str         = Form(""),
    year: int          = Form(None),
    poster_url: str    = Form(""),
    format_type: str   = Form("dvd"),
    notes: str         = Form(""),
    share_with: list[int] = Form([]),
    photo: UploadFile  = File(None),
    db: Session        = Depends(get_db),
):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user = _user_obj(username, db)

    data = {}
    if tmdb_id and tmdb.enabled():
        try:
            data = await tmdb.fetch_movie(tmdb_id)
        except Exception:
            data = {}
    if not data:
        if not title.strip():
            raise HTTPException(status_code=400, detail="Falta el título")
        data = {"title": title.strip(), "year": year or None}
    if poster_url:
        data["poster_url"] = poster_url  # portada elegida pisa la default de TMDB

    movie = Movie(
        user_id       = user.id,
        format_type   = format_type if format_type in FORMATS else "dvd",
        notes         = notes or None,
        edition_photo = await _photo_data_url(photo),
        **data,
    )
    _set_shares(movie, share_with, db)
    db.add(movie)
    db.commit()
    return RedirectResponse(url=f"/peliculas/{movie.id}", status_code=303)


# ── Detalle ───────────────────────────────────────────────

@router.get("/{movie_id}", response_class=HTMLResponse)
async def movie_detail(movie_id: int, request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    movie = db.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404)
    me = _user_obj(username, db)
    return templates.TemplateResponse("peliculas/detail.html", {
        "request": request, "user": username, "movie": movie, "owner": movie.owner,
        "is_own":   movie.can_edit(me),          # dueño o co-dueño: puede editar
        "is_owner": movie.user_id == me.id,      # solo el dueño maneja con quién se comparte
        "formats":  FORMATS,
        "other_users": db.query(User).filter(User.id != movie.user_id).order_by(User.username).all(),
    })


# ── Editar formato / notas / foto ─────────────────────────

@router.post("/{movie_id}/editar")
async def movie_update(
    movie_id: int,
    request: Request,
    format_type: str   = Form("dvd"),
    notes: str         = Form(""),
    poster_url: str    = Form(""),
    share_with: list[int] = Form([]),
    photo: UploadFile  = File(None),
    db: Session        = Depends(get_db),
):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user  = _user_obj(username, db)
    movie = db.query(Movie).filter(Movie.id == movie_id).first()
    if not movie or not movie.can_edit(user):
        raise HTTPException(status_code=404)

    if movie.user_id == user.id:
        _set_shares(movie, share_with, db)

    if format_type in FORMATS:
        movie.format_type = format_type
    movie.notes = notes or None
    if poster_url:
        movie.poster_url = poster_url
    new_photo = await _photo_data_url(photo)
    if new_photo:
        movie.edition_photo = new_photo
    db.commit()
    return RedirectResponse(url=f"/peliculas/{movie.id}", status_code=303)


# ── Eliminar ──────────────────────────────────────────────

@router.post("/{movie_id}/eliminar")
async def movie_delete(movie_id: int, request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    user  = _user_obj(username, db)
    movie = db.query(Movie).filter(Movie.id == movie_id).first()
    if movie and movie.user_id == user.id:
        db.delete(movie)                      # el dueño la borra para todos
        db.commit()
    elif movie and user in movie.shared_with:
        movie.shared_with.remove(user)        # un co-dueño solo la saca de su colección
        db.commit()
    return RedirectResponse(url="/peliculas", status_code=303)
