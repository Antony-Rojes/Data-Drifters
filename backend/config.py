import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")  # change if AI Studio shows a newer name
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "")
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
EMBED_DIMS = 256  # small vectors keep store.json light

UPLOAD_DIR = BASE_DIR / "data" / "uploads"
CACHE_DIR = BASE_DIR / "data" / "cache"
ARCHIVE_DIR = BASE_DIR / "data" / "archive"
STORE_PATH = CACHE_DIR / "store.json"
FRONTEND_DIR = BASE_DIR / "frontend"

MAX_UPLOAD_MB = 25
OCR_MIN_CHARS = 40  # a page with less text than this is treated as scanned

for folder in (UPLOAD_DIR, CACHE_DIR, ARCHIVE_DIR):
    folder.mkdir(parents=True, exist_ok=True)