"""Pydantic models for NFC Jukebox."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class Album(BaseModel):
    id: Optional[int] = None
    album_text: str
    notes: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    last_written_at: Optional[str] = None
    last_scanned_at: Optional[str] = None


class AlbumCreate(BaseModel):
    album_text: str
    notes: Optional[str] = None


class AlbumUpdate(BaseModel):
    album_text: str
    notes: Optional[str] = None


class ScanHistory(BaseModel):
    id: Optional[int] = None
    album_text: str
    alexa_command: str
    status: str  # "success" | "error"
    error_message: Optional[str] = None
    created_at: str = ""


class WriteJobStatus(BaseModel):
    active: bool
    album_id: Optional[int] = None
    album_text: Optional[str] = None
    status: str = "idle"  # "idle" | "waiting" | "writing" | "done" | "error" | "cancelled"
    error_message: Optional[str] = None


class SettingsUpdate(BaseModel):
    alexa_command_template: str
