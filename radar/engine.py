"""LLM engines.

The daily analysis needs a capable model. Which one is a cost decision, not an
architectural one, so all engines expose the same `run(system, user) -> str` and
are chosen by name in config.yaml.

  claude_cli    Claude Code CLI in headless mode. Uses your existing Claude
                subscription, so there is no per-run charge.
                Install: npm install -g @anthropic-ai/claude-code
  gemini_cli    Google's Gemini CLI (already installed on this machine). Has a
                free tier. Good fallback.
  anthropic_api Direct API. Most reliable and scriptable, but billed per token.
                Needs ANTHROPIC_API_KEY.

Prompts are passed on stdin, never as a command-line argument: a full day of
headlines is far past the ~8 KB Windows command-line limit.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


class EngineError(RuntimeError):
    pass


class Engine:
    name = "base"

    def available(self) -> bool:
        raise NotImplementedError

    def run(self, system: str, user: str) -> str:
        raise NotImplementedError


def _which(*names: str) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


class ClaudeCLIEngine(Engine):
    """Headless Claude Code. Free with a Claude subscription."""
    name = "claude_cli"

    def __init__(self, model: str = "claude-sonnet-5", timeout: int = 900):
        self.model = model
        self.timeout = timeout
        self.exe = _which("claude", "claude.cmd", "claude.exe")

    def available(self) -> bool:
        return self.exe is not None

    def run(self, system: str, user: str) -> str:
        if not self.exe:
            raise EngineError(
                "claude CLI not found. Install with:\n"
                "    npm install -g @anthropic-ai/claude-code\n"
                "then run `claude` once to log in.")

        # The analyst prompt is far too big to pass as an argument: `claude` is
        # a .cmd shim on Windows, so it goes through cmd.exe, which refuses any
        # command line over 8191 characters. Hand it over as a file instead.
        # `--system-prompt` (rather than `--append-`) replaces Claude Code's
        # own coding-agent prompt, which is only noise for this task.
        tmp = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                          encoding="utf8")
        try:
            tmp.write(system)
            tmp.close()
            cmd = [self.exe, "-p", "--output-format", "text",
                   "--model", self.model,
                   "--system-prompt-file", tmp.name]
            proc = subprocess.run(cmd, input=user, capture_output=True,
                                  text=True, encoding="utf8", errors="replace",
                                  timeout=self.timeout, shell=False)
        finally:
            os.unlink(tmp.name)

        if proc.returncode != 0:
            raise EngineError(f"claude CLI failed ({proc.returncode}): "
                              f"{(proc.stderr or '')[:500]}")
        return proc.stdout


class GeminiCLIEngine(Engine):
    """Google Gemini CLI. Free tier available."""
    name = "gemini_cli"

    def __init__(self, model: str = "gemini-2.5-pro", timeout: int = 900):
        self.model = model
        self.timeout = timeout
        self.exe = _which("gemini", "gemini.cmd")

    def available(self) -> bool:
        return self.exe is not None

    def run(self, system: str, user: str) -> str:
        if not self.exe:
            raise EngineError("gemini CLI not found. Install: npm install -g @google/gemini-cli")
        # Gemini CLI has no separate system-prompt flag; prepend it instead.
        payload = f"{system}\n\n---\n\n{user}"
        proc = subprocess.run([self.exe, "-m", self.model, "-p", "-"],
                              input=payload, capture_output=True, text=True,
                              encoding="utf8", errors="replace",
                              timeout=self.timeout, shell=False)
        if proc.returncode != 0:
            raise EngineError(f"gemini CLI failed ({proc.returncode}): "
                              f"{(proc.stderr or '')[:500]}")
        return proc.stdout


class AnthropicAPIEngine(Engine):
    """Direct Claude API. Billed per token."""
    name = "anthropic_api"

    def __init__(self, model: str = "claude-sonnet-5", max_tokens: int = 8000):
        self.model = model
        self.max_tokens = max_tokens

    def available(self) -> bool:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False

    def run(self, system: str, user: str) -> str:
        try:
            import anthropic
        except ImportError as e:
            raise EngineError("pip install anthropic") from e
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise EngineError("ANTHROPIC_API_KEY is not set")
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


class GeminiAPIEngine(Engine):
    """Google's Gemini over plain HTTPS, using a free API key.

    This is the engine the cloud runner uses. The Gemini CLI needs an
    interactive browser login, which a server cannot do; an API key from
    aistudio.google.com is free, has a daily quota comfortably larger than one
    run, and is just an HTTP header.
    """
    name = "gemini_api"
    ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
                "{model}:generateContent")

    def __init__(self, model: str = "gemini-2.0-flash", timeout: int = 900):
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        return bool(os.environ.get("GEMINI_API_KEY"))

    def run(self, system: str, user: str) -> str:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise EngineError(
                "GEMINI_API_KEY is not set. Get a free key at "
                "https://aistudio.google.com/apikey")
        import requests

        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 16000,
                # The analyst prompt demands JSON; asking for it at the API
                # level stops the model wrapping the object in prose.
                "responseMimeType": "application/json",
            },
        }
        r = requests.post(self.ENDPOINT.format(model=self.model),
                          headers={"x-goog-api-key": key},
                          json=body, timeout=self.timeout)
        if r.status_code == 429:
            raise EngineError("Gemini free-tier quota exhausted for now — "
                              "the next scheduled run should succeed.")
        if not r.ok:
            raise EngineError(f"Gemini API {r.status_code}: {r.text[:400]}")

        data = r.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as e:
            fb = data.get("promptFeedback") or data
            raise EngineError(f"Gemini returned no candidates: {str(fb)[:300]}") from e
        return "".join(p.get("text", "") for p in parts)


class FileEngine(Engine):
    """Read the analysis from a file instead of calling a model.

    Two uses: testing the rest of the pipeline without spending tokens, and
    writing a day's brief by hand when you want to do the analysis yourself.
    Point FINRADAR_RESPONSE_FILE at a file containing the JSON response.
    """
    name = "file"

    def __init__(self, model: str | None = None):
        self.path = os.environ.get("FINRADAR_RESPONSE_FILE", "")

    def available(self) -> bool:
        return bool(self.path) and Path(self.path).exists()

    def run(self, system: str, user: str) -> str:
        if not self.available():
            raise EngineError(
                "FINRADAR_RESPONSE_FILE is not set or the file does not exist")
        return Path(self.path).read_text(encoding="utf8")


ENGINES = {
    "claude_cli": ClaudeCLIEngine,
    "gemini_cli": GeminiCLIEngine,
    "gemini_api": GeminiAPIEngine,
    "anthropic_api": AnthropicAPIEngine,
    "file": FileEngine,
}


def build_engine(name: str, model: str | None = None) -> Engine:
    """Build a named engine, or auto-pick the first available one."""
    if name == "auto":
        # Order matters: best quality first, free-and-serverless last. On the
        # cloud runner only gemini_api will be available, so it wins there
        # without needing a different command line.
        for key in ("claude_cli", "anthropic_api", "gemini_cli", "gemini_api"):
            eng = ENGINES[key](**({"model": model} if model else {}))
            if eng.available():
                return eng
        raise EngineError(
            "No LLM engine available. Pick one:\n"
            "  1) npm install -g @anthropic-ai/claude-code   (free with your Claude plan)\n"
            "  2) set ANTHROPIC_API_KEY                       (pay per use)\n"
            "  3) npm install -g @google/gemini-cli           (free tier)")
    if name not in ENGINES:
        raise EngineError(f"Unknown engine '{name}'. Options: {', '.join(ENGINES)}, auto")
    return ENGINES[name](**({"model": model} if model else {}))


def extract_json(text: str) -> dict:
    """Pull the JSON object out of a model response, tolerating prose and fences."""
    if not text or not text.strip():
        raise EngineError("engine returned an empty response")

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = [fenced.group(1)] if fenced else []

    # Otherwise take the outermost balanced {...} block.
    start = text.find("{")
    if start != -1:
        depth, in_str, esc = 0, False, False
        for i, ch in enumerate(text[start:], start):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:i + 1])
                    break

    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            # Models occasionally leave trailing commas.
            try:
                return json.loads(re.sub(r",\s*([}\]])", r"\1", cand))
            except json.JSONDecodeError:
                continue

    raise EngineError(f"could not parse JSON from response. First 400 chars:\n{text[:400]}")
