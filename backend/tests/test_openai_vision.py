from app.config import Settings
from app.schemas import VisionAnalysis
from app.services.openai_vision import OpenAIVisionService


def make_service() -> OpenAIVisionService:
    return OpenAIVisionService(Settings(OPENAI_API_KEY="test-key"), client=object())


def test_dust_prediction_below_threshold_is_normalized_to_clean():
    service = make_service()
    result = service._normalize_analysis(
        VisionAnalysis(
            prediction="Dust",
            confidence=0.82,
            dust_coverage_percent=12,
            reason="Only minor specks are visible.",
        )
    )

    assert result.prediction == "Clean"
    assert result.dust_coverage_percent == 12


def test_crack_reason_overrides_dust_prediction():
    service = make_service()
    result = service._normalize_analysis(
        VisionAnalysis(
            prediction="Dust",
            confidence=0.76,
            dust_coverage_percent=80,
            reason="Dust is present with a visible crack across the glass.",
        )
    )

    assert result.prediction == "Crack"
    assert result.dust_coverage_percent == 0


def test_negative_crack_reason_does_not_override_dust_prediction():
    service = make_service()
    result = service._normalize_analysis(
        VisionAnalysis(
            prediction="Dust",
            confidence=0.76,
            dust_coverage_percent=80,
            reason="Heavy dust with no visible crack.",
        )
    )

    assert result.prediction == "Dust"
    assert result.dust_coverage_percent == 80
