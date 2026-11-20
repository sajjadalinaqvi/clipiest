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
    "lmstudio": "http://localhost:1235/v1",
    "ollama": "http://127.0.0.1:11434/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "xai": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "custom": "http://localhost:1235/v1"
}

LOCAL_FALLBACK_URLS = [
    "http://localhost:1235/v1",
    "http://127.0.0.1:1235/v1",
    "http://127.0.0.1:1234/v1",
    "http://localhost:1234/v1",
    "http://127.0.0.1:11434/v1"
]

def list_supported_providers() -> list[str]:
    return list(PROVIDERS.keys())

def explain_ai_error(e: Exception, provider: str = "AI") -> str:
    """Explains AI errors in clear actionable terms."""
    msg = str(e).lower()
    if "refused" in msg or "10061" in msg or "connecterror" in msg:
        return f"Could not connect to {provider.upper()}. Ensure LM Studio or Ollama is running and Local Server is started."
    if "401" in msg or "403" in msg or "key" in msg:
        return f"Authentication failed for {provider.upper()}. Check your API key under Settings -> AI."
    if "404" in msg or "not found" in msg:
        return f"The model requested does not exist on {provider.upper()}. Click 'Fetch Models' in Settings to select a loaded model."
    if "429" in msg or "quota" in msg or "rate limit" in msg:
        return f"{provider.upper()} rate limit or quota exceeded. Please check your provider account."
    if "timed out" in msg or "readtimeout" in msg:
        return f"{provider.upper()} took too long to reply (>120s). The model may still be loading into VRAM."
    return str(e)

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
    base_url = (base_url or PROVIDERS.get(provider, "http://localhost:1235/v1")).rstrip("/")
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
            m_target = model or "qwen/qwen3.5-9b"
            res = _call_openai_compat(base_url, m_target, api_key or "lm-studio", test_prompt, allow_fallback=False)
            
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
            "error": explain_ai_error(e, provider)
        }

def fetch_models_with_url(provider: str, base_url: str = "", api_key: str = "") -> tuple[list[str], str]:
    """Fetches list of available models and returns the working base_url that responded."""
    provider = (provider or "lmstudio").lower().strip()
    base_url = (base_url or PROVIDERS.get(provider, "http://localhost:1235/v1")).rstrip("/")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    urls_to_try = [base_url]
    if provider in ("lmstudio", "custom", "ollama"):
        for alt in LOCAL_FALLBACK_URLS:
            if alt not in urls_to_try:
                urls_to_try.append(alt)

    for target_url in urls_to_try:
        try:
            if provider in ("lmstudio", "ollama", "openai", "groq", "openrouter", "custom"):
                with httpx.Client(timeout=8.0) as client:
                    r = client.get(f"{target_url}/models", headers=headers)
                    if r.status_code == 200:
                        data = r.json()
                        models = [item["id"] for item in data.get("data", []) if "id" in item]
                        if models:
                            return models, target_url
            elif provider == "gemini" and api_key:
                with httpx.Client(timeout=10.0) as client:
                    r = client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}")
                    if r.status_code == 200:
                        data = r.json()
                        return [m["name"].replace("models/", "") for m in data.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])], target_url
        except Exception:
            continue
        
    defaults = {
        "lmstudio": ["qwen/qwen3.5-9b", "local-model", "qwen2.5-7b-instruct", "deepseek-r1-distill-qwen-7b", "llama-3.2-3b-instruct"],
        "ollama": ["llama3.2:3b", "llama3.1:8b", "mistral", "qwen2.5:7b"],
        "gemini": ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
        "openai": ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
        "anthropic": ["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"],
        "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
        "openrouter": ["meta-llama/llama-3.2-3b-instruct:free", "google/gemini-2.5-flash", "anthropic/claude-3.5-haiku"]
    }
    return defaults.get(provider, ["default-model"]), base_url

def fetch_models_from_provider(provider: str, base_url: str = "", api_key: str = "") -> list[str]:
    """Fetches list of available/loaded models from LM Studio, Ollama, or OpenAI."""
    models, _ = fetch_models_with_url(provider, base_url, api_key)
    return models

def ask_llm(prompt: str, schema: dict = None, model: str = None) -> dict | list:
    """Invokes LLM with fallback handling and returns parsed JSON response."""
    cfg = load_user_config()
    ai_cfg = cfg.get("ai", {})
    provider = (ai_cfg.get("provider") or AI_PROVIDER or "lmstudio").lower().strip()
    key = ai_cfg.get("api_key") or AI_KEY or ""
    if not key and provider in ("lmstudio", "custom", "ollama"):
        key = "lm-studio"
    base_url = (ai_cfg.get("base_url") or AI_BASE_URL or PROVIDERS.get(provider, "http://localhost:1235/v1")).rstrip("/")
    models = [model] if model else ([ai_cfg.get("model")] if ai_cfg.get("model") else AI_MODELS)

    last_err = None
    for m in models:
        try:
            if provider == "gemini":
                return _call_gemini(m, key, prompt)
            elif provider == "anthropic":
                return _call_anthropic(m, key, prompt)
            else:
                # OpenAI-compatible protocol (LM Studio, Ollama, OpenAI, Groq, OpenRouter, Custom)
                return _call_openai_compat(base_url, m, key, prompt)
        except Exception as e:
            last_err = e
            continue
            
    # Direct LM Studio & Ollama fallback attempts before giving up
    if provider in ("lmstudio", "custom", "ollama"):
        for fallback_base in LOCAL_FALLBACK_URLS:
            if fallback_base == base_url:
                continue
            try:
                return _call_openai_compat(fallback_base, models[0] if models else "qwen/qwen3.5-9b", "lm-studio", prompt)
            except Exception as e:
                last_err = e
                pass

    raise RuntimeError(f"All AI providers failed: {explain_ai_error(last_err or Exception('connection failed'), provider)}")

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

def _call_openai_compat(base_url: str, model: str, key: str, prompt: str, allow_fallback: bool = True):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    messages = [
        {"role": "system", "content": "You are a professional viral short-form video editor AI. Reply ONLY with valid JSON. Never output markdown, explanations or conversational text outside JSON."},
        {"role": "user", "content": prompt}
    ]
    # For reasoning models (Qwen, DeepSeek-R1), add closed think tag to bypass long CoT generation
    if any(tag in (model or "").lower() for tag in ("qwen", "r1", "deepseek", "reason")):
        messages.append({"role": "assistant", "content": "</think>\n"})

    payload = {
        "model": model or "local-model",
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2048
    }
    
    urls_to_attempt = [base_url]
    if allow_fallback and any(h in base_url for h in ("localhost", "127.0.0.1")):
        for alt in LOCAL_FALLBACK_URLS:
            if alt not in urls_to_attempt:
                urls_to_attempt.append(alt)
                
    last_ex = None
    for target in urls_to_attempt:
        try:
            with httpx.Client(timeout=120.0) as client:
                r = client.post(f"{target}/chat/completions", headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
                msg = data["choices"][0]["message"]
                raw = (msg.get("content") or "").strip()
                if not raw and msg.get("reasoning_content"):
                    raw = msg.get("reasoning_content", "").strip()
                cleaned = _clean_json_text(raw)
                return json.loads(cleaned)
        except Exception as e:
            last_ex = e
            # Only failover to another local URL if it was a connection/refusal error
            if "connect" in str(e).lower() or "refused" in str(e).lower():
                continue
            raise e
            
    raise last_ex or RuntimeError("Failed to communicate with OpenAI-compatible endpoint.")

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
