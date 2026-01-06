from __future__ import annotations

import requests

from app.config import settings


class LLMUnavailableError(RuntimeError):
    pass


class LLMService:
    def generate(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        provider_norm = (provider or "ollama").strip().lower()
        if provider_norm == "ollama":
            return self._generate_ollama(prompt=prompt, model=model, temperature=temperature)
        if provider_norm == "vllm":
            return self._generate_openai_compatible(
                base_url=settings.VLLM_BASE_URL,
                api_key=settings.VLLM_API_KEY,
                provider_label="vllm",
                prompt=prompt,
                model=model,
                temperature=temperature,
            )
        if provider_norm == "xinference":
            return self._generate_openai_compatible(
                base_url=settings.XINFERENCE_BASE_URL,
                api_key=settings.XINFERENCE_API_KEY,
                provider_label="xinference",
                prompt=prompt,
                model=model,
                temperature=temperature,
            )
        raise LLMUnavailableError(f"Unknown LLM provider: {provider_norm}")

    def _generate_ollama(self, *, prompt: str, model: str | None, temperature: float | None) -> str:
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
        payload = {
            "model": model or settings.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "temperature": temperature if temperature is not None else settings.OLLAMA_TEMPERATURE,
        }
        try:
            response = requests.post(url, json=payload, timeout=180)
        except requests.RequestException as exc:
            raise LLMUnavailableError(f"Ollama request failed: {exc}") from exc

        if response.status_code != 200:
            detail = ""
            try:
                detail = str(response.json().get("error") or "")
            except Exception:
                detail = response.text.strip()
            raise LLMUnavailableError(detail or f"HTTP {response.status_code}")

        data = response.json()
        return str(data.get("response") or "")

    def _generate_openai_compatible(
        self,
        *,
        base_url: str | None,
        api_key: str | None,
        provider_label: str,
        prompt: str,
        model: str | None,
        temperature: float | None,
    ) -> str:
        if not base_url:
            raise LLMUnavailableError(f"{provider_label} base_url is not configured")
        if not model:
            raise LLMUnavailableError("model is required for OpenAI-compatible providers")

        url = f"{base_url.rstrip('/')}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature if temperature is not None else 0.7,
            "stream": False,
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=180)
        except requests.RequestException as exc:
            raise LLMUnavailableError(f"{provider_label} request failed: {exc}") from exc

        if response.status_code != 200:
            detail = ""
            try:
                data = response.json()
                detail = str(data.get("error") or data.get("message") or "")
            except Exception:
                detail = response.text.strip()
            raise LLMUnavailableError(detail or f"HTTP {response.status_code}")

        data = response.json()
        try:
            choices = data.get("choices") or []
            if choices:
                msg = (choices[0] or {}).get("message") or {}
                if "content" in msg:
                    return str(msg.get("content") or "")
                # some implementations may return "text"
                if "text" in choices[0]:
                    return str((choices[0] or {}).get("text") or "")
        except Exception:
            pass
        raise LLMUnavailableError(f"Unexpected {provider_label} response format")
