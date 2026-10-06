from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    kwargs = {}
    if url.startswith("sqlite"):
        # Background jobs use their own sessions on worker threads.
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)
