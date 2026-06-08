import uvicorn
from nfc_jukebox.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "nfc_jukebox.app:app",
        host=settings.WEB_HOST,
        port=settings.WEB_PORT,
        reload=False,
        log_level="info",
    )
