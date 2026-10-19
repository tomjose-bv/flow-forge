"""Chat clients: Ollama on localhost, and a scripted fake for tests."""

from __future__ import annotations

import json
import re
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

DEFAULT_MODEL = "qwen2.5-coder:3b"


@dataclass
class Usage:
    prompt_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    seconds: float = 0.0

    def add(self, prompt: int, output: int, seconds: float) -> None:
        self.prompt_tokens += prompt
        self.output_tokens += output
        self.calls += 1
        self.seconds += seconds


class LLM(Protocol):
    usage: Usage

    def chat(self, messages: list[dict[str, str]]) -> str: ...


@dataclass
class OllamaClient:
    model: str = DEFAULT_MODEL
    host: str = "http://127.0.0.1:11434"
    temperature: float = 0.2
    seed: int | None = None
    num_ctx: int = 8192
    num_predict: int = 2048  # cap reply length so a runaway generation stops
    timeout: float = 300.0
    usage: Usage = field(default_factory=Usage)

    def chat(self, messages: list[dict[str, str]]) -> str:
        options = {"temperature": self.temperature, "num_ctx": self.num_ctx, "num_predict": self.num_predict}
        if self.seed is not None:
            options["seed"] = self.seed
        body = json.dumps({"model": self.model, "messages": messages, "stream": False, "options": options}).encode()
        req = urllib.request.Request(
            f"{self.host}/api/chat", data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        started = time.monotonic()
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.loads(r.read())
        self.usage.add(out.get("prompt_eval_count", 0), out.get("eval_count", 0), time.monotonic() - started)
        return out["message"]["content"]


@dataclass
class FakeLLM:
    """Returns scripted replies in order; records the messages it was sent."""

    replies: list[str]
    usage: Usage = field(default_factory=Usage)
    seen: list[list[dict[str, str]]] = field(default_factory=list)

    def chat(self, messages: list[dict[str, str]]) -> str:
        self.seen.append([dict(m) for m in messages])
        if not self.replies:
            raise RuntimeError("FakeLLM ran out of replies")
        reply = self.replies.pop(0)
        self.usage.add(sum(len(m["content"]) // 4 for m in messages), len(reply) // 4, 0.0)
        return reply


_FENCE = re.compile(r"```(?:ya?ml)?[ \t]*\n(.*?)```", re.DOTALL)


def extract_recipe(text: str) -> str | None:
    """Return the longest fenced YAML block in a reply, or the reply itself if it looks like a recipe."""
    blocks = _FENCE.findall(text)
    if blocks:
        return max(blocks, key=len).strip() + "\n"
    if "trigger:" in text and "steps:" in text:
        return text.strip() + "\n"
    return None
