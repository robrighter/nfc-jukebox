"""SQLite database layer using stdlib sqlite3 with asyncio.to_thread."""
import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)

_db_path: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db_sync() -> None:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS albums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                album_text TEXT NOT NULL UNIQUE,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_written_at TEXT,
                last_scanned_at TEXT
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scan_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                album_text TEXT NOT NULL,
                alexa_command TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL
            );
        """)
        # Migration: add album-metadata columns if missing.
        existing = {row[1] for row in cur.execute("PRAGMA table_info(albums)")}
        for col in ("artist", "meta_artist", "meta_title", "cover_url", "tracks"):
            if col not in existing:
                cur.execute(f"ALTER TABLE albums ADD COLUMN {col} TEXT")

        # Seed default settings if not present
        cur.execute(
            "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            ("alexa_command_template", settings.ALEXA_COMMAND_TEMPLATE, _now()),
        )
        conn.commit()
    finally:
        conn.close()


async def init_db(db_path: str) -> None:
    global _db_path
    _db_path = db_path
    await asyncio.to_thread(_init_db_sync)
    logger.info("Database initialised at %s", db_path)


# ---------- albums ----------

def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _get_albums_sync() -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM albums ORDER BY album_text COLLATE NOCASE"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


async def get_albums() -> list[dict]:
    return await asyncio.to_thread(_get_albums_sync)


def _get_album_by_id_sync(album_id: int) -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM albums WHERE id=?", (album_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


async def get_album_by_id(album_id: int) -> Optional[dict]:
    return await asyncio.to_thread(_get_album_by_id_sync, album_id)


def _get_album_by_text_sync(album_text: str) -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM albums WHERE album_text=?", (album_text,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


async def get_album_by_text(album_text: str) -> Optional[dict]:
    return await asyncio.to_thread(_get_album_by_text_sync, album_text)


def _create_album_sync(album_text: str, artist: Optional[str], notes: Optional[str]) -> dict:
    now = _now()
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO albums (album_text, artist, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (album_text, artist, notes, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM albums WHERE id=?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


async def create_album(
    album_text: str, artist: Optional[str] = None, notes: Optional[str] = None
) -> dict:
    return await asyncio.to_thread(_create_album_sync, album_text, artist, notes)


def _update_album_sync(
    album_id: int, album_text: str, artist: Optional[str], notes: Optional[str]
) -> Optional[dict]:
    now = _now()
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE albums SET album_text=?, artist=?, notes=?, updated_at=? WHERE id=?",
            (album_text, artist, notes, now, album_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM albums WHERE id=?", (album_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


async def update_album(
    album_id: int, album_text: str, artist: Optional[str] = None, notes: Optional[str] = None
) -> Optional[dict]:
    return await asyncio.to_thread(_update_album_sync, album_id, album_text, artist, notes)


def _delete_album_sync(album_id: int) -> bool:
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM albums WHERE id=?", (album_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


async def delete_album(album_id: int) -> bool:
    return await asyncio.to_thread(_delete_album_sync, album_id)


def _mark_album_written_sync(album_id: int) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE albums SET last_written_at=?, updated_at=? WHERE id=?",
            (_now(), _now(), album_id),
        )
        conn.commit()
    finally:
        conn.close()


async def mark_album_written(album_id: int) -> None:
    await asyncio.to_thread(_mark_album_written_sync, album_id)


def _set_album_metadata_sync(album_id: int, meta: dict) -> None:
    import json as _json

    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE albums SET meta_artist=?, meta_title=?, cover_url=?, tracks=?, updated_at=? WHERE id=?",
            (
                meta.get("artist"),
                meta.get("title"),
                meta.get("cover_url"),
                _json.dumps(meta.get("tracks") or []),
                _now(),
                album_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def set_album_metadata(album_id: int, meta: dict) -> None:
    await asyncio.to_thread(_set_album_metadata_sync, album_id, meta)


def _mark_album_scanned_sync(album_text: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE albums SET last_scanned_at=?, updated_at=? WHERE album_text=?",
            (_now(), _now(), album_text),
        )
        conn.commit()
    finally:
        conn.close()


async def mark_album_scanned(album_text: str) -> None:
    await asyncio.to_thread(_mark_album_scanned_sync, album_text)


# ---------- scan_history ----------

def _add_scan_history_sync(
    album_text: str,
    alexa_command: str,
    status: str,
    error_message: Optional[str],
) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO scan_history (album_text, alexa_command, status, error_message, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (album_text, alexa_command, status, error_message, _now()),
        )
        conn.commit()
    finally:
        conn.close()


async def add_scan_history(
    album_text: str,
    alexa_command: str,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    await asyncio.to_thread(_add_scan_history_sync, album_text, alexa_command, status, error_message)


def _get_recent_scans_sync(limit: int = 10) -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT s.*, a.cover_url AS cover_url "
            "FROM scan_history s "
            "LEFT JOIN albums a ON a.album_text = s.album_text "
            "ORDER BY s.created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


async def get_recent_scans(limit: int = 10) -> list[dict]:
    return await asyncio.to_thread(_get_recent_scans_sync, limit)


# ---------- settings ----------

def _get_setting_sync(key: str) -> Optional[str]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


async def get_setting(key: str) -> Optional[str]:
    return await asyncio.to_thread(_get_setting_sync, key)


def _set_setting_sync(key: str, value: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, _now()),
        )
        conn.commit()
    finally:
        conn.close()


async def set_setting(key: str, value: str) -> None:
    await asyncio.to_thread(_set_setting_sync, key, value)


def _get_all_settings_sync() -> dict[str, str]:
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


async def get_all_settings() -> dict[str, str]:
    return await asyncio.to_thread(_get_all_settings_sync)
