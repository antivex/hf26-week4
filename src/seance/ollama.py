"""The only network call of the program: Ollama's HTTP API, ``POST /api/chat``, non-streaming."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "gemma4:e2b"
# Never route the request through a proxy from the environment: the library stays between you and your Ollama.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class OllamaError(RuntimeError):
    """Ollama could not be reached or refused the request."""


def normalize_host(host: str) -> str:
    host = host.strip().rstrip("/")
    return host if "://" in host else "http://" + host


def chat(host: str, model: str, messages: list[dict], *, num_predict: int = 200, temperature: float = 0.2,
         timeout: float = 600) -> str:
    """Send the conversation to the model and return the text of its reply."""
    body = {"model": model, "messages": messages, "stream": False, "think": False,
            "options": {"temperature": temperature, "num_predict": num_predict}}
    request = urllib.request.Request(normalize_host(host) + "/api/chat", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(detail).get("error", detail)
        except (ValueError, AttributeError):
            pass
        raise OllamaError(f"Ollama answered HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise OllamaError(f"cannot reach Ollama at {normalize_host(host)} ({reason}); is `ollama serve` running?") from e
    except ValueError as e:
        raise OllamaError(f"Ollama sent a reply that is not JSON ({e})") from e
    return ((data.get("message") or {}).get("content") or "").strip()
