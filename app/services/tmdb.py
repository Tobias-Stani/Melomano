import os
import httpx

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
BASE_URL     = "https://api.themoviedb.org/3"
IMG_URL      = "https://image.tmdb.org/t/p/"
LANGUAGE     = "es-MX"


def enabled() -> bool:
    return bool(TMDB_API_KEY)


async def _get(path: str, **params) -> dict:
    # Acepta tanto la "API Key" corta (v3) como el "Read Access Token" largo (v4)
    headers = {}
    if len(TMDB_API_KEY) > 40:
        headers["Authorization"] = f"Bearer {TMDB_API_KEY}"
    else:
        params["api_key"] = TMDB_API_KEY
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{BASE_URL}{path}", params={"language": LANGUAGE, **params}, headers=headers)
        resp.raise_for_status()
        return resp.json()


def _img(path: str | None, size: str) -> str | None:
    return f"{IMG_URL}{size}{path}" if path else None


async def search_movies(q: str) -> list[dict]:
    data = await _get("/search/movie", query=q)
    return [
        {
            "tmdb_id":    r["id"],
            "title":      r.get("title") or r.get("original_title"),
            "year":       (r.get("release_date") or "")[:4] or None,
            "poster_url": _img(r.get("poster_path"), "w185"),
        }
        for r in data.get("results", [])[:10]
    ]


async def fetch_posters(tmdb_id: int) -> list[dict]:
    data = await _get(f"/movie/{tmdb_id}/images", include_image_language="es,en,null")
    posters = sorted(data.get("posters", []), key=lambda p: p.get("vote_average", 0), reverse=True)
    return [
        {
            "thumb":    _img(p["file_path"], "w185"),
            "url":      _img(p["file_path"], "w500"),
            "language": p.get("iso_639_1"),
        }
        for p in posters[:40]
    ]


async def fetch_movie(tmdb_id: int) -> dict:
    d = await _get(f"/movie/{tmdb_id}", append_to_response="credits")
    directors = [c["name"] for c in d.get("credits", {}).get("crew", []) if c.get("job") == "Director"]
    year = (d.get("release_date") or "")[:4]
    return {
        "tmdb_id":        d["id"],
        "title":          d.get("title") or d.get("original_title"),
        "original_title": d.get("original_title"),
        "year":           int(year) if year else None,
        "director":       ", ".join(directors) or None,
        "genres":         ", ".join(g["name"] for g in d.get("genres", [])) or None,
        "runtime":        d.get("runtime") or None,
        "overview":       d.get("overview") or None,
        "poster_url":     _img(d.get("poster_path"), "w500"),
        "backdrop_url":   _img(d.get("backdrop_path"), "w1280"),
    }
