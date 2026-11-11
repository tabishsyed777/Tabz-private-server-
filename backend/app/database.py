"""Durable local storage. SQLite is for development; PostgreSQL is for deployment."""
from __future__ import annotations

import os
from collections.abc import Generator
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./localmind.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class Base(DeclarativeBase):
    pass

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try: yield db
    finally: db.close()

def initialize_database() -> None:
    """Create current tables and add the small set of columns needed by older local DBs."""
    from .models import ChatMessage

    Base.metadata.create_all(bind=engine)
    columns = {column["name"] for column in inspect(engine).get_columns("chat_messages")}
    additions = {
        "sequence": "INTEGER NOT NULL DEFAULT 0",
        "status": "VARCHAR(20) NOT NULL DEFAULT 'complete'",
        "error_message": "TEXT",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in columns:
                connection.exec_driver_sql(f"ALTER TABLE chat_messages ADD COLUMN {name} {definition}")

    # Earlier milestone records had no ordering column. Give each old conversation a
    # deterministic order so same-second messages cannot swap roles in later prompts.
    with SessionLocal() as db:
        items = db.scalars(select(ChatMessage).order_by(ChatMessage.conversation_id, ChatMessage.created_at, ChatMessage.id)).all()
        groups: dict[str, list[ChatMessage]] = {}
        for item in items:
            groups.setdefault(item.conversation_id, []).append(item)
        for group in groups.values():
            if any(item.sequence == 0 for item in group):
                for index, item in enumerate(group, start=1):
                    item.sequence = index
        for item in items:
            if item.status == "streaming":
                item.status = "interrupted"
                item.error_message = "The server restarted during this reply. The saved text is the available partial answer."
        db.commit()
