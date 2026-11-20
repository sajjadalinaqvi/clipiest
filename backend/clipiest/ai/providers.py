"""Universal multi-provider AI gateway for Clipiest.
Supports: Gemini, OpenAI, Anthropic Claude, Groq, xAI Grok, OpenRouter, Ollama, LM Studio, and Custom OpenAI endpoints.
"""
import json
import urllib.request
import httpx
from ..config import AI_PROVIDER, AI_KEY, AI_MODELS, AI_BASE_URL

PROVIDERS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "xai": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://127.0.0.1:11434/v1",
    "custom": AI_BASE_URL or "http://localhost:1235/v1"
}

def list_supported_providers() -> list[str]:
    return list(PROVIDERS.keys())

def ask_llm(prompt: str, schema: dict = None, model: str = None) -> dict | list:
    """Invokes LLM with fallback handling and returns parsed JSON response."""
    provider = AI_PROVIDER
    key = AI_KEY
    models = [model] if model else AI_MODELS

    for m in models:
        try:
            if provider == "gemini":
                return _call_gemini(m, key, prompt)
            elif provider == "anthropic":
                return _call_anthropic(m, key, prompt)
            else:
                # OpenAI-compatible protocol (OpenAI, Grok, Groq, OpenRouter, Ollama, Custom)
                base = AI_BASE_URL or PROVIDERS.get(provider, "https://api.openai.com/v1")
                return _call_openai_compat(base, m, key, prompt)
        except Exception:
            continue
            
    # Local Ollama direct fallback
    try:
        body = json.dumps({
            "model": models[0] if models else "llama3.2:3b",
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }).encode()
        req = urllib.request.Request("http://127.0.0.1:11434/api/generate", body, {"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(json.loads(resp.read().decode())["response"])
    except Exception as e:
        raise RuntimeError(f"All AI providers failed: {e}")

def _call_gemini(model: str, key: str, prompt: str):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }
    with httpx.Client(timeout=45.0) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(raw)

def _call_openai_compat(base_url: str, model: str, key: str, prompt: str):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a professional video editor AI. Reply ONLY with valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    with httpx.Client(timeout=45.0) as client:
        r = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        # Clean markdown codeblocks if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)

def _call_anthropic(model: str, key: str, prompt: str):
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    payload = {
        "model": model or "claude-3-5-haiku-20241022",
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}]
    }
    with httpx.Client(timeout=45.0) as client:
        r = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
        r.raise_for_status()
        raw = r.json()["content"][0]["text"].strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)
