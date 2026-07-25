"""Model backends for the diagnostic pipeline.

Same retrieval, same grounding rules, same validation — only the "brain"
differs (brief §4: the data layer is identical across deployment modes).

- claude:  Anthropic API (frontier reasoning; needs connectivity + key)
- ollama:  local model via Ollama (offline laptop mode)

Both take (system, messages) and return (text, meta). `on_text` receives
incremental chunks when streaming is supported.
"""

import json
import os
import time
import urllib.request

from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def get_config() -> dict:
    """User settings (provider/model). Reread each call so the Settings
    page takes effect without restarts. Falls back to sane defaults."""
    defaults = {
        "backend": "claude",
        "claude_model": "claude-opus-5",
        "ollama_url": os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
        "ollama_model": os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
    }
    try:
        defaults.update(json.loads(_CONFIG_PATH.read_text(encoding="utf-8")))
    except Exception:
        pass
    return defaults


_cfg = get_config()
OLLAMA_URL = _cfg["ollama_url"]
OLLAMA_MODEL = _cfg["ollama_model"]
CLAUDE_MODEL = _cfg["claude_model"]


def claude_chat(system: str, messages: list[dict], max_tokens: int = 8000,
                on_text=None) -> tuple[str, dict]:
    import anthropic
    client = anthropic.Anthropic()
    model = get_config()["claude_model"]
    t0 = time.monotonic()
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        system=[{"type": "text", "text": system,
                 "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            if on_text:
                on_text(text)
        response = stream.get_final_message()
    text = "".join(b.text for b in response.content if b.type == "text")
    return text, {
        "backend": f"claude ({model})",
        "seconds": round(time.monotonic() - t0, 1),
        "output_tokens": response.usage.output_tokens,
        "stop_reason": response.stop_reason,
    }


def ollama_chat(system: str, messages: list[dict], model: str = None,
                on_text=None) -> tuple[str, dict]:
    model = model or get_config()["ollama_model"]
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}]
                    + [{"role": m["role"], "content": m["content"]}
                       for m in messages],
        "stream": True,
        "options": {"num_ctx": 16384, "temperature": 0.2},
    }
    req = urllib.request.Request(
        OLLAMA_URL + "/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    chunks, eval_count = [], 0
    with urllib.request.urlopen(req, timeout=1800) as resp:
        for line in resp:
            if not line.strip():
                continue
            obj = json.loads(line)
            piece = obj.get("message", {}).get("content", "")
            if piece:
                chunks.append(piece)
                if on_text:
                    on_text(piece)
            if obj.get("done"):
                eval_count = obj.get("eval_count", 0)
    return "".join(chunks), {
        "backend": f"ollama ({model})",
        "seconds": round(time.monotonic() - t0, 1),
        "output_tokens": eval_count,
        "stop_reason": "end_turn",
    }


def ollama_stream(system: str, messages: list[dict], model: str = None):
    """Generator yielding text chunks (for HTTP streaming responses)."""
    model = model or get_config()["ollama_model"]
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}]
                    + [{"role": m["role"], "content": m["content"]}
                       for m in messages],
        "stream": True,
        "options": {"num_ctx": 16384, "temperature": 0.2},
    }
    req = urllib.request.Request(
        OLLAMA_URL + "/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=1800) as resp:
        for line in resp:
            if not line.strip():
                continue
            obj = json.loads(line)
            piece = obj.get("message", {}).get("content", "")
            if piece:
                yield piece


def chat(backend: str, system: str, messages: list[dict], on_text=None,
         model: str = None) -> tuple[str, dict]:
    if backend == "ollama":
        return ollama_chat(system, messages, model=model, on_text=on_text)
    return claude_chat(system, messages, on_text=on_text)


def ollama_available() -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=3) as r:
            return bool(json.loads(r.read()).get("models"))
    except Exception:
        return False
