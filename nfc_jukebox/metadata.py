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


async def _search_albums(session, term: str, limit: int = 25) -> list:
    async with session.get(
        _SEARCH_URL,
        params={"term": term, "entity": "album", "limit": str(limit)},
    ) as resp:
        # iTunes returns content-type text/javascript.
        data = await resp.json(content_type=None)
    return data.get("results") or []


def _pick(results: list, artist: str) -> Optional[dict]:
    """Choose the best album result, preferring an artist-name match."""
    if not results:
        return None
    if artist:
        al = artist.lower()
        for r in results:
            if al in (r.get("artistName") or "").lower():
                return r
    return None


async def fetch_album_metadata(
    album_text: str, artist: str = ""
) -> Optional[dict[str, Any]]:
    """Return {artist, title, cover_url, tracks:[...]} for an album, or None.

    When ``artist`` is given it is used to disambiguate: iTunes keyword search
    treats the term fuzzily, so we fetch several results and pick the one whose
    artist matches, rather than trusting the top hit.
    """
    album_text = (album_text or "").strip()
    artist = (artist or "").strip()
    if not album_text:
        return None

    import aiohttp

    timeout = aiohttp.ClientTimeout(total=_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 1) Find the album, disambiguating by artist when provided.
            album = None
            if artist:
                # Try "artist album", then "album", filtering by artist name.
                for term in (f"{artist} {album_text}", album_text):
                    album = _pick(await _search_albums(session, term), artist)
                    if album:
                        break
            if album is None:
                results = await _search_albums(session, album_text, limit=1)
                album = results[0] if results else None

            if album is None:
                logger.info("No iTunes match for album '%s' / artist '%s'", album_text, artist)
                return None
            collection_id = album.get("collectionId")
            cover = (album.get("artworkUrl100") or "").replace(
                "100x100bb", "600x600bb"
            )
            meta: dict[str, Any] = {
                "artist": album.get("artistName"),
                "title": album.get("collectionName"),
                "genre": album.get("primaryGenreName"),
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
