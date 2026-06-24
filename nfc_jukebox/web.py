"""FastAPI route handlers."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import db
from .app import templates
from .models import WriteJobStatus
from . import settings_store

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------- HTML pages ----------

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    nfc = request.app.state.nfc
    alexa = request.app.state.alexa
    scans = await db.get_recent_scans(10)
    template = await settings_store.get_command_template()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "nfc_status": nfc.get_status(),
            "alexa_connected": alexa.connected,
            "alexa_device_name": alexa._device_name,
            "command_template": template,
            "recent_scans": scans,
        },
    )


@router.get("/albums", response_class=HTMLResponse)
async def albums_list(request: Request):
    albums = await db.get_albums()
    return templates.TemplateResponse(
        request,
        "albums.html", {"request": request, "albums": albums}
    )


@router.get("/albums/new", response_class=HTMLResponse)
async def album_new(request: Request):
    return templates.TemplateResponse(
        request,
        "album_form.html",
        {"request": request, "album": None, "action": "/albums", "title": "Add Album"},
    )


@router.post("/albums")
async def album_create(
    request: Request,
    album_text: str = Form(...),
    notes: Optional[str] = Form(None),
):
    album_text = album_text.strip()
    if not album_text:
        return templates.TemplateResponse(
            request,
            "album_form.html",
            {
                "request": request,
                "album": {"album_text": album_text, "notes": notes},
                "action": "/albums",
                "title": "Add Album",
                "error": "Album text is required.",
            },
            status_code=422,
        )
    try:
        await db.create_album(album_text, notes)
    except Exception as exc:
        logger.error("Failed to create album: %s", exc)
        error = "That album already exists." if "UNIQUE" in str(exc) else f"Could not save album: {exc}"
        return templates.TemplateResponse(
            request,
            "album_form.html",
            {
                "request": request,
                "album": {"album_text": album_text, "notes": notes},
                "action": "/albums",
                "title": "Add Album",
                "error": error,
            },
            status_code=422,
        )
    return RedirectResponse("/albums?added=1", status_code=303)


@router.get("/albums/{album_id}/edit", response_class=HTMLResponse)
async def album_edit(request: Request, album_id: int):
    album = await db.get_album_by_id(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found")
    return templates.TemplateResponse(
        request,
        "album_form.html",
        {
            "request": request,
            "album": album,
            "action": f"/albums/{album_id}",
            "title": "Edit Album",
        },
    )


@router.post("/albums/{album_id}")
async def album_update(
    request: Request,
    album_id: int,
    album_text: str = Form(...),
    notes: Optional[str] = Form(None),
):
    result = await db.update_album(album_id, album_text.strip(), notes)
    if result is None:
        raise HTTPException(status_code=404, detail="Album not found")
    return RedirectResponse("/albums?updated=1", status_code=303)


@router.post("/albums/{album_id}/delete")
async def album_delete(request: Request, album_id: int):
    await db.delete_album(album_id)
    return RedirectResponse("/albums?deleted=1", status_code=303)


@router.get("/albums/{album_id}/write", response_class=HTMLResponse)
async def album_write_page(request: Request, album_id: int):
    album = await db.get_album_by_id(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found")
    return templates.TemplateResponse(
        request,
        "write_tag.html", {"request": request, "album": album}
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    stored = await settings_store.get_all()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request,
            "settings": stored,
            "alexa_device_name": request.app.state.alexa._device_name,
        },
    )


@router.post("/settings")
async def settings_save(
    request: Request,
    alexa_command_template: str = Form(...),
):
    message = None
    try:
        await settings_store.set_command_template(alexa_command_template.strip())
        message = "Settings saved."
    except ValueError as exc:
        message = f"Error: {exc}"
    stored = await settings_store.get_all()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request,
            "settings": stored,
            "alexa_device_name": request.app.state.alexa._device_name,
            "message": message,
        },
    )


@router.post("/settings/test-command")
async def settings_test_command(request: Request):
    alexa = request.app.state.alexa
    template = await settings_store.get_command_template()
    command = template.format(album="Test Album")
    try:
        await alexa.send_text_command(command)
        return JSONResponse({"ok": True, "command": command})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.get("/status", response_class=HTMLResponse)
async def status_page(request: Request):
    nfc = request.app.state.nfc
    alexa = request.app.state.alexa
    template = await settings_store.get_command_template()
    return templates.TemplateResponse(
        request,
        "status.html",
        {
            "request": request,
            "nfc_status": nfc.get_status(),
            "alexa_connected": alexa.connected,
            "alexa_device_name": alexa._device_name,
            "command_template": template,
        },
    )


# ---------- JSON API ----------

@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    setup = request.app.state.setup_service
    alexa = request.app.state.alexa
    return templates.TemplateResponse(
        request,
        "setup.html",
        {
            "request": request,
            "is_complete": setup.is_complete(),
            "alexa_connected": alexa.connected,
            "login_url": setup.pending.login_url if setup.pending else None,
        },
    )


@router.post("/api/setup/start")
async def api_setup_start(request: Request):
    setup = request.app.state.setup_service
    try:
        login_url = await setup.begin_login()
        return JSONResponse({"ok": True, "login_url": login_url})
    except Exception as exc:
        logger.error("Setup start failed: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.post("/api/setup/complete")
async def api_setup_complete(request: Request):
    setup = request.app.state.setup_service
    alexa = request.app.state.alexa
    body = await request.json()
    redirect_url = (body.get("redirect_url") or "").strip()
    if not redirect_url:
        raise HTTPException(status_code=422, detail="redirect_url is required")
    try:
        await setup.complete_login(redirect_url)
    except Exception as exc:
        logger.error("Setup complete failed: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    # Reconnect the Alexa client with the freshly saved tokens.
    try:
        await alexa.reconnect()
    except Exception as exc:
        logger.error("Reconnect after setup failed: %s", exc)

    return JSONResponse({"ok": True, "connected": alexa.connected})


@router.get("/api/setup/status")
async def api_setup_status(request: Request):
    setup = request.app.state.setup_service
    alexa = request.app.state.alexa
    return {
        "is_complete": setup.is_complete(),
        "connected": alexa.connected,
        "in_progress": setup.pending is not None,
    }


@router.post("/api/alexa/command")
async def api_alexa_command(request: Request):
    body = await request.json()
    command = (body.get("command") or "").strip()
    if not command:
        raise HTTPException(status_code=422, detail="command is required")
    alexa = request.app.state.alexa
    try:
        await alexa.send_text_command(command)
        return JSONResponse({"ok": True, "command": command})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.get("/api/status")
async def api_status(request: Request):
    nfc = request.app.state.nfc
    alexa = request.app.state.alexa
    template = await settings_store.get_command_template()
    return {
        "nfc": nfc.get_status(),
        "alexa_connected": alexa.connected,
        "alexa_device_name": alexa._device_name,
        "command_template": template,
    }


@router.get("/api/albums")
async def api_albums():
    return await db.get_albums()


@router.get("/api/settings")
async def api_settings():
    return await settings_store.get_all()


@router.post("/api/write-jobs")
async def api_write_job_create(request: Request):
    body = await request.json()
    album_id = body.get("album_id")
    if album_id is None:
        raise HTTPException(status_code=422, detail="album_id required")

    write_job = request.app.state.write_job
    if write_job.get("active"):
        raise HTTPException(status_code=409, detail="A write job is already in progress")

    album = await db.get_album_by_id(int(album_id))
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found")

    nfc = request.app.state.nfc
    write_job.update(
        {
            "active": True,
            "album_id": album_id,
            "album_text": album["album_text"],
            "status": "waiting",
            "error_message": None,
        }
    )

    async def _run_write():
        try:
            write_job["status"] = "writing"
            await nfc.write_tag_text(album["album_text"])
            write_job["status"] = "done"
            await db.mark_album_written(int(album_id))
        except asyncio.CancelledError:
            write_job["status"] = "cancelled"
        except TimeoutError as exc:
            write_job["status"] = "error"
            write_job["error_message"] = str(exc)
        except Exception as exc:
            write_job["status"] = "error"
            write_job["error_message"] = str(exc)
            logger.error("Write job error: %s", exc)
        finally:
            write_job["active"] = write_job["status"] not in ("done", "cancelled", "error")

    asyncio.create_task(_run_write())

    return WriteJobStatus(
        active=True,
        album_id=album_id,
        album_text=album["album_text"],
        status="waiting",
    )


@router.get("/api/write-jobs/current")
async def api_write_job_current(request: Request):
    write_job = request.app.state.write_job
    return WriteJobStatus(
        active=write_job.get("active", False),
        album_id=write_job.get("album_id"),
        album_text=write_job.get("album_text"),
        status=write_job.get("status", "idle"),
        error_message=write_job.get("error_message"),
    )


@router.post("/api/write-jobs/current/cancel")
async def api_write_job_cancel(request: Request):
    write_job = request.app.state.write_job
    nfc = request.app.state.nfc
    if not write_job.get("active"):
        raise HTTPException(status_code=404, detail="No active write job")
    nfc.cancel_write()
    write_job["status"] = "cancelled"
    write_job["active"] = False
    return {"ok": True}
