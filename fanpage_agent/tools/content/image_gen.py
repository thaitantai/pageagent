"""Image generation service — mock and OpenAI-compatible providers.

Supports three modes (via Settings.img_provider):
  mock   → Pillow placeholder with visual_brief as overlay text
  openai → OpenAI-compatible image API (DALL-E, etc.)
  url    → download an image from a pre-existing URL (for testing / manual)
"""

from __future__ import annotations

import json
import os
import re
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

import requests

from fanpage_agent.config import Settings

# ---------------------------------------------------------------------------
#  Interface
# ---------------------------------------------------------------------------


class ImageTool(ABC):
    """Generate an image from a text brief, returning a local file path."""

    @abstractmethod
    def generate(self, prompt: str, output_dir: str | Path | None = None) -> str: ...


# ---------------------------------------------------------------------------
#  Mock — Pillow placeholder
# ---------------------------------------------------------------------------


class MockImageTool(ImageTool):
    """Creates a fashion-branded colour-block placeholder image.

    Uses Outfit Nhà Gấu brand palette (soft pastels, warm tones)
    with decorative bands for a more polished look.
    Requires Pillow (PIL).
    """

    WIDTH = 1024
    HEIGHT = 1024

    # Outfit Nhà Gấu brand palette
    PALETTES = [
        {  # Hồng pastel
            "bg": (255, 228, 235),
            "accent": (255, 182, 193),
            "text": (180, 80, 100),
            "band": (255, 200, 210),
        },
        {  # Beige/cream
            "bg": (250, 245, 235),
            "accent": (220, 200, 170),
            "text": (140, 110, 80),
            "band": (235, 220, 195),
        },
        {  # Lavender nhẹ
            "bg": (240, 235, 250),
            "accent": (200, 180, 230),
            "text": (120, 90, 160),
            "band": (215, 200, 240),
        },
        {  # Mint nhẹ
            "bg": (230, 248, 240),
            "accent": (170, 215, 190),
            "text": (80, 140, 110),
            "band": (200, 230, 210),
        },
        {  # Peach
            "bg": (255, 240, 230),
            "accent": (250, 200, 170),
            "text": (170, 110, 70),
            "band": (250, 215, 190),
        },
    ]

    def __init__(self, output_dir: str | Path | None = None) -> None:
        self.default_output_dir = Path(output_dir or "artifacts/images")
        self._palette_idx = 0

    def _next_palette(self) -> dict:
        p = self.PALETTES[self._palette_idx % len(self.PALETTES)]
        self._palette_idx += 1
        return p

    def generate(self, prompt: str, output_dir: str | Path | None = None) -> str:
        from PIL import Image, ImageDraw

        out_dir = Path(output_dir or self.default_output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        palette = self._next_palette()
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), palette["bg"])
        draw = ImageDraw.Draw(img)

        # ── Top decorative band ──
        band_h = 60
        draw.rectangle([(0, 0), (self.WIDTH, band_h)], fill=palette["band"])
        # Thin accent line below band
        draw.rectangle([(0, band_h), (self.WIDTH, band_h + 4)], fill=palette["accent"])

        # ── Bottom decorative band ──
        draw.rectangle([(0, self.HEIGHT - band_h), (self.WIDTH, self.HEIGHT)], fill=palette["band"])
        draw.rectangle(
            [(0, self.HEIGHT - band_h - 4), (self.WIDTH, self.HEIGHT - band_h)],
            fill=palette["accent"],
        )

        # ── Side accent stripe ──
        stripe_w = 16
        draw.rectangle(
            [(stripe_w, band_h + 4), (stripe_w + 6, self.HEIGHT - band_h - 4)],
            fill=palette["accent"],
        )

        # ── Brand name in band ──
        brand_font = self._find_font(size=22)
        draw.text(
            (stripe_w + 20, 16),
            "Outfit Nhà Gấu · MOCK",
            fill=palette["text"],
            font=brand_font,
        )

        # ── Center content area ──
        content_top = band_h + 80
        content_bottom = self.HEIGHT - band_h - 80

        # Subtitle line
        sub_font = self._find_font(size=20)
        subtitle = "📸 Ảnh minh hoạ (mock — chưa có ảnh thật)"
        sub_bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
        draw.text(
            ((self.WIDTH - (sub_bbox[2] - sub_bbox[0])) // 2, content_top),
            subtitle,
            fill=palette["text"],
            font=sub_font,
        )

        # Main prompt text (wrapped)
        font = self._find_font(size=30)
        margin = 80
        max_w = self.WIDTH - 2 * margin
        lines = self._wrap_text(draw, prompt or "(no brief)", font, max_w)
        y_start = (content_top + content_bottom) // 2 - (len(lines) * 42) // 2
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            x = (self.WIDTH - (bbox[2] - bbox[0])) // 2
            draw.text((x, y_start + i * 42), line, fill=palette["text"], font=font)

        # ── Decorative circles (fashion vibe) ──
        # Small circles in the corners
        draw.ellipse(
            [(40, content_top + 30), (70, content_top + 60)], fill=palette["accent"], outline=None
        )
        draw.ellipse(
            [(self.WIDTH - 90, content_bottom - 50), (self.WIDTH - 60, content_bottom - 20)],
            fill=palette["accent"],
            outline=None,
        )

        slug = re.sub(r"[^a-z0-9]+", "_", prompt.lower()[:40]).strip("_") or "untitled"
        filename = f"{slug}_{uuid.uuid4().hex[:8]}.png"
        filepath = out_dir / filename
        img.save(filepath, "PNG")
        return str(filepath.resolve())

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_font(size: int = 24):
        from PIL import ImageFont

        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
        ]
        for path in candidates:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()

    @staticmethod
    def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current = ""
        for w in words:
            test = f"{current} {w}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if (bbox[2] - bbox[0]) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        return lines if lines else [text]


# ---------------------------------------------------------------------------
#  OpenAI-compatible (DALL-E, etc.)
# ---------------------------------------------------------------------------


class OpenAIImageTool(ImageTool):
    """Generate images via an OpenAI-compatible image API.

    Calls ``POST /v1/images/generations`` with the prompt, then
    downloads the resulting URL to a local file.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "dall-e-3",
        base_url: str = "https://api.openai.com/v1",
        output_dir: str | Path | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.default_output_dir = Path(output_dir or "artifacts/images")

    def generate(self, prompt: str, output_dir: str | Path | None = None) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
        }

        resp = requests.post(
            f"{self.base_url}/images/generations",
            headers=headers,
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        image_url = data.get("data", [{}])[0].get("url", "")
        if not image_url:
            raise RuntimeError(f"OpenAI image API returned no url: {json.dumps(data)[:300]}")

        return self._download(image_url, output_dir)

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    def _download(self, url: str, output_dir: str | Path | None = None) -> str:
        out_dir = Path(output_dir or self.default_output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        resp = requests.get(url, timeout=120)
        resp.raise_for_status()

        ext = ".png"
        if "content-type" in resp.headers:
            ct = resp.headers["content-type"]
            if "jpeg" in ct or "jpg" in ct:
                ext = ".jpg"
            elif "webp" in ct:
                ext = ".webp"

        filename = f"gen_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}{ext}"
        filepath = out_dir / filename
        filepath.write_bytes(resp.content)
        return str(filepath.resolve())


# ---------------------------------------------------------------------------
#  URL-based — download an image from a pre-existing URL
# ---------------------------------------------------------------------------


class UrlImageTool(ImageTool):
    """Download an image from a pre-existing URL (no generation).

    Useful for testing or when using an external tool to create the image.
    """

    def __init__(self, output_dir: str | Path | None = None) -> None:
        self.default_output_dir = Path(output_dir or "artifacts/images")

    def generate(self, prompt: str, output_dir: str | Path | None = None) -> str:
        # prompt IS the URL for this provider
        url = prompt.strip()
        if not url.startswith("http"):
            raise ValueError(f"UrlImageTool requires a valid HTTP(S) URL, got: {prompt[:100]}")

        out_dir = Path(output_dir or self.default_output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        resp = requests.get(url, timeout=120)
        resp.raise_for_status()

        ext = ".png"
        if "content-type" in resp.headers:
            ct = resp.headers["content-type"]
            if "jpeg" in ct or "jpg" in ct:
                ext = ".jpg"
            elif "webp" in ct:
                ext = ".webp"

        filename = f"url_{uuid.uuid4().hex[:8]}{ext}"
        filepath = out_dir / filename
        filepath.write_bytes(resp.content)
        return str(filepath.resolve())


# ---------------------------------------------------------------------------
#  Factory
# ---------------------------------------------------------------------------


def build_image_service(settings: Settings) -> ImageTool:
    """Create an ImageTool from application Settings."""
    provider = settings.img_provider.lower()
    out = settings.artifacts_dir / "images"

    if provider == "mock":
        return MockImageTool(output_dir=out)
    if provider == "openai":
        return OpenAIImageTool(
            api_key=settings.img_api_key,
            model=settings.img_model,
            base_url=settings.img_base_url or "https://api.openai.com/v1",
            output_dir=out,
        )
    if provider == "url":
        return UrlImageTool(output_dir=out)

    raise ValueError(f"Unknown img_provider: {provider!r}. Expected: mock, openai, url")
