from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.database import engine, Base
from app.routers import auth, albums, concerts
from app.routers import perfil
from app.models import concert_photo  # noqa: F401 — registers table with Base
from app.models import featured        # noqa: F401 — registers table with Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Melomano", version="1.0.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(albums.router)
app.include_router(concerts.router)
app.include_router(perfil.router)
