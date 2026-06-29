from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services.storage import connect


class NotePayload(BaseModel):
    title: str = Field(default="Untitled note")
    content: str = ""


class Note(NotePayload):
    id: str
    created_at: datetime
    updated_at: datetime


class NoteRequest(NotePayload):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_title(title: str) -> str:
    cleaned = title.strip()
    return cleaned if cleaned else "Untitled note"


def _row_to_note(row) -> Note:
    payload = NotePayload.model_validate_json(row["payload"])
    return Note(
        id=row["id"],
        title=payload.title,
        content=payload.content,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def load_notes(settings: Settings | None = None) -> list[Note]:
    settings = settings or get_settings()
    with connect(settings.data_dir) as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at, payload FROM user_notes ORDER BY updated_at DESC, title"
        ).fetchall()
    return [_row_to_note(row) for row in rows]


def create_note(request: NoteRequest, settings: Settings | None = None) -> Note:
    settings = settings or get_settings()
    now = _now()
    note = Note(
        id=uuid.uuid4().hex,
        title=_clean_title(request.title),
        content=request.content,
        created_at=now,
        updated_at=now,
    )
    payload = NotePayload(title=note.title, content=note.content)
    with connect(settings.data_dir) as conn:
        conn.execute(
            """
            INSERT INTO user_notes (id, title, created_at, updated_at, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (note.id, note.title, note.created_at.isoformat(), note.updated_at.isoformat(), payload.model_dump_json()),
        )
        conn.commit()
    return note


def update_note(note_id: str, request: NoteRequest, settings: Settings | None = None) -> Note | None:
    settings = settings or get_settings()
    now = _now()
    payload = NotePayload(title=_clean_title(request.title), content=request.content)
    with connect(settings.data_dir) as conn:
        existing = conn.execute("SELECT id, created_at FROM user_notes WHERE id = ?", (note_id,)).fetchone()
        if existing is None:
            return None
        conn.execute(
            """
            UPDATE user_notes
            SET title = ?, updated_at = ?, payload = ?
            WHERE id = ?
            """,
            (payload.title, now.isoformat(), payload.model_dump_json(), note_id),
        )
        conn.commit()
        return Note(
            id=note_id,
            title=payload.title,
            content=payload.content,
            created_at=datetime.fromisoformat(existing["created_at"]),
            updated_at=now,
        )


def delete_note(note_id: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    with connect(settings.data_dir) as conn:
        cursor = conn.execute("DELETE FROM user_notes WHERE id = ?", (note_id,))
        conn.commit()
    return cursor.rowcount > 0
