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
    if isinstance(e, (httpx.ConnectTimeout, httpx.ConnectError)) or any(term in msg for term in ("refused", "10061", "connecterror", "connecttimeout", "failed to establish")):
        return f"Could not connect to {provider.upper()}. Ensure LM Studio or Ollama is running and Local Server is started."
    if "401" in msg or "403" in msg or "key" in msg:
        return f"Authentication failed for {provider.upper()}. Check your API key under Settings -> AI."
    if "404" in msg or "not found" in msg:
        return f"The model requested does not exist on {provider.upper()}. Click 'Fetch Models' in Settings to select a loaded model."
    if "429" in msg or "quota" in msg or "rate limit" in msg:
        return f"{provider.upper()} rate limit or quota exceeded. Please check your provider account."
    if isinstance(e, httpx.ReadTimeout) or "readtimeout" in msg:
        return f"{provider.upper()} took too long to generate response (>120s). The model may still be generating or loading into VRAM."
    return str(e)

def _clean_json_text(raw: str) -> str:
    """Strips <think> tags, markdown blocks, trailing commas, and repairs unclosed LLM JSON."""
    text = str(raw or "").strip()
    # Strip <think>...</think> reasoning blocks common in LM Studio (DeepSeek-R1, Qwen)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Extract from markdown code fences if present (```json ... ``` or ``` ... ```)
    m_code = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if m_code:
        text = m_code.group(1).strip()
    # Fix missing comma between objects: } { -> }, {
    text = re.sub(r"}\s*\n*\s*{", "},{", text)
    # Strip trailing commas before closing braces
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # Extract from outermost { or [
    m = re.search(r"(\{|\[)[\s\S]*", text)
    if m:
        text = m.group(0).strip()
    # Repair unclosed array if LLM output was truncated near completion
    if text.startswith("[") and not text.endswith("]"):
        last_brace = text.rfind("}")
        if last_brace != -1:
            text = text[:last_brace + 1] + "]"
    elif text.startswith("{") and not text.endswith("}"):
        last_brace = text.rfind("}")
        if last_brace != -1:
            text = text[:last_brace + 1]
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
            res = _call_openai_compat(base_url, m_target, api_key or "lm-studio", test_prompt, allow_fallback=False, max_tokens=32)
            
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

def ask_llm(prompt: str, schema: dict = None, model: str = None, max_tokens: int = 1024, temperature: float = 0.65, system_prompt: str = None) -> dict | list:
    """Invokes LLM with fallback handling and returns parsed JSON response."""
    cfg = load_user_config()
    ai_cfg = cfg.get("ai", {})
    provider = (ai_cfg.get("provider") or AI_PROVIDER or "lmstudio").lower().strip()
    key = ai_cfg.get("api_key") or AI_KEY or ""
    if not key and provider in ("lmstudio", "custom", "ollama"):
        key = "lm-studio"
    base_url = (ai_cfg.get("base_url") or AI_BASE_URL or PROVIDERS.get(provider, "http://localhost:1235/v1")).rstrip("/")

    # Auto-resolve working endpoint and loaded model for local providers
    if provider in ("lmstudio", "custom", "ollama"):
        try:
            avail_models, working_url = fetch_models_with_url(provider, base_url, key)
            if working_url:
                base_url = working_url
            chat_models = [m for m in avail_models if "embed" not in m.lower()]
            if chat_models:
                cfg_model = model or ai_cfg.get("model")
                if not cfg_model or cfg_model not in chat_models:
                    model = chat_models[0]
        except Exception:
            pass

    models = [model] if model else ([ai_cfg.get("model")] if ai_cfg.get("model") else AI_MODELS)

    last_err = None
    for m in models:
        try:
            if provider == "gemini":
                return _call_gemini(m, key, prompt, temperature=temperature)
            elif provider == "anthropic":
                return _call_anthropic(m, key, prompt, max_tokens=max_tokens, temperature=temperature)
            else:
                # OpenAI-compatible protocol (LM Studio, Ollama, OpenAI, Groq, OpenRouter, Custom)
                return _call_openai_compat(base_url, m, key, prompt, max_tokens=max_tokens, temperature=temperature, system_prompt=system_prompt)
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"All AI providers failed: {explain_ai_error(last_err or Exception('connection failed'), provider)}")

def _call_gemini(model: str, key: str, prompt: str, temperature: float = 0.65):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": temperature}
    }
    with httpx.Client(timeout=45.0) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(_clean_json_text(raw))

def _call_openai_compat(base_url: str, model: str, key: str, prompt: str, allow_fallback: bool = True, max_tokens: int = 1024, temperature: float = 0.65, system_prompt: str = None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    sys_content = system_prompt or (
        "You are an elite short-form viral video editor AI specializing in YouTube Shorts, TikTok, and Instagram Reels. "
        "Your mission is to analyze transcripts, energy spikes, and hooks to discover high-retention, scroll-stopping clips with punchy viral titles. "
        "Reply strictly with valid JSON. Never output markdown, think tags, explanations or conversational text outside JSON."
    )
    messages = [
        {"role": "system", "content": sys_content},
        {"role": "user", "content": prompt}
    ]
    # For reasoning models (Qwen, DeepSeek-R1), add closed think tag to bypass long CoT generation
    if any(tag in (model or "").lower() for tag in ("qwen", "r1", "deepseek", "reason")):
        messages.append({"role": "assistant", "content": "</think>\n"})

    payload = {
        "model": model or "local-model",
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "presence_penalty": 0.1,
        "max_tokens": max_tokens
    }
    
    urls_to_attempt = [base_url]
    if allow_fallback and any(h in base_url for h in ("localhost", "127.0.0.1")):
        for alt in LOCAL_FALLBACK_URLS:
            if alt not in urls_to_attempt:
                urls_to_attempt.append(alt)
                
    last_ex = None
    for target in urls_to_attempt:
        try:
            with httpx.Client(timeout=httpx.Timeout(120.0, connect=2.0)) as client:
                target_model = payload["model"]
                # Auto-align target model if local provider has loaded models
                if allow_fallback and any(h in target for h in ("localhost", "127.0.0.1")):
                    try:
                        m_resp = client.get(f"{target}/models", timeout=httpx.Timeout(2.0, connect=0.8))
                        if m_resp.status_code == 200:
                            avail = [item["id"] for item in m_resp.json().get("data", []) if "id" in item and "embed" not in item["id"].lower()]
                            if avail and target_model not in avail:
                                target_model = avail[0]
                    except Exception:
                        pass

                req_payload = {**payload, "model": target_model}
                r = client.post(f"{target}/chat/completions", headers=headers, json=req_payload)
                r.raise_for_status()
                data = r.json()
                msg = data["choices"][0]["message"]
                raw = (msg.get("content") or "").strip()
                if not raw and msg.get("reasoning_content"):
                    raw = msg.get("reasoning_content", "").strip()
                cleaned = _clean_json_text(raw)
                return json.loads(cleaned)
        except (httpx.ConnectTimeout, httpx.ConnectError, httpx.NetworkError, httpx.RemoteProtocolError) as e:
            last_ex = e
            continue
        except Exception as e:
            last_ex = e
            # Only failover to another port on genuine connection refusals, never on ReadTimeout (which means server is busy generating)
            err_lower = str(e).lower()
            if any(term in err_lower for term in ("refused", "10061", "failed to establish", "connection refused")):
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
