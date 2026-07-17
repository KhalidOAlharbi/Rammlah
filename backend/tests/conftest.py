import io
import sys
from pathlib import Path

import pytest
from PIL import Image

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture
def image_bytes() -> bytes:
    image = Image.new("RGB", (64, 64), color=(230, 230, 220))
    output = io.BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()
