import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.database import engine, Base, SessionLocal
from app.routers import auth, albums, concerts
from app.routers import perfil, users, bares, formatos, crates, chat, admin_ai, wishlist, public, setlist
from app.models import concert_photo  # noqa: F401
from app.models import featured       # noqa: F401
from app.models import user as user_model  # noqa: F401
from app.models import hifi_bar, bar_visit, bar_photo  # noqa: F401
from app.models import format_type    # noqa: F401
from app.models import favorite_track  # noqa: F401
from app.models import crate as crate_model  # noqa: F401
from app.models import wishlist_category, wishlist_item  # noqa: F401
from app.models import saved_setlist  # noqa: F401
from app.models.user import User
from app.models.featured import FeaturedItem
from app.auth import hash_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        admin_username = os.getenv("APP_USERNAME", "admin")
        admin_password = os.getenv("APP_PASSWORD", "admin")

        admin = db.query(User).filter(User.username == admin_username).first()
        if not admin:
            admin = User(
                username=admin_username,
                display_name=admin_username.capitalize(),
                password_hash=hash_password(admin_password),
                is_admin=True,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)

        # Asignar featured items huerfanos al admin
        db.query(FeaturedItem).filter(FeaturedItem.user_id == None).update(
            {"user_id": admin.id}, synchronize_session=False
        )
        db.commit()
    finally:
        db.close()

    yield


app = FastAPI(title="Melomano", version="1.0.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(albums.router)
app.include_router(concerts.router)
app.include_router(perfil.router)
app.include_router(users.router)
app.include_router(bares.router)
app.include_router(formatos.router)
app.include_router(crates.router)
app.include_router(chat.router)
app.include_router(admin_ai.router)
app.include_router(wishlist.router)
app.include_router(public.router)
app.include_router(setlist.router)
