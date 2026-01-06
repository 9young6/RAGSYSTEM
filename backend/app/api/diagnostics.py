from __future__ import annotations

import requests
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.config import settings
from app.models.user import User
from app.schemas.diagnostics import (
    InferenceProviderDiagnosticsRequest,
    InferenceProviderDiagnosticsResponse,
    OllamaDiagnosticsRequest,
    OllamaDiagnosticsResponse,
    RerankDiagnosticsRequest,
    RerankDiagnosticsResponse,
)


router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.post("/ollama", response_model=OllamaDiagnosticsResponse)
def diagnose_ollama(
    payload: OllamaDiagnosticsRequest,
    _: User = Depends(get_current_user),
) -> OllamaDiagnosticsResponse:
    base = settings.OLLAMA_BASE_URL.rstrip("/")
    models_found: list[str] = []

    llm_ok = False
    llm_error: str | None = None
    llm_preview: str | None = None

    embedding_ok = False
    embedding_error: str | None = None
    embedding_dimension: int | None = None

    try:
        r = requests.get(f"{base}/api/tags", timeout=10)
        r.raise_for_status()
        data = r.json()
        models_found = [m.get("name") for m in (data.get("models") or []) if isinstance(m, dict) and m.get("name")]
    except Exception as exc:
        return OllamaDiagnosticsResponse(
            ok=False,
            ollama_base_url=settings.OLLAMA_BASE_URL,
            models_found=[],
            llm_ok=False,
            llm_error=f"tags failed: {exc}",
            embedding_ok=False,
            embedding_error="tags failed",
        )

    # Embeddings test
    try:
        r = requests.post(
            f"{base}/api/embeddings",
            json={"model": payload.embedding_model, "prompt": "ping"},
            timeout=30,
        )
        r.raise_for_status()
        emb = r.json().get("embedding")
        if not isinstance(emb, list) or not emb:
            raise ValueError("unexpected embeddings response")
        embedding_dimension = len(emb)
        embedding_ok = True
    except Exception as exc:
        embedding_error = str(exc)

    # LLM generate test
    try:
        r = requests.post(
            f"{base}/api/generate",
            json={
                "model": payload.llm_model,
                "prompt": payload.prompt,
                "stream": False,
                "options": {"temperature": payload.temperature},
            },
            timeout=60,
        )
        r.raise_for_status()
        text = r.json().get("response")
        if not isinstance(text, str):
            raise ValueError("unexpected generate response")
        llm_preview = text.strip()[:200]
        llm_ok = True
    except Exception as exc:
        llm_error = str(exc)

    ok = llm_ok and embedding_ok
    return OllamaDiagnosticsResponse(
        ok=ok,
        ollama_base_url=settings.OLLAMA_BASE_URL,
        models_found=models_found,
        llm_ok=llm_ok,
        llm_error=llm_error,
        llm_preview=llm_preview,
        embedding_ok=embedding_ok,
        embedding_error=embedding_error,
        embedding_dimension=embedding_dimension,
    )


def _openai_chat_completion(base_url: str, api_key: str | None, model: str, prompt: str, temperature: float) -> str:
    url = base_url.rstrip("/") + "/v1/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "stream": False,
    }
    r = requests.post(url, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("no choices")
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if not isinstance(content, str):
        raise ValueError("unexpected response format")
    return content


@router.post("/inference", response_model=InferenceProviderDiagnosticsResponse)
def diagnose_inference_provider(
    payload: InferenceProviderDiagnosticsRequest,
    _: User = Depends(get_current_user),
) -> InferenceProviderDiagnosticsResponse:
    provider = (payload.provider or "").lower()
    try:
        if provider == "ollama":
            base = settings.OLLAMA_BASE_URL
            url = base.rstrip("/") + "/api/generate"
            r = requests.post(
                url,
                json={"model": payload.model, "prompt": payload.prompt, "stream": False, "temperature": payload.temperature},
                timeout=60,
            )
            r.raise_for_status()
            text = r.json().get("response")
            if not isinstance(text, str):
                raise ValueError("unexpected ollama response")
            return InferenceProviderDiagnosticsResponse(
                ok=True,
                provider="ollama",
                base_url=base,
                model=payload.model,
                preview=text.strip()[:200],
            )

        if provider == "vllm":
            base = settings.VLLM_BASE_URL or ""
            if not base:
                raise ValueError("VLLM_BASE_URL not configured")
            text = _openai_chat_completion(base, settings.VLLM_API_KEY, payload.model, payload.prompt, payload.temperature)
            return InferenceProviderDiagnosticsResponse(ok=True, provider="vllm", base_url=base, model=payload.model, preview=text.strip()[:200])

        if provider == "xinference":
            base = settings.XINFERENCE_BASE_URL or ""
            if not base:
                raise ValueError("XINFERENCE_BASE_URL not configured")
            text = _openai_chat_completion(base, settings.XINFERENCE_API_KEY, payload.model, payload.prompt, payload.temperature)
            return InferenceProviderDiagnosticsResponse(ok=True, provider="xinference", base_url=base, model=payload.model, preview=text.strip()[:200])

        raise ValueError(f"Unsupported provider: {provider}")
    except Exception as exc:
        base_url = (
            settings.OLLAMA_BASE_URL
            if provider == "ollama"
            else (settings.VLLM_BASE_URL or "")
            if provider == "vllm"
            else (settings.XINFERENCE_BASE_URL or "")
            if provider == "xinference"
            else ""
        )
        return InferenceProviderDiagnosticsResponse(
            ok=False,
            provider=provider or payload.provider,
            base_url=base_url,
            model=payload.model,
            error=str(exc),
        )


@router.post("/rerank", response_model=RerankDiagnosticsResponse)
def diagnose_rerank(
    payload: RerankDiagnosticsRequest,
    _: User = Depends(get_current_user),
) -> RerankDiagnosticsResponse:
    provider = (payload.provider or "").lower()
    if provider != "xinference":
        return RerankDiagnosticsResponse(ok=False, provider=provider, base_url="", model=payload.model, error="Only xinference supported")

    base = settings.XINFERENCE_BASE_URL or ""
    if not base:
        return RerankDiagnosticsResponse(ok=False, provider="xinference", base_url="", model=payload.model, error="XINFERENCE_BASE_URL not configured")

    try:
        url = base.rstrip("/") + "/v1/rerank"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if settings.XINFERENCE_API_KEY:
            headers["Authorization"] = f"Bearer {settings.XINFERENCE_API_KEY}"
        r = requests.post(
            url,
            json={"model": payload.model, "query": payload.query, "documents": payload.documents},
            headers=headers,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or data.get("data") or data.get("rerank") or []
        scores: list[float] = []
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict) and "score" in item:
                    scores.append(float(item["score"]))
        if not scores and isinstance(data.get("scores"), list):
            scores = [float(s) for s in data["scores"]]
        if not scores:
            raise ValueError("unexpected rerank response format")

        return RerankDiagnosticsResponse(ok=True, provider="xinference", base_url=base, model=payload.model, scores=scores)
    except Exception as exc:
        return RerankDiagnosticsResponse(ok=False, provider="xinference", base_url=base, model=payload.model, error=str(exc))
