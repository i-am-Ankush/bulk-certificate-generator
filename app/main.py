from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app.api import router
from app.config import Settings
from app.database import Base, make_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)

    app = FastAPI(
        title="Bulk Certificate Generator",
        version="1.0.0",
        description="Submit a list of recipients, track progress, download PDF certificates.",
    )
    app.state.settings = settings
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.include_router(router)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    return app
