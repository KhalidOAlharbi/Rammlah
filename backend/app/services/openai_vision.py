import base64
import io
import logging

from openai import OpenAI, OpenAIError
from PIL import Image, ImageOps, UnidentifiedImageError

from ..config import Settings
from ..schemas import VisionAnalysis

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
Inspect only the visible solar panel.
Classify the panel as exactly Clean, Dust, or Crack.
Crack means visible glass damage, fractures, spider-web damage, circular impact damage, or broken photovoltaic cells.
Dust means visible sand, dust, dirt, or particles on the panel surface.
Clean means no meaningful visible dust and no visible crack.
Crack has higher priority than Dust.
If both dust and a crack are present, return Crack.
Do not return any additional classes.
Do not include markdown in the result.
If prediction is Clean or Crack, dust_coverage_percent should normally be 0.
If prediction is Dust, estimate the visible dust-coverage percentage from 0 to 100.
Keep reason short and suitable for display on a dashboard.
""".strip()


class OpenAIVisionError(RuntimeError):
    pass


class InvalidImageError(ValueError):
    pass


class OpenAIVisionService:
    def __init__(self, settings: Settings, client: OpenAI | None = None):
        self.settings = settings
        self.client = client or OpenAI(
            api_key=settings.openai_api_key_value,
            timeout=settings.openai_timeout_seconds,
        )

    def analyze_image(self, image_bytes: bytes) -> VisionAnalysis:
        logger.info("OpenAI vision request started")
        data_url = self._image_bytes_to_data_url(image_bytes)
        try:
            response = self.client.responses.parse(
                model=self.settings.openai_model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "Classify this solar panel image and return the required structured result.",
                            },
                            {"type": "input_image", "image_url": data_url},
                        ],
                    },
                ],
                text_format=VisionAnalysis,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise OpenAIVisionError("OpenAI returned no structured output.")
            logger.info(
                "OpenAI classification completed: prediction=%s confidence=%.3f dust=%.1f",
                parsed.prediction,
                parsed.confidence,
                parsed.dust_coverage_percent,
            )
            return parsed
        except OpenAIError as exc:
            logger.exception("OpenAI request failed")
            raise OpenAIVisionError(f"OpenAI analysis failed: {exc}") from exc
        except Exception as exc:
            logger.exception("OpenAI structured parsing failed")
            raise OpenAIVisionError(f"OpenAI analysis failed: {exc}") from exc

    def _image_bytes_to_data_url(self, image_bytes: bytes) -> str:
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.verify()
            with Image.open(io.BytesIO(image_bytes)) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail(
                    (self.settings.max_image_dimension, self.settings.max_image_dimension),
                    Image.Resampling.LANCZOS,
                )
                if image.mode not in ("RGB", "L"):
                    background = Image.new("RGB", image.size, (255, 255, 255))
                    if "A" in image.getbands():
                        background.paste(image, mask=image.getchannel("A"))
                        image = background
                    else:
                        image = image.convert("RGB")
                elif image.mode == "L":
                    image = image.convert("RGB")
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=88, optimize=True)
        except (UnidentifiedImageError, OSError) as exc:
            raise InvalidImageError("Invalid image. Upload a JPG, PNG, or WEBP file.") from exc

        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"
