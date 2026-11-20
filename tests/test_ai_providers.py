"""Exhaustive unit tests for AI providers, LM Studio gateway, JSON cleaning, and connection diagnostics."""
import unittest
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from clipiest.ai.providers import (
    _clean_json_text,
    test_llm_connection,
    fetch_models_from_provider,
    list_supported_providers,
    PROVIDERS
)

class TestAIProviders(unittest.TestCase):
    def test_clean_json_text_various_formats(self):
        # 1. Clean JSON
        raw1 = '{"status": "ok", "score": 95}'
        self.assertEqual(_clean_json_text(raw1), '{"status": "ok", "score": 95}')

        # 2. Markdown codeblock
        raw2 = """Here is the result:
```json
{
  "title": "Insane Clutch",
  "score": 88
}
```
Hope you like it!"""
        cleaned2 = _clean_json_text(raw2)
        self.assertIn('"title": "Insane Clutch"', cleaned2)
        self.assertNotIn("Here is the result", cleaned2)

        # 3. DeepSeek-R1 / Qwen reasoning <think> blocks common in LM Studio
        raw3 = """<think>
Let's analyze this gaming video transcript. The player killed 4 enemies in 5 seconds.
This is clearly a high-score clutch play. Score should be 90+.
</think>
```json
{
  "score": 92,
  "hook": "UNBELIEVABLE ACE"
}
```"""
        cleaned3 = _clean_json_text(raw3)
        self.assertNotIn("<think>", cleaned3)
        self.assertNotIn("Let's analyze", cleaned3)
        self.assertIn('"score": 92', cleaned3)

        # 4. JSON Array
        raw4 = """Output:
[{"id": 1}, {"id": 2}]
Done."""
        self.assertEqual(_clean_json_text(raw4), '[{"id": 1}, {"id": 2}]')

    def test_supported_providers_completeness(self):
        providers = list_supported_providers()
        self.assertIn("lmstudio", providers)
        self.assertIn("ollama", providers)
        self.assertIn("gemini", providers)
        self.assertIn("openai", providers)
        self.assertIn("anthropic", providers)
        self.assertIn("groq", providers)
        self.assertIn("openrouter", providers)
        self.assertIn("custom", providers)

    def test_connection_test_invalid_url(self):
        res = test_llm_connection("lmstudio", base_url="http://127.0.0.1:99999/invalid", api_key="", model="test")
        self.assertFalse(res["ok"])
        self.assertFalse(res["success"])
        self.assertIn("error", res)

    def test_fetch_models_fallback(self):
        # When connection fails, returns sensible defaults for that provider
        models = fetch_models_from_provider("lmstudio", base_url="http://127.0.0.1:99999")
        self.assertIsInstance(models, list)
        self.assertGreaterEqual(len(models), 1)

if __name__ == "__main__":
    unittest.main()
