import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")
    ADMIN_FULLNAME: str = os.getenv("ADMIN_FULLNAME", "Administrator")

    NINEROUTER_URL: str = os.getenv("NINEROUTER_URL", "http://localhost:20128/v1/chat/completions")

    # API key router (opsional). Jika diisi, kolom "API" di sidebar otomatis disembunyikan
    # dan key ini dipakai server untuk semua panggilan ke router AI.
    NINEROUTER_API_KEY: str = os.getenv("NINEROUTER_API_KEY", "").strip()
    # Set true jika router lokal Anda tidak butuh API key sama sekali.
    NINEROUTER_NO_AUTH: bool = os.getenv("NINEROUTER_NO_AUTH", "false").strip().lower() in ("1", "true", "yes")

    # Batas token keluaran. Model "berpikir" memakai sebagian max_tokens untuk bernalar sebelum menulis JSON, sehingga batas 8000
    # mudah habis dan JSON terpotong. Model yang namanya memuat salah satu penanda di AI_THINKING_MARKERS memakai batas lebih besar.
    AI_MAX_TOKENS: int = int(os.getenv("AI_MAX_TOKENS", "8000"))
    AI_MAX_TOKENS_THINKING: int = int(os.getenv("AI_MAX_TOKENS_THINKING", "16000"))
    AI_THINKING_MARKERS: tuple = tuple(m.strip().lower() for m in os.getenv(
        "AI_THINKING_MARKERS", "deepseek,mimo,thinking,reason,-r1,qwq,o1,o3,o4").split(",") if m.strip())

    # Alur dua panggilan terpisah: (1) deteksi objek [kotak + diagnosis], (2) segmentasi [kontur] lewat tombol "Segmentasi".
    # Masing-masing punya batas token keluaran sendiri dan TIDAK PERNAH di bawah TOKEN_FLOOR (8000).
    TOKEN_FLOOR: int = 8000
    DETECT_MAX_TOKENS: int = int(os.getenv("DETECT_MAX_TOKENS", "8000"))
    DETECT_MAX_TOKENS_THINKING: int = int(os.getenv("DETECT_MAX_TOKENS_THINKING", "16000"))
    SEGMENT_MAX_TOKENS: int = int(os.getenv("SEGMENT_MAX_TOKENS", "8000"))
    SEGMENT_MAX_TOKENS_THINKING: int = int(os.getenv("SEGMENT_MAX_TOKENS_THINKING", "16000"))

    # Lintasan tambahan (grounding pass): lokalisasi temuan yang disebut di teks tanpa kotak + pengukuran CTR. Ini panggilan model KETIGA,
    # jadi bawaannya mati agar alur tetap tepat dua panggilan (deteksi + segmentasi). Aktifkan dengan GROUNDING_PASS=true bila perlu.
    GROUNDING_PASS: bool = os.getenv("GROUNDING_PASS", "false").strip().lower() in ("1", "true", "yes")
    GROUNDING_MAX_TOKENS: int = int(os.getenv("GROUNDING_MAX_TOKENS", "4000"))
    GROUNDING_MAX_TOKENS_THINKING: int = int(os.getenv("GROUNDING_MAX_TOKENS_THINKING", "10000"))

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./radiology.db")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")


settings = Settings()


def is_thinking_model(model_name: str) -> bool:
    ml = (model_name or "").lower()
    return any(m in ml for m in settings.AI_THINKING_MARKERS)


def detect_max_tokens_for(model_name: str) -> int:
    """max_tokens panggilan 1 (deteksi objek): minimal TOKEN_FLOOR; lebih besar untuk model berpikir (token berpikir ikut dihitung)."""
    v = settings.DETECT_MAX_TOKENS_THINKING if is_thinking_model(model_name) else settings.DETECT_MAX_TOKENS
    return max(settings.TOKEN_FLOOR, v)


def segment_max_tokens_for(model_name: str) -> int:
    """max_tokens panggilan 2 (segmentasi): minimal TOKEN_FLOOR; lebih besar untuk model berpikir."""
    v = settings.SEGMENT_MAX_TOKENS_THINKING if is_thinking_model(model_name) else settings.SEGMENT_MAX_TOKENS
    return max(settings.TOKEN_FLOOR, v)


def max_tokens_for(model_name: str) -> int:
    """Nama lama: batas token panggilan analisis utama (= deteksi objek)."""
    return detect_max_tokens_for(model_name)


def router_key_managed() -> bool:
    """True bila server sudah mengurus autentikasi router (key di .env / router tanpa key)."""
    return bool(settings.NINEROUTER_API_KEY) or settings.NINEROUTER_NO_AUTH


def resolve_authorization(authorization):
    """Pakai key dari form jika ada; jika kosong, pakai NINEROUTER_API_KEY dari .env."""
    if authorization and authorization.strip() and authorization.strip().lower() != "bearer":
        return authorization
    if settings.NINEROUTER_API_KEY:
        return f"Bearer {settings.NINEROUTER_API_KEY}"
    return None
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
