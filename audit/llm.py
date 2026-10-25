"""Groq client: cached and token-counted. Used ONLY for unstructured evidence (images, scanned PDFs)
and ambiguous request text. All audit decisions stay deterministic."""
import os, json, time, hashlib, base64, requests
from pathlib import Path

URL = "https://api.groq.com/openai/v1/chat/completions"
# USD per 1M tokens (input, output). Estimates - verify at https://groq.com/pricing
PRICES = {
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "meta-llama/llama-4-scout-17b-16e-instruct": (0.11, 0.34),
}


class Groq:
    def __init__(self, api_key=None, model="llama-3.3-70b-versatile",
                 vision_model="meta-llama/llama-4-scout-17b-16e-instruct", cache_dir=".cache"):
        self.key = api_key or os.getenv("GROQ_API_KEY")
        self.model, self.vision_model = model, vision_model
        self.calls = []
        self.path = Path(cache_dir) / "groq_cache.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.cache = json.loads(self.path.read_text())
        except Exception:
            self.cache = {}

    @property
    def enabled(self):
        return bool(self.key)

    def _post(self, payload):
        for i in range(6):
            r = requests.post(URL, json=payload, timeout=120,
                              headers={"Authorization": f"Bearer {self.key}"})
            if r.status_code == 429:
                time.sleep(2 ** i + 1)
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("Groq rate limit - retry later")

    def chat(self, messages, model=None, case_id="", json_mode=False, max_tokens=700):
        if not self.enabled:
            return ""
        model = model or self.model
        key = hashlib.sha256(json.dumps([model, messages, json_mode]).encode()).hexdigest()
        hit = self.cache.get(key)
        if hit:
            self.calls.append(dict(model=model, inp=hit["in"], out=hit["out"], case_id=case_id, cached=True))
            return hit["text"]
        payload = {"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        d = self._post(payload)
        text = d["choices"][0]["message"]["content"]
        u = d.get("usage", {})
        rec = {"text": text, "in": u.get("prompt_tokens", 0), "out": u.get("completion_tokens", 0)}
        self.cache[key] = rec
        self.path.write_text(json.dumps(self.cache))
        self.calls.append(dict(model=model, inp=rec["in"], out=rec["out"], case_id=case_id, cached=False))
        return text

    def describe_image(self, path, case_id=""):
        p = Path(path)
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(
            p.suffix.lstrip(".").lower(), "image/png")
        b64 = base64.b64encode(p.read_bytes()).decode()
        msg = [{"role": "user", "content": [
            {"type": "text", "text": "Transcribe ALL visible text exactly (names, emails, phones, ids, "
                                     "dates, table cells). Output plain text only, one record per line."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]}]
        return self.chat(msg, model=self.vision_model, case_id=case_id, max_tokens=1200)
