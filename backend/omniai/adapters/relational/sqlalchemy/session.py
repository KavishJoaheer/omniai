from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from omniai.adapters.relational.sqlalchemy.models import Base


class DatabaseManager:
    def __init__(self, url: str, *, echo: bool = False) -> None:
        connect_args: dict[str, object] = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        self.engine = create_engine(
            url,
            echo=echo,
            future=True,
            pool_pre_ping=not url.startswith("sqlite"),
            connect_args=connect_args,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def new_session(self) -> Session:
        return self.session_factory()

