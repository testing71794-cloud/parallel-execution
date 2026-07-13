# Vision API integration guide

The agent never hardcodes a single cloud vendor. Implement or select a `VisionProvider`.

## Interface

```python
class VisionProvider(ABC):
    def compare_images(self, baseline: Path, actual: Path) -> VisionResult: ...
    def verify_expected_ui(self, screenshot: Path, expectation: str) -> VisionResult: ...
    def detect_visual_difference(self, before: Path, after: Path) -> VisionResult: ...
```

## Select provider

```bat
set AI_AGENT_VISION_PROVIDER=null
set AI_AGENT_VISION_PROVIDER=openrouter
REM future: gemini | vertex | azure | claude | ollama
```

## Adding Gemini (example sketch)

1. Create `ai-agent/vision/gemini_provider.py` implementing `VisionProvider`.
2. Register in `get_vision_provider()`.
3. Pass API key via env (`GEMINI_API_KEY`) — never commit secrets.
4. Keep failures soft: vision errors must not crash the regression orchestrator.

## OpenRouter

Uses optional `intelligent_platform.openrouter_client` when present. If the client signature changes, the provider returns a soft failure and the run continues.
