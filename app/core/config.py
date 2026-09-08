
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py -> app/core -> app -> my repo root
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # APP SETTINGS
    app_name: str = "Beau-Auto-Repairs-Inspector"
    agent_name : str = "ColCar"
    environment: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = True
    api_prefix: str = "/api"
    log_level: str = "INFO"

    # This project serves on 8015, not uvicorn's default 8000:
    # frontend/vite.config.ts must proxy /api to the same port.
    api_host: str = "0.0.0.0"
    api_port: int = 8015

    # Load models and the embedder during startup rather than on the first
    # request. Costs ~8 s of boot; the alternative is a customer waiting for it,
    # and a cold HF cache check once stalled a request for 8 minutes.
    warmup_on_startup: bool = True

    # Vite dev (5173) and vite preview (4173) proxy /api to the backend, so the
    # SPA works either way. 8015 is listed for direct hits on the API host
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:4173",
        "http://localhost:8015",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8015",
    ] # to be changed with the subdoamin

    #  Anthropic  
    anthropic_api_key: SecretStr
    # Claude drives the tool-use loop only; the ONNX models do the perception,
    # so it never receives an image and Haiku is sufficient cheap and fast .
    anthropic_model: str = "claude-haiku-4-5"
    anthropic_max_tokens: int = 2048
    # Guards the agent loop against a tool-calling cycle that never terminates.
    anthropic_max_tool_iterations: int = 8

    # How many recent messages the agent keeps in context.
    agent_memory_messages: int = 5

    # Keep the query_pricing_batch tool_use/tool_result pair in context for the
    # whole conversation, on top of the window.
    agent_pin_pricing: bool = True

    #  API Ninjas / engine specifications 
    # Optional: without a key the query_car_specs tool reports itself as
    # unavailable and everything else keeps working. Read from API_NINJA_KEY.
    api_ninja_key: SecretStr | None = None
    api_ninja_cars_url: str = "https://api.api-ninjas.com/v1/cars"
    api_ninja_timeout: int = 10

    #  MongoDB Atlas
    # Source of truth for the pricing catalog and the brand index (v2). Optional:
    # when unset -- or unreachable -- both loaders fall back to the local JSON files
    # and log an error, so tests, CI and a Mongo outage still quote. The URI
    # carries the password; it is in the log redaction filter.
    mongodb_uri: SecretStr | None = None
    mongodb_db: str = "car_scanner"
    mongodb_timeout_ms: int = 5000
    pricing_collection: str = "pricing_catalog"
    brands_collection: str = "car_brands"
    catalog_meta_collection: str = "catalog_meta"
    inspections_collection: str = "inspections"
    appointments_collection: str = "appointments"

    #  Workshop scheduling (make_appointment tool)
    # Slots are validated in the workshop's local time, then stored in UTC.
    workshop_timezone: str = "America/Bogota"
    workshop_open_hour: int = 8  # first bookable slot, inclusive
    workshop_close_hour: int = 18  # last bookable slot starts before this
    workshop_days: list[int] = [0, 1, 2, 3, 4, 5]  # Mon..Sat (datetime.weekday)
    appointment_code_length: int = 6

    #  Qdrant / compliance RAG
    qdrant_url: str
    qdrant_api_key: SecretStr
    qdrant_collection: str = "compliance_normativa"
    qdrant_timeout: int = 30

    # The live collection was built with bge-m3 dense vectors at 1024 dims and
    # cosine distance. Queries MUST be embedded the same way or search returns
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    # Both mirror the ingest's encode() call.
    embedding_max_length: int = 512
    embedding_batch_size: int = 12
    embedding_use_fp16: bool = False
    # Where the weights live. None = HuggingFace default (~/.cache/huggingface).
    # Point this at a mounted volume in Docker so the download does not repeat
    # on every container rebuild.
    embedding_cache_dir: Path | None = None
    # Once the weights are cached, skip HuggingFace's network validation.
    embedding_offline: bool = True

    # Fixed project decision, not a tuning knob. k=3 is load-bearing: for
    # back_glass the correct clause lands at rank 2 behind an unrelated tyre
    # row, so k=2 would drop it. Raising k feeds the agent more low-relevance
    # text, which is what the scope gate exists to prevent.
    compliance_top_k: int = 3

    #  Pricing 
    # Source for the in-memory PricingTrie, loaded once at startup:
    # pieza -> tipo_defecto -> severidad, plus `generic:*` fallback nodes.
    pricing_catalog_path: Path = BASE_DIR / "AUTOPAIRS_CATALOG_PRICES.json"
    car_models_path: Path = BASE_DIR / "app" / "rag" / "car_models.json"

    #  Vision Models 
    models_dir: Path = BASE_DIR / "models"
    car_parts_model: str = "car_parts_model.onnx"
    car_defects_model: str = "car_defects_model.onnx"
    tyres_defect_model: str = "tyres_defect_model.onnx"

    # An inspection is a single sitting: upload, run, read the report, ask a
    # few questions. Sessions are swept on the next create() or purge call.
    session_ttl_minutes: int = 120

    upload_dir: Path = BASE_DIR / "data" / "uploads"
    max_upload_mb: int = 15
    allowed_image_types: list[str] = ["image/jpeg", "image/png", "image/webp"]

    # Per-panel upload caps, enforced by the routers. Both segmentation models
    # run over every surface image (~1.5 s/image on this CPU), so 3 is a
    # latency budget, not an arbitrary limit. 
    max_images_surface: int = 3
    max_images_tyres: int = 1

    # 0 = let ONNX Runtime choose. Pin it if inference competes with the
    # embedder for cores on this CPU-only box.
    onnx_intra_op_threads: int = 0
    det_confidence_threshold: float = 0.25
    nms_iou_threshold: float = 0.45  
    # Severity bands, as defect-area / part-area ratios. Half-open:
    #   ratio < leve_max              -> leve      (Bajo)
    #   leve_max <= r < moderado_max  -> moderado  (Medio)
    #   ratio >= moderado_max         -> grave     (Grave)
    # The spec's own bands overlapped (0.25-0.35 was both Medium and High) and
    # left 0.1-0.2 ungraded; resolved with the owner in favour of the < 0.1 and
    # > 0.25 bounds, with moderado filling the gap.
    severity_leve_max: float = 0.10
    severity_moderado_max: float = 0.25

    # Same bands for defects with no parent part (tyres, unmatched), measured
    # against image area. Higher because this ratio is dominated by how close
    # the photo was taken -- a tyre close-up fills the frame without being severe.
    severity_image_leve_max: float = 0.20
    severity_image_moderado_max: float = 0.45

    # A tyre defect whose type can escalate (Cracks, Flat spots) becomes
    # GRAVE at or above this share of the image. Real defects measured
    # 0.3%-6.5%; a full-tread flat spot measured 62.7%.
    severity_tyre_escalate_ratio: float = 0.15

    # Minimum *containment* (defect area inside the part) to attribute a defect
    # to a part -- not IoU, which is near-zero for a small defect on a large
    # panel. Below this the defect lands in unmatched_defects.
    spatial_match_min_containment: float = 0.50

    @field_validator("qdrant_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("mongodb_uri", "api_ninja_key", mode="before")
    @classmethod
    def _empty_secret_is_unset(cls, v: object) -> object:
        # `MONGODB_URI=` left blank in .env (or set to "" by the test suite to
        # force the JSON fallback) means "not configured", not an empty key.
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def car_parts_model_path(self) -> Path:
        return self.models_dir / self.car_parts_model

    @computed_field  # type: ignore[prop-decorator]
    @property
    def car_defects_model_path(self) -> Path:
        return self.models_dir / self.car_defects_model

    @computed_field  # type: ignore[prop-decorator]
    @property
    def tyres_defect_model_path(self) -> Path:
        return self.models_dir / self.tyres_defect_model

    @computed_field  # type: ignore[prop-decorator]
    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Cached accessor -- also the FastAPI dependency.

    Usage in a router:
        def endpoint(settings: Annotated[Settings, Depends(get_settings)]): ...
    """
    return Settings()  # type: ignore[call-arg]  # values come from .env


settings = get_settings()
