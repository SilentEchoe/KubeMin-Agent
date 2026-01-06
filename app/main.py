from typing import List, Optional
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

app = FastAPI(title="KubeMin-Agent Embedding API", version="0.1.0")

MODEL_NAME = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
_model: Optional[SentenceTransformer] = None


class EmbedRequest(BaseModel):
    text: Optional[str] = Field(default=None, description="Single text input.")
    texts: Optional[List[str]] = Field(
        default=None, description="Batch input for multiple texts."
    )


class EmbedResponse(BaseModel):
    model: str
    dim: int
    count: int
    embeddings: List[List[float]]


@app.on_event("startup")
def load_model() -> None:
    _ensure_model()


def _ensure_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _normalize_texts(req: EmbedRequest) -> List[str]:
    if (req.text is None) == (req.texts is None):
        raise HTTPException(
            status_code=400, detail="Provide either 'text' or 'texts'."
        )

    if req.text is not None:
        text = req.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="'text' cannot be empty.")
        return [text]

    texts = [(t or "").strip() for t in (req.texts or [])]
    if not texts or any(not t for t in texts):
        raise HTTPException(
            status_code=400, detail="'texts' cannot be empty or contain blanks."
        )
    return texts


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest) -> EmbedResponse:
    texts = _normalize_texts(req)
    model = _ensure_model()
    embeddings = model.encode(texts, normalize_embeddings=False).tolist()
    dim = len(embeddings[0]) if embeddings else 0
    return EmbedResponse(
        model=MODEL_NAME, dim=dim, count=len(embeddings), embeddings=embeddings
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": MODEL_NAME}
