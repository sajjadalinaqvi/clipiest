"""Universal multi-provider AI gateway for Clipiest.
Supports: LM Studio (Local), Ollama (Local), Google Gemini, OpenAI, Anthropic Claude, Groq, xAI Grok, OpenRouter, and Custom OpenAI endpoints.
"""
import re
import json
import time
import urllib.request
import httpx
from ..config import AI_PROVIDER, AI_KEY, AI_MODELS, AI_BASE_URL, load_user_config

PROVIDERS = {
    "lmstudio": "http://127.0.0.1:1234/v1",
    "ollama": "http://127.0.0.1:11434/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "xai": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "custom": "http://127.0.0.1:1234/v1"
}

def list_supported_providers() -> list[str]:
    return list(PROVIDERS.keys())

def _clean_json_text(raw: str) -> str:
    """Strips <think> tags, markdown blocks, and surrounding conversational filler."""
    text = str(raw or "").strip()
    # Strip <think>...</think> reasoning blocks common in LM Studio (DeepSeek-R1, Qwen)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Extract from markdown code fences if present (```json ... ``` or ``` ... ```)
    m_code = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if m_code:
        text = m_code.group(1).strip()
    # Extract from outermost { or [ to matching } or ]
    m = re.search(r"(\{|\[)[\s\S]*(\}|\])", text)
    if m:
        text = m.group(0).strip()
    return text

def test_llm_connection(provider: str, base_url: str = "", api_key: str = "", model: str = "") -> dict:
    """Tests connection to the specified LLM provider and measures latency."""
    t0 = time.monotonic()
    provider = (provider or "lmstudio").lower().strip()
    base_url = (base_url or PROVIDERS.get(provider, "http://127.0.0.1:1234/v1")).rstrip("/")
    test_prompt = "Reply strictly with this JSON: {\"status\": \"ok\", \"name\": \"Clipiest\"}"
    
    try:
        if provider == "gemini":
            m_target = model or "gemini-2.5-flash"
            res = _call_gemini(m_target, api_key, test_prompt)
        elif provider == "anthropic":
            m_target = model or "claude-3-5-haiku-20241022"
            res = _call_anthropic(m_target, api_key, test_prompt)
        else:
            # LM Studio, Ollama, OpenAI, Groq, OpenRouter, Custom
            m_target = model or "local-model"
            res = _call_openai_compat(base_url, m_target, api_key, test_prompt)
            
        latency = int((time.monotonic() - t0) * 1000)
        return {
            "ok": True,
            "success": True,
            "latency_ms": latency,
            "provider": provider,
            "model": m_target,
            "message": f"Successfully connected to {provider.upper()}! Response received in {latency}ms."
        }
    except Exception as e:
        return {
            "ok": False,
            "success": False,
            "provider": provider,
            "error": str(e)
        }

def fetch_models_from_provider(provider: str, base_url: str = "", api_key: str = "") -> list[str]:
    """Fetches list of available/loaded models from LM Studio, Ollama, or OpenAI."""
    provider = (provider or "lmstudio").lower().strip()
    base_url = (base_url or PROVIDERS.get(provider, "http://127.0.0.1:1234/v1")).rstrip("/")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        if provider in ("lmstudio", "ollama", "openai", "groq", "openrouter", "custom"):
            with httpx.Client(timeout=10.0) as client:
                r = client.get(f"{base_url}/models", headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    models = [item["id"] for item in data.get("data", []) if "id" in item]
                    if models:
                        return models
        elif provider == "gemini" and api_key:
            with httpx.Client(timeout=10.0) as client:
                r = client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}")
                if r.status_code == 200:
                    data = r.json()
                    return [m["name"].replace("models/", "") for m in data.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    except Exception:
        pass
        
    # Standard sensible fallbacks per provider
    defaults = {
        "lmstudio": ["local-model", "qwen2.5-7b-instruct", "deepseek-r1-distill-qwen-7b", "llama-3.2-3b-instruct"],
        "ollama": ["llama3.2:3b", "llama3.1:8b", "mistral", "qwen2.5:7b"],
        "gemini": ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
        "openai": ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
        "anthropic": ["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"],
        "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
        "openrouter": ["meta-llama/llama-3.2-3b-instruct:free", "google/gemini-2.5-flash", "anthropic/claude-3.5-haiku"]
    }
    return defaults.get(provider, ["default-model"])

def ask_llm(prompt: str, schema: dict = None, model: str = None) -> dict | list:
    """Invokes LLM with fallback handling and returns parsed JSON response."""
    cfg = load_user_config()
    ai_cfg = cfg.get("ai", {})
    provider = (ai_cfg.get("provider") or AI_PROVIDER or "lmstudio").lower().strip()
    key = ai_cfg.get("api_key") or AI_KEY or ""
    base_url = (ai_cfg.get("base_url") or AI_BASE_URL or PROVIDERS.get(provider, "http://127.0.0.1:1234/v1")).rstrip("/")
    models = [model] if model else ([ai_cfg.get("model")] if ai_cfg.get("model") else AI_MODELS)

    for m in models:
        try:
            if provider == "gemini":
                return _call_gemini(m, key, prompt)
            elif provider == "anthropic":
                return _call_anthropic(m, key, prompt)
            else:
                # OpenAI-compatible protocol (LM Studio, Ollama, OpenAI, Groq, OpenRouter, Custom)
                return _call_openai_compat(base_url, m, key, prompt)
        except Exception:
            continue
            
    # Direct LM Studio & Ollama fallback attempts before giving up
    for fallback_base in ("http://127.0.0.1:1234/v1", "http://127.0.0.1:11434/v1"):
        try:
            return _call_openai_compat(fallback_base, models[0] if models else "local-model", "", prompt)
        except Exception:
            pass

    raise RuntimeError("All AI providers failed. Check your LLM settings and verify your local LM Studio / Ollama server is running.")

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
        return json.loads(_clean_json_text(raw))

def _call_openai_compat(base_url: str, model: str, key: str, prompt: str):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": model or "local-model",
        "messages": [
            {"role": "system", "content": "You are a professional viral short-form video editor AI. Reply ONLY with valid JSON. Never output markdown, explanations or conversational text outside JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    with httpx.Client(timeout=45.0) as client:
        r = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        cleaned = _clean_json_text(raw)
        return json.loads(cleaned)

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
        cleaned = _clean_json_text(raw)
        return json.loads(cleaned)
