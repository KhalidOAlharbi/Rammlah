import base64
import io
import logging
import re

from openai import OpenAI, OpenAIError
from PIL import Image, ImageOps, UnidentifiedImageError

from ..config import Settings
from ..schemas import VisionAnalysis

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
Inspect only the active surface of the visible solar panel.
Return exactly one class: Clean, Dust, or Crack.
Use this decision order:
1. Crack: visible glass damage, fractures, spider-web damage, circular impact damage, or broken photovoltaic cells. Crack has priority over Dust.
2. Dust: sand, dust, dirt, or particles visibly covering at least 25 percent of the active panel surface.
3. Clean: no crack and dust coverage is below 25 percent.
Do not classify background sand, room dust, panel frame dirt, minor specks, glare, reflections, shadows, scratches, grid lines, or busbars as Dust.
Do not classify grid lines, normal cell boundaries, reflections, or shadows as Crack.
If both dust and a crack are present, return Crack.
Do not return any additional classes.
Do not include markdown in the result.
If prediction is Clean or Crack, dust_coverage_percent should normally be 0.
If prediction is Dust, estimate the visible dust-coverage percentage from 25 to 100.
Keep reason short and suitable for display on a dashboard.
""".strip()


CRACK_TERMS = re.compile(
    r"\b(crack(?:ed|s)?|fracture(?:d|s)?|spider[- ]?web|broken|shatter(?:ed|s)?|impact damage|glass damage)\b",
    re.IGNORECASE,
)

CRACK_NEGATIONS = (
    "no crack",
    "no visible crack",
    "without crack",
    "no fracture",
    "no visible fracture",
    "without fracture",
    "no glass damage",
    "without glass damage",
    "no broken",
    "not cracked",
)


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
            parsed = self._normalize_analysis(parsed)
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

    def _normalize_analysis(self, analysis: VisionAnalysis) -> VisionAnalysis:
        reason = analysis.reason.lower()

        if analysis.prediction == "Dust" and CRACK_TERMS.search(reason) and not any(
            phrase in reason for phrase in CRACK_NEGATIONS
        ):
            return analysis.model_copy(
                update={
                    "prediction": "Crack",
                    "dust_coverage_percent": 0.0,
                    "reason": "Visible crack damage has priority over dust.",
                }
            )

        if analysis.prediction == "Dust" and analysis.dust_coverage_percent < 25:
            return analysis.model_copy(
                update={
                    "prediction": "Clean",
                    "reason": "Dust coverage is below 25 percent. Panel is treated as clean.",
                }
            )

        if analysis.prediction == "Crack" and analysis.dust_coverage_percent != 0:
            return analysis.model_copy(update={"dust_coverage_percent": 0.0})

        return analysis
