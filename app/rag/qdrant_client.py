"""
Qdrant connection and the bge-m3 query encoder.

The [[compliance_normativa]] collection was built by ml/Compliance_RAG.ipynb with
dense bge-m3 vectors (1024 dims, cosine) in SP. Query vectors must come from the same
model -- a mismatch produces no error, just meaningless neighbours -- so the
encoder lives here next to the client.

Encoding uses FlagEmbedding's BGEM3FlagModel -- deliberately the same library
and the same call the ingest used, so query vectors are produced by an identical
code path rather than an equivalent one.  

First use downloads ~4 GB of weights to the HuggingFace cache; call warmup()
at app startup so no user request pays for it.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import TYPE_CHECKING

from qdrant_client import QdrantClient

from app.core.config import Settings, get_settings

if TYPE_CHECKING:  # heavy import, only needed for type checking
    from FlagEmbedding import BGEM3FlagModel

logger = logging.getLogger(__name__)


@lru_cache
def get_client(settings: Settings | None = None) -> QdrantClient:
    """Process-wide Qdrant client."""
    s = settings or get_settings()
    
    return QdrantClient(
        url=s.qdrant_url,
        api_key=s.qdrant_api_key.get_secret_value(),
        timeout=s.qdrant_timeout,
    )


@lru_cache
def get_embedder(settings: Settings | None = None) -> "BGEM3FlagModel":
    """
    Load the bge-m3 encoder once, as the ingest did.

    Notebook: `BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)`. fp16 is settings-
    driven here because the notebook ran on a Colab GPU while this box VPS has a
    CPU-only torch build, where half precision is slow and sometimes
    unimplemented. It affects numeric precision only, not the vector space.
    """
    s = settings or get_settings()
    
    if s.embedding_offline:
        # Must be set before FlagEmbedding/huggingface_hub is imported.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")

    from FlagEmbedding import BGEM3FlagModel  # lazy: slow import

    logger.info("Loading embedding model %s ...", s.embedding_model)
    
    model = BGEM3FlagModel(
        s.embedding_model,
        use_fp16=s.embedding_use_fp16,
        cache_dir=str(s.embedding_cache_dir) if s.embedding_cache_dir else None,
    )
    logger.info("Embedding model ready.")
    
    return model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch variant -- the ingest's `.encode(...)["dense_vecs"]`."""
    s = get_settings()
    
    vectors = get_embedder().encode(
        
        texts, 
        batch_size=s.embedding_batch_size, 
        max_length=s.embedding_max_length
    )["dense_vecs"]
    
    return [v.tolist() for v in vectors]


def embed_text(text: str) -> list[float]:
    """
    Encode one string into a dense 1024-dim vector.

    Mirrors the notebook's `search()`: `model.encode([q])["dense_vecs"][0]`.
    """
    return embed_texts([text])[0]


def warmup() -> None:
    """
    Preload the encoder and verify the collection is reachable.

    Call from the FastAPI lifespan handler. On a cold cache this downloads the
    model, so expect the first startup to take a while.
    """
    s = get_settings()
    embed_text("warmup")
    
    info = get_client().get_collection(s.qdrant_collection)
    
    logger.info(
        "Qdrant collection '%s' ready: %s points.", 
        s.qdrant_collection, 
        info.points_count
    )


def collection_exists() -> bool:
    
    return get_client().collection_exists(get_settings().qdrant_collection)
