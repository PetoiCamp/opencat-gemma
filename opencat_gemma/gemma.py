"""Ask a local Gemma (through Ollama) to turn a request into robot commands."""
import json
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma4:e2b-it-qat"


def ask(contract, text, model=MODEL, url=OLLAMA_URL, timeout=180):
    """Return Gemma's raw reply. think=False matters: with thinking on, replies took 6-20 s instead of ~1 s."""
    body = json.dumps({
        "model": model, "stream": False, "think": False, "format": contract.schema,
        "options": {"temperature": 0},
        "messages": [{"role": "system", "content": contract.prompt}, {"role": "user", "content": text}],
    }).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Ollama error {e.code}: {e.read().decode(errors='replace')}. "
                           f"Is the model pulled? Run: ollama pull {model}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Can't reach Ollama at {url}. Is it running? Start it with: ollama serve") from e


def parse(contract, out):
    """Return (commands, error). Never trust model output: other runtimes may not enforce the schema."""
    try:
        v = json.loads(out)
    except json.JSONDecodeError:
        return None, "invalid JSON"
    if isinstance(v, dict):
        v = next((x for x in v.values() if isinstance(x, list)), None)
    if not isinstance(v, list):
        return None, "not a list"
    bad = contract.validate(v)
    if bad:
        return None, f"not allowed: {bad}"
    return v, None
