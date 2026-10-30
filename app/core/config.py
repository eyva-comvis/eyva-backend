from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    cors_origins: str = "http://localhost:3000"
    # Dev: izinkan localhost/127.0.0.1 di port mana pun (mis. buka web lewat http://127.0.0.1:3000 atau port lain).
    cors_origin_regex: str = r"https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$"

    inference_backend: str = "mock"  # mock | yolo
    model_path: str = "../models/best.pt"
    mock_scenario: str = "normal"  # normal | drowsy

    # Parameter YOLO (hanya untuk INFERENCE_BACKEND=yolo)
    yolo_conf: float = 0.25  # batas bawah deteksi; filter lebih ketat ada di temporal.MIN_CONF
    yolo_imgsz: int = 640
    yolo_device: str = ""  # "" = otomatis (GPU jika ada), atau "cpu" / "0"
    # Peta nama kelas bila data.yaml berbeda dari yang diharapkan, mis. {"closed_eye":"eye_closed"}
    yolo_label_aliases: dict[str, str] = {}

    # Threshold sementara; dituning dari uji webcam.
    eye_closure_seconds: float = 1.5
    alert1_confirm_seconds: float = 3.0
    alert2_recheck_seconds: float = 5.0
    alert_cooldown_seconds: float = 30.0

    supabase_url: str = ""
    supabase_jwt_secret: str = ""  # hanya untuk proyek lama (HS256); proyek baru memakai JWKS dari SUPABASE_URL
    supabase_jwt_audience: str = "authenticated"
    auth_required: bool = False  # true = semua endpoint sesi butuh login
    supabase_service_key: str = ""
    # LLM (rekomendasi Summary + tip Break). Default OpenRouter + DeepSeek varian gratis; slug model bisa berubah,
    # cek https://openrouter.ai/models?q=deepseek&max_price=0 lalu isi LLM_MODEL.
    llm_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "deepseek/deepseek-chat-v3-0324:free"
    llm_timeout_seconds: float = 20.0  # per permintaan
    llm_total_seconds: float = 45.0  # batas seluruh percobaan (semua model + ulang)
    # Model cadangan (dipisah koma) yang dicoba OpenRouter bila model utama kena rate limit/gagal.
    llm_fallback_models: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
