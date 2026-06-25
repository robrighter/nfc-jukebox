"""Fetch album metadata (cover art, artist, title, track list) from iTunes.

Uses the public iTunes Search API — no key required. Best-effort: returns None
if nothing matches or the network call fails.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://itunes.apple.com/search"
_LOOKUP_URL = "https://itunes.apple.com/lookup"
_TIMEOUT = 8


async def fetch_album_metadata(album_text: str) -> Optional[dict[str, Any]]:
    """Return {artist, title, cover_url, tracks:[...]} for album_text, or None."""
    album_text = (album_text or "").strip()
    if not album_text:
        return None

    import aiohttp

    timeout = aiohttp.ClientTimeout(total=_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 1) Find the album.
            async with session.get(
                _SEARCH_URL,
                params={"term": album_text, "entity": "album", "limit": "1"},
            ) as resp:
                # iTunes returns content-type text/javascript.
                data = await resp.json(content_type=None)
            results = data.get("results") or []
            if not results:
                logger.info("No iTunes match for album '%s'", album_text)
                return None
            album = results[0]
            collection_id = album.get("collectionId")
            cover = (album.get("artworkUrl100") or "").replace(
                "100x100bb", "600x600bb"
            )
            meta: dict[str, Any] = {
                "artist": album.get("artistName"),
                "title": album.get("collectionName"),
                "cover_url": cover or None,
                "tracks": [],
            }

            # 2) Look up the track list.
            if collection_id:
                async with session.get(
                    _LOOKUP_URL,
                    params={"id": str(collection_id), "entity": "song"},
                ) as resp:
                    lookup = await resp.json(content_type=None)
                tracks = [
                    item.get("trackName")
                    for item in lookup.get("results", [])
                    if item.get("wrapperType") == "track" and item.get("trackName")
                ]
                meta["tracks"] = tracks

            logger.info(
                "Fetched metadata for '%s' -> %s by %s (%d tracks)",
                album_text,
                meta["title"],
                meta["artist"],
                len(meta["tracks"]),
            )
            return meta
    except Exception as exc:
        logger.warning("Metadata lookup failed for '%s': %s", album_text, exc)
        return None
