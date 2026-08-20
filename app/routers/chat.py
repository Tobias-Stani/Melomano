import asyncio
import os
import uuid

import httpx
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
from app.models.wishlist_item import WishlistItem
from app.auth import get_current_user
from app.services.ai_chat import chat_completion_stream, AIChatError
from app.services.discogs import fetch_release_details

router = APIRouter(prefix="/api/chat")

# Ito (Iteguito AI) — segundo asistente en prueba, alternable desde el chat.
# Server-side only: ITO_API_KEY nunca debe llegar al navegador.
ITO_GATEWAY_URL = os.getenv("ITO_GATEWAY_URL", "")
ITO_API_KEY = os.getenv("ITO_API_KEY", "")

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


@router.post("/ito")
async def chat_ito(request: Request):
    """Proxies one question to the Ito (Iteguito AI) gateway, server-side —
    keeps ITO_API_KEY out of the browser. Test-only, alongside the existing
    Groq-based assistant above; does not replace it."""
    if not get_current_user(request):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    if not ITO_API_KEY or not ITO_GATEWAY_URL:
        return JSONResponse({"error": "Ito no está configurado (falta ITO_API_KEY/ITO_GATEWAY_URL)"}, status_code=503)

    body = await request.json()
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "question requerida")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{ITO_GATEWAY_URL}/query",
                headers={"X-API-Key": ITO_API_KEY},
                json={"question": question, "request_id": str(uuid.uuid4())},
            )
    except httpx.HTTPError:
        return JSONResponse({"error": "No se pudo conectar con Ito."}, status_code=502)

    if resp.status_code >= 400:
        return JSONResponse({"error": "Ito no pudo responder esa pregunta."}, status_code=502)

    data = resp.json()
    return {"answer": data["answer"], "source": data.get("source")}


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


@router.post("/setlist")
async def chat_setlist(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "no autorizado"}, status_code=401)

    body             = await request.json()
    album_ids        = body.get("album_ids", [])
    duration_minutes = int(body.get("duration_minutes", 120))
    num_tracks       = int(body.get("num_tracks", 20))
    user_context     = (body.get("user_context") or "").strip()
    if not album_ids:
        return JSONResponse({"error": "seleccioná al menos un disco"}, status_code=400)

    user_obj = db.query(User).filter(User.username == username).first()
    albums   = (
        db.query(Album)
        .filter(Album.id.in_(album_ids), Album.user_id == user_obj.id, Album.deleted_at == None)
        .all()
    )
    if not albums:
        return JSONResponse({"error": "no se encontraron los discos"}, status_code=404)

    extras = await asyncio.gather(*[
        fetch_release_details(a.discogs_id) if a.discogs_id else asyncio.sleep(0, result=None)
        for a in albums
    ])

    context_lines = []
    for album, extra in zip(albums, extras):
        context_lines.append(f"\n== {album.title} — {album.artist} ==")
        if album.genre: context_lines.append(f"  Género: {album.genre}")
        if album.year:  context_lines.append(f"  Año: {album.year}")
        if extra and extra.get("tracklist"):
            tracks = []
            for t in extra["tracklist"]:
                if not t.get("title"): continue
                entry = f"{t.get('pos','').strip()} {t['title']}"
                if t.get("duration"): entry += f" ({t['duration']})"
                tracks.append(entry.strip())
            if tracks:
                context_lines.append("  Tracklist:")
                for tr in tracks:
                    context_lines.append(f"    - {tr}")
        else:
            context_lines.append("  (sin tracklist en Discogs)")

    context = "\n".join(context_lines)
    duration_h   = duration_minutes // 60
    duration_min = duration_minutes % 60
    duration_str = f"{duration_h}h{f' {duration_min}min' if duration_min else ''}"

    context_line = f"\nAmbiente/contexto del set: {user_context}" if user_context else ""

    system_prompt = (
        f"Sos un DJ con años de experiencia curando sets. Tu trabajo es elegir y ordenar canciones para que el set FLUYA, "
        f"no solo listar tracks al azar.{context_line}\n\n"
        f"Armá un setlist de exactamente {num_tracks} temas para una sesión de {duration_str}.\n\n"
        "REGLAS DE CURACIÓN (son obligatorias, no opcionales):\n"
        "- Elegí SOLO los temas que funcionan juntos en términos de tempo, energía y mood. Si un tema rompe el flujo, no lo pongas.\n"
        "- No uses todos los temas disponibles. Seleccioná los mejores para ese arco de energía específico.\n"
        "- El arco debe ser claro: calentamiento suave → build progresivo → pico → descenso → cierre memorable.\n"
        "- Las transiciones deben ser técnicas y realistas: blend en el drop, loop del intro, cut en 4 tiempos, fade con filtro, silencio dramático, etc.\n"
        "- Pensá en compatibilidad tonal y rítmica entre temas consecutivos.\n"
        "- Si el usuario especificó un ambiente, priorizá tracks que encajen con ese mood aunque no sean los más 'obvios'.\n\n"
        "Respondé en español. NO uses markdown (sin asteriscos, sin #, sin **). Solo texto plano con mayúsculas para secciones.\n\n"
        "Formato exacto:\n"
        "VIBE DEL SET\n"
        "[2 líneas: qué sensación genera este set y para qué momento/público]\n\n"
        "SETLIST\n"
        "1. Titulo del tema — Artista (Album)\n"
        "   → [transición técnica al siguiente: qué hacés, cuántos beats, qué elemento usás]\n"
        "2. ...\n"
        "(el último tema no lleva transición)\n\n"
        "NOTA DEL DJ\n"
        "[2-3 líneas explicando la lógica de curación: por qué ese orden, qué momentos clave hay en el set]\n\n"
        f"Discos y tracklists disponibles (elegí solo lo que sirve):\n{context}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": "Armá el setlist con estos discos."},
    ]

    async def gen():
        try:
            async for chunk in chat_completion_stream(messages):
                yield chunk
        except AIChatError as e:
            yield f"[[error]] {e}"

    return StreamingResponse(gen(), media_type="text/plain")


@router.post("/wishlist/{item_id}")
async def chat_wishlist(item_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return JSONResponse({"error": "no autorizado"}, status_code=401)

    item = db.query(WishlistItem).filter(WishlistItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404)

    extra = await fetch_release_details(item.discogs_id) if item.discogs_id else None

    lines = [f"Título: {item.title}", f"Artista: {item.artist}"]
    if item.year:        lines.append(f"Año: {item.year}")
    if item.genre:       lines.append(f"Género: {item.genre}")
    if item.label:       lines.append(f"Sello: {item.label}")
    if item.format_type: lines.append(f"Formato: {item.format_type}")
    if item.notes:       lines.append(f"Notas del usuario: {item.notes}")
    lines.append("Estado: en la wishlist del usuario (todavía no lo tiene)")
    if extra:
        if extra.get("released"):  lines.append(f"Fecha de edición (Discogs): {extra['released']}")
        if extra.get("country"):   lines.append(f"País: {extra['country']}")
        if extra.get("notes"):     lines.append(f"Notas del release: {extra['notes']}")
        if extra.get("tracklist"):
            tracks = ", ".join(t["title"] for t in extra["tracklist"] if t.get("title"))
            if tracks: lines.append(f"Tracklist: {tracks}")
        if extra.get("rating_avg"):
            lines.append(f"Puntuación Discogs: {extra['rating_avg']}/5 ({extra.get('rating_count', '?')} votos)")
        if extra.get("community_have"):
            lines.append(f"Personas que lo tienen (Discogs): {extra['community_have']}")
        if extra.get("community_want"):
            lines.append(f"Personas que lo quieren (Discogs): {extra['community_want']}")
        if extra.get("lowest_price") is not None:
            lines.append(f"Precio más bajo en marketplace Discogs: ${extra['lowest_price']}")

    context = "\n".join(lines)
    system_prompt = (
        "Sos un asistente que habla EXCLUSIVAMENTE sobre el siguiente disco de la wishlist del usuario. "
        "No respondas sobre otros temas. Podés hablar de la música, el artista, el álbum, "
        "el tracklist, la historia del disco, y datos de Discogs que te paso. "
        "Respondé corto y en español.\n\n"
        f"Datos del disco:\n{context}"
    )

    body    = await request.json()
    history = body.get("messages", [])[-MAX_HISTORY:]
    messages = [{"role": "system", "content": system_prompt}] + history

    async def gen():
        try:
            async for chunk in chat_completion_stream(messages):
                yield chunk
        except AIChatError as e:
            yield f"[[error]] {e}"

    return StreamingResponse(gen(), media_type="text/plain")
