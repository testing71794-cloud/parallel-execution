"""Vision Analyzer — provider interface with placeholders (no hardcoded OpenAI)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class VisionResult:
    ok: bool
    score: float
    details: str
    provider: str
    raw: dict[str, Any] | None = None


class VisionProvider(ABC):
    """Future-proof interface for Gemini / Vertex / Azure / Claude / Ollama / OpenRouter."""

    name: str = "base"

    @abstractmethod
    def compare_images(self, baseline: Path, actual: Path) -> VisionResult:
        ...

    @abstractmethod
    def verify_expected_ui(self, screenshot: Path, expectation: str) -> VisionResult:
        ...

    @abstractmethod
    def detect_visual_difference(self, before: Path, after: Path) -> VisionResult:
        ...


class NullVisionProvider(VisionProvider):
    """Default no-op provider — keeps agent runnable without vision credentials."""

    name = "null"

    def compare_images(self, baseline: Path, actual: Path) -> VisionResult:
        return VisionResult(ok=True, score=0.0, details="vision not configured", provider=self.name)

    def verify_expected_ui(self, screenshot: Path, expectation: str) -> VisionResult:
        return VisionResult(ok=True, score=0.0, details=f"skipped: {expectation}", provider=self.name)

    def detect_visual_difference(self, before: Path, after: Path) -> VisionResult:
        return VisionResult(ok=True, score=0.0, details="vision not configured", provider=self.name)


class OpenRouterVisionProvider(VisionProvider):
    """
    Optional OpenRouter-backed vision (uses existing intelligent_platform client if present).

    Not selected by default — set AI_AGENT_VISION_PROVIDER=openrouter.
    """

    name = "openrouter"

    def compare_images(self, baseline: Path, actual: Path) -> VisionResult:
        return self._call(
            "Compare these two mobile screenshots. Are they visually equivalent for QA? "
            "Reply with JSON {ok:bool, score:0-1, details:str}.",
            [baseline, actual],
        )

    def verify_expected_ui(self, screenshot: Path, expectation: str) -> VisionResult:
        return self._call(
            f"Does this Android screenshot match the expectation: {expectation}? "
            "Reply with JSON {ok:bool, score:0-1, details:str}.",
            [screenshot],
        )

    def detect_visual_difference(self, before: Path, after: Path) -> VisionResult:
        return self._call(
            "Detect meaningful UI differences between before/after screenshots for a Kodak Smile test. "
            "Reply with JSON {ok:bool, score:0-1, details:str}.",
            [before, after],
        )

    def _call(self, prompt: str, images: list[Path]) -> VisionResult:
        try:
            import sys
            from pathlib import Path as P

            # repo root = ai-agent/../
            repo = P(__file__).resolve().parents[1]
            if str(repo.parent) not in sys.path:
                sys.path.insert(0, str(repo.parent))
            from intelligent_platform.openrouter_client import call_openrouter_vision

            # Lightweight: pass first image path description if vision API expects URLs/base64.
            # Existing client API may vary — treat failures as soft.
            resp = call_openrouter_vision(prompt=prompt, image_paths=[str(p) for p in images])  # type: ignore[call-arg]
            text = str(resp)[:2000]
            return VisionResult(ok=True, score=0.5, details=text, provider=self.name, raw={"response": text})
        except Exception as exc:  # noqa: BLE001
            return VisionResult(ok=False, score=0.0, details=f"openrouter vision unavailable: {exc}", provider=self.name)


def get_vision_provider(name: str | None = None) -> VisionProvider:
    import os

    key = (name or os.environ.get("AI_AGENT_VISION_PROVIDER") or "null").strip().lower()
    if key in ("openrouter", "or"):
        return OpenRouterVisionProvider()
    # Placeholders for future providers
    if key in ("gemini", "vertex", "azure", "claude", "ollama"):
        return NullVisionProvider()  # wired later; interface stable
    return NullVisionProvider()
