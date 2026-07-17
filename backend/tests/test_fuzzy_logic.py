from app.services.fuzzy_logic import FuzzyLogicService


def test_safe_moderate_dust_recommends_cleaning():
    service = FuzzyLogicService()
    result = service.calculate(dust_coverage_percent=35, wind_speed_mps=0.4, rainfall_mm=0.0)

    assert result.used is True
    assert result.score >= 60
    assert result.decision == "Clean"


def test_very_high_dust_scores_stronger_than_moderate_dust():
    service = FuzzyLogicService()
    moderate = service.calculate(35, 0.4, 0.0)
    very_high = service.calculate(92, 0.4, 0.0)

    assert very_high.score > moderate.score
    assert very_high.decision == "Clean"


def test_light_wind_and_very_light_rain_postpones_moderate_dust():
    service = FuzzyLogicService()
    result = service.calculate(dust_coverage_percent=35, wind_speed_mps=1.8, rainfall_mm=0.2)

    assert result.score < 60
    assert result.decision == "Postpone"


def test_boundary_dust_thirty_can_enter_clean_decision_under_safe_weather():
    service = FuzzyLogicService()
    result = service.calculate(dust_coverage_percent=30, wind_speed_mps=0.2, rainfall_mm=0.0)

    assert result.score >= 60
    assert result.decision == "Clean"
