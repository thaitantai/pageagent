from __future__ import annotations

import json
from pathlib import Path

from fanpage_agent.models import BrandProfile


def load_brand_profile(path: str | Path) -> BrandProfile:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return BrandProfile.model_validate(data)
