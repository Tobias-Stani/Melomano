from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.album import Album
from app.models.concert import Concert
from app.models.hifi_bar import HifiBar
from app.models.crate import Crate
from app.models.user import User
from app.auth import get_current_user
from app.services.ai_chat import chat_completion_stream, AIChatError
from app.services.discogs import fetch_release_details

router = APIRouter(prefix="/api/chat")

BASE_SYSTEM_PROMPT = (
    "Sos el asistente de Melomano, una app personal de colección de discos, "
    "recitales y bares hifi. Respondé corto, cordial y en español. "
    "Solo podés hablar de música, discos, recitales y bares hifi relacionados con "
    "los datos de esta app — no hables de otros temas (programación, noticias, etc.). "
    "Usá ÚNICAMENTE los datos reales que te paso abajo para responder sobre la colección "
    "del usuario; si no tenés el dato, decilo en vez de inventarlo. No podés modificar, "
    "eliminar ni crear nada — solo responder preguntas con la información dada. "
    "El precio más bajo, las copias en venta y los usuarios que tienen/quieren cada disco "
    "vienen de Discogs y solo están disponibles si el usuario ya los sincronizó con el botón "
    "'💰 Actualizar valores' de la galería; si un disco dice 'sin datos de mercado todavía', "
    "avisale que puede usar ese botón para obtenerlos."
)

MAX_HISTORY = 12  # mensajes (sin contar el system prompt)


def _build_user_context(db: Session, user_obj: User) -> str:
    albums_total = db.query(Album).filter(
        Album.user_id == user_obj.id, Album.deleted_at == None
    ).count()
    fmt_counts = dict(
        db.query(Album.format_type, func.count(Album.id))
        .filter(Album.user_id == user_obj.id, Album.deleted_at == None, Album.format_type != None)
        .group_by(Album.format_type)
        .all()
    )
    owned    = db.query(Album).filter(Album.user_id == user_obj.id, Album.deleted_at == None, Album.owned == True).count()
    listened = db.query(Album).filter(Album.user_id == user_obj.id, Album.deleted_at == None, Album.listened == True).count()
    wishlist = db.query(Album).filter(Album.user_id == user_obj.id, Album.deleted_at == None, Album.wishlist == True).count()
    concerts_total = db.query(Concert).filter(Concert.user_id == user_obj.id).count()
    bars_total     = db.query(HifiBar).filter(HifiBar.user_id == user_obj.id).count()

    lines = [
        f"Usuario: {user_obj.display_name or user_obj.username}",
        f"Total de discos en su colección: {albums_total}",
        f"En colección (owned): {owned} · Escuchados: {listened} · Wishlist: {wishlist}",
    ]
    if fmt_counts:
        fmt_str = ", ".join(f"{k}: {v}" for k, v in fmt_counts.items())
        lines.append(f"Discos por formato: {fmt_str}")
    lines.append(f"Total de recitales registrados: {concerts_total}")
    lines.append(f"Total de bares hifi registrados: {bars_total}")

    # Bateas (ubicacion fisica) y que discos tiene cada una
    crates = db.query(Crate).filter(Crate.user_id == user_obj.id).order_by(Crate.position).all()
    if crates:
        lines.append("Bateas (ubicación física) y los discos que contiene cada una:")
        for c in crates:
            crate_albums = (
                db.query(Album)
                .filter(Album.crate_id == c.id, Album.deleted_at == None)
                .order_by(Album.artist)
                .all()
            )
            if crate_albums:
                album_list = "; ".join(f"{a.title} - {a.artist}" for a in crate_albums)
            else:
                album_list = "(vacía)"
            lines.append(f'- Batea "{c.name}": {album_list}')
        unassigned = db.query(Album).filter(
            Album.user_id == user_obj.id, Album.crate_id == None, Album.deleted_at == None
        ).count()
        lines.append(f"Discos sin batea asignada: {unassigned}")
    else:
        lines.append("El usuario no tiene bateas creadas todavía.")

    # Detalle disco por disco: fecha de alta y datos de mercado de Discogs (si fueron cacheados)
    all_albums = (
        db.query(Album)
        .filter(Album.user_id == user_obj.id, Album.deleted_at == None)
        .order_by(Album.artist)
        .all()
    )
    if all_albums:
        lines.append("\nListado completo de discos (fecha de alta a la colección y datos de mercado de Discogs si se conocen):")
        for a in all_albums:
            added = a.created_at.strftime("%Y-%m-%d") if a.created_at else "fecha desconocida"
            parts = [f'- "{a.title}" - {a.artist} (agregado: {added})']
            if a.discogs_lowest_price is not None:
                parts.append(f"precio más bajo en Discogs: ${a.discogs_lowest_price}")
            if a.discogs_num_for_sale is not None:
                parts.append(f"copias en venta: {a.discogs_num_for_sale}")
            if a.discogs_have is not None:
                parts.append(f"usuarios que lo tienen: {a.discogs_have}")
            if a.discogs_want is not None:
                parts.append(f"usuarios que lo quieren: {a.discogs_want}")
            if len(parts) == 1:
                parts.append("sin datos de mercado todavía (no sincronizado)")
            lines.append(", ".join(parts))

    return "\n".join(lines)


@router.post("")
async def chat(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "no autorizado"}, status_code=401)

    user_obj = db.query(User).filter(User.username == username).first()
    context  = _build_user_context(db, user_obj) if user_obj else ""
    system_prompt = f"{BASE_SYSTEM_PROMPT}\n\nDatos reales de la colección del usuario:\n{context}"

    body     = await request.json()
    history  = body.get("messages", [])[-MAX_HISTORY:]
    messages = [{"role": "system", "content": system_prompt}] + history

    async def gen():
        try:
            async for chunk in chat_completion_stream(messages):
                yield chunk
        except AIChatError as e:
            yield f"[[error]] {e}"

    return StreamingResponse(gen(), media_type="text/plain")


# ── Chat acotado a un disco puntual ───────────────────────

def _build_album_context(album: Album, extra: dict | None, crate: Crate | None) -> str:
    lines = [
        f"Título: {album.title}",
        f"Artista: {album.artist}",
    ]
    # Aclaracion importante: el "año" guardado es el de ESTA EDICION/PRESSING
    # puntual que tiene el usuario en su colección, no necesariamente el año
    # de lanzamiento original del álbum (puede ser una reedición, RSD, etc.)
    if album.year:        lines.append(f"Año de esta edición/pressing en la colección del usuario: {album.year}")
    if album.genre:       lines.append(f"Género: {album.genre}")
    if album.label:       lines.append(f"Sello: {album.label}")
    if album.format_type: lines.append(f"Formato: {album.format_type}")
    if album.score:       lines.append(f"Puntuación personal del usuario: {album.score}/10")
    if album.review:      lines.append(f"Reseña personal del usuario: {album.review}")
    if crate: lines.append(f"Ubicación física (batea): {crate.name}")
    else:     lines.append("Ubicación física (batea): sin asignar")
    if extra:
        if extra.get("released"):   lines.append(f"Fecha de esta edición/pressing según Discogs: {extra['released']}")
        if extra.get("country"):    lines.append(f"País de esta edición: {extra['country']}")
        if extra.get("notes"):      lines.append(f"Notas del release: {extra['notes']}")
        if extra.get("tracklist"):
            tracks = ", ".join(t["title"] for t in extra["tracklist"] if t.get("title"))
            if tracks:
                lines.append(f"Tracklist: {tracks}")
        if extra.get("rating_avg"):
            rating_line = f"Puntuación promedio en Discogs: {extra['rating_avg']}/5"
            if extra.get("rating_count"):
                rating_line += f" (basada en {extra['rating_count']} votos)"
            lines.append(rating_line)
        if extra.get("community_have"):
            lines.append(f"Personas que tienen este disco (Discogs): {extra['community_have']}")
        if extra.get("community_want"):
            lines.append(f"Personas que quieren este disco (Discogs): {extra['community_want']}")
    return "\n".join(lines)


@router.post("/album/{album_id}")
async def chat_album(album_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return JSONResponse({"error": "no autorizado"}, status_code=401)

    album = db.query(Album).filter(Album.id == album_id, Album.deleted_at == None).first()
    if not album:
        raise HTTPException(status_code=404)

    extra   = await fetch_release_details(album.discogs_id) if album.discogs_id else None
    crate   = db.query(Crate).filter(Crate.id == album.crate_id).first() if album.crate_id else None
    context = _build_album_context(album, extra, crate)

    system_prompt = (
        "Sos un asistente que habla EXCLUSIVAMENTE sobre el siguiente disco. "
        "No respondas nada que no sea sobre este disco puntual: ni sobre programación, "
        "ni sobre la aplicación Melomano, ni sobre otros discos, ni sobre ningún otro tema. "
        "Si te preguntan algo fuera de este disco, respondé amablemente que solo podés "
        "hablar sobre este disco en particular. Respondé corto y en español.\n\n"
        "IMPORTANTE sobre las fechas: los datos de abajo describen la EDICIÓN/PRESSING "
        "específica que el usuario tiene en su colección (puede ser una reedición, version "
        "de Record Store Day, etc.), no necesariamente el álbum original. Si te preguntan "
        "por el año de lanzamiento ORIGINAL del álbum, usá tu conocimiento general sobre el "
        "artista y el álbum para responder correctamente, aclarando la diferencia entre el "
        "lanzamiento original y esta edición puntual si corresponde. No asumas que el año "
        "de la edición es el año de lanzamiento original.\n\n"
        f"Datos del disco:\n{context}"
    )

    body     = await request.json()
    history  = body.get("messages", [])[-MAX_HISTORY:]
    messages = [{"role": "system", "content": system_prompt}] + history

    async def gen():
        try:
            async for chunk in chat_completion_stream(messages):
                yield chunk
        except AIChatError as e:
            yield f"[[error]] {e}"

    return StreamingResponse(gen(), media_type="text/plain")
