import os
import httpx
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.album import Album
from app.models.sync_log import SyncLog

DISCOGS_TOKEN    = os.getenv("DISCOGS_TOKEN", "")
DISCOGS_USERNAME = os.getenv("DISCOGS_USERNAME", "")
BASE_URL         = "https://api.discogs.com"
USER_AGENT       = "Melomano/1.0"


def _headers() -> dict:
    return {
        "Authorization": f"Discogs token={DISCOGS_TOKEN}",
        "User-Agent": USER_AGENT,
    }


async def fetch_collection_page(page: int = 1, per_page: int = 100) -> dict:
    """Trae una pagina de la coleccion del usuario."""
    url = f"{BASE_URL}/users/{DISCOGS_USERNAME}/collection/folders/0/releases"
    params = {"page": page, "per_page": per_page, "sort": "added", "sort_order": "desc"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = client.get(url, headers=_headers(), params=params)  # sync inside async ok for single call
        resp = await client.get(url, headers=_headers(), params=params)
        resp.raise_for_status()
        return resp.json()


def _parse_release(item: dict) -> dict:
    """Extrae los campos relevantes de un item de la coleccion."""
    info     = item.get("basic_information", {})
    formats  = info.get("formats", [])
    fmt_names = ", ".join(f.get("name", "") for f in formats if f.get("name"))
    fmt_desc  = []
    for f in formats:
        fmt_desc.extend(f.get("descriptions", []))
    fmt_type = formats[0].get("name", "") if formats else ""

    genres  = info.get("genres", [])
    styles  = info.get("styles", [])
    genre   = ", ".join(genres + styles) if genres or styles else None

    labels  = info.get("labels", [])
    label   = labels[0].get("name", "") if labels else None

    artists = info.get("artists", [])
    artist  = " / ".join(a.get("name", "").strip() for a in artists) if artists else "Desconocido"

    # Portada — thumb es pequeña, intentamos la imagen completa
    cover_url = info.get("cover_image") or info.get("thumb") or None

    return {
        "discogs_id":  info.get("id"),
        "title":       info.get("title", "Sin titulo"),
        "artist":      artist,
        "year":        info.get("year") or None,
        "genre":       genre,
        "label":       label,
        "cover_url":   cover_url,
        "formats":     fmt_names,
        "format_type": fmt_type,
        "discogs_url": f"https://www.discogs.com/release/{info.get('id')}",
    }


async def sync_collection(db: Session) -> SyncLog:
    """Sincroniza toda la coleccion de Discogs. Crea o actualiza albums."""
    log = SyncLog(status="running", source="discogs")
    db.add(log)
    db.commit()
    db.refresh(log)

    added = updated = total = 0

    try:
        page = 1
        while True:
            data      = await fetch_collection_page(page=page, per_page=100)
            releases  = data.get("releases", [])
            pages     = data.get("pagination", {}).get("pages", 1)

            for item in releases:
                total += 1
                parsed = _parse_release(item)
                disc_id = parsed["discogs_id"]
                if not disc_id:
                    continue

                existing = db.query(Album).filter(Album.discogs_id == disc_id).first()
                if existing:
                    # Actualiza metadatos pero preserva score/review del usuario
                    existing.title       = parsed["title"]
                    existing.artist      = parsed["artist"]
                    existing.year        = parsed["year"]
                    existing.genre       = parsed["genre"]
                    existing.label       = parsed["label"]
                    existing.cover_url   = parsed["cover_url"] or existing.cover_url
                    existing.formats     = parsed["formats"]
                    existing.format_type = parsed["format_type"]
                    existing.owned       = True
                    existing.synced_at   = datetime.utcnow()
                    updated += 1
                else:
                    album = Album(
                        **parsed,
                        owned=True,
                        listened=False,
                        wishlist=False,
                        synced_at=datetime.utcnow(),
                    )
                    db.add(album)
                    added += 1

            db.commit()

            if page >= pages:
                break
            page += 1

        log.status      = "success"
        log.added       = added
        log.updated     = updated
        log.total       = total
        log.finished_at = datetime.utcnow()
        log.message     = f"Sincronizacion completada: {added} nuevos, {updated} actualizados de {total} total."

    except Exception as e:
        db.rollback()
        log.status      = "error"
        log.message     = str(e)
        log.finished_at = datetime.utcnow()

    db.add(log)
    db.commit()
    db.refresh(log)
    return log


async def search_discogs(query: str, search_type: str = "release") -> list[dict]:
    """Busca en el catalogo de Discogs."""
    url    = f"{BASE_URL}/database/search"
    params = {"q": query, "type": search_type, "per_page": 10}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=_headers(), params=params)
        resp.raise_for_status()
        results = resp.json().get("results", [])

    out = []
    for r in results:
        out.append({
            "discogs_id": r.get("id"),
            "title":      r.get("title", ""),
            "year":       r.get("year"),
            "genre":      ", ".join(r.get("genre", []) + r.get("style", [])),
            "label":      r.get("label", [None])[0] if r.get("label") else None,
            "cover_url":  r.get("cover_image") or r.get("thumb"),
            "format_type": r.get("format", [None])[0] if r.get("format") else None,
            "discogs_url": f"https://www.discogs.com/release/{r.get('id')}",
        })
    return out
