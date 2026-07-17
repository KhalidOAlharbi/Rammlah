import logging
from dataclasses import dataclass

import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl

from ..schemas import FuzzyInputs, FuzzyResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FuzzyLogicConfig:
    dust_min: float = 0.0
    dust_max: float = 100.0
    wind_min: float = 0.0
    wind_max: float = 2.0
    rainfall_min: float = 0.0
    rainfall_max: float = 0.3
    output_min: float = 0.0
    output_max: float = 100.0
    clean_threshold: float = 60.0


class FuzzyLogicError(RuntimeError):
    pass


class FuzzyLogicService:
    def __init__(self, config: FuzzyLogicConfig | None = None):
        self.config = config or FuzzyLogicConfig()
        self._system = self._build_system()

    def calculate(self, dust_coverage_percent: float, wind_speed_mps: float, rainfall_mm: float) -> FuzzyResult:
        inputs = FuzzyInputs(
            dust_coverage_percent=dust_coverage_percent,
            wind_speed_mps=wind_speed_mps,
            rainfall_mm=rainfall_mm,
        )
        logger.info("Fuzzy inputs: %s", inputs.model_dump())
        try:
            simulation = ctrl.ControlSystemSimulation(self._system)
            simulation.input["dust"] = float(np.clip(dust_coverage_percent, 0, 100))
            simulation.input["wind"] = float(np.clip(wind_speed_mps, 0, self.config.wind_max))
            simulation.input["rainfall"] = float(np.clip(rainfall_mm, 0, self.config.rainfall_max))
            simulation.compute()
            score = float(simulation.output["cleaning_requirement"])
        except Exception as exc:
            logger.exception("Fuzzy calculation failed")
            raise FuzzyLogicError(f"Fuzzy calculation failed: {exc}") from exc

        decision = "Clean" if score >= self.config.clean_threshold else "Postpone"
        logger.info("Fuzzy score=%.2f decision=%s", score, decision)
        return FuzzyResult(score=round(score, 2), decision=decision, inputs=inputs)

    def _build_system(self) -> ctrl.ControlSystem:
        dust = ctrl.Antecedent(np.arange(0, 101, 1), "dust")
        wind = ctrl.Antecedent(np.arange(0, 2.01, 0.01), "wind")
        rainfall = ctrl.Antecedent(np.arange(0, 0.301, 0.001), "rainfall")
        cleaning = ctrl.Consequent(np.arange(0, 101, 1), "cleaning_requirement")

        dust["moderate"] = fuzz.trapmf(dust.universe, [25, 30, 45, 60])
        dust["high"] = fuzz.trimf(dust.universe, [50, 68, 86])
        dust["very_high"] = fuzz.trapmf(dust.universe, [76, 90, 100, 100])

        wind["calm"] = fuzz.trapmf(wind.universe, [0, 0, 0.75, 1.15])
        wind["light"] = fuzz.trapmf(wind.universe, [0.85, 1.2, 2.0, 2.0])

        rainfall["none"] = fuzz.trapmf(rainfall.universe, [0, 0, 0.04, 0.11])
        rainfall["very_light"] = fuzz.trapmf(rainfall.universe, [0.08, 0.14, 0.3, 0.3])

        cleaning["postpone"] = fuzz.trapmf(cleaning.universe, [0, 0, 35, 58])
        cleaning["clean"] = fuzz.trapmf(cleaning.universe, [55, 72, 100, 100])

        rules = [
            ctrl.Rule(dust["very_high"] & wind["calm"] & rainfall["none"], cleaning["clean"]),
            ctrl.Rule(dust["high"] & wind["calm"] & rainfall["none"], cleaning["clean"] % 0.9),
            ctrl.Rule(dust["moderate"] & wind["calm"] & rainfall["none"], cleaning["clean"] % 0.72),
            ctrl.Rule(dust["very_high"] & wind["light"] & rainfall["none"], cleaning["clean"]),
            ctrl.Rule(dust["high"] & wind["light"] & rainfall["none"], cleaning["clean"] % 0.78),
            ctrl.Rule(dust["moderate"] & wind["light"], cleaning["postpone"]),
            ctrl.Rule(rainfall["very_light"] & dust["moderate"], cleaning["postpone"]),
            ctrl.Rule(rainfall["very_light"] & wind["light"], cleaning["postpone"]),
            ctrl.Rule(rainfall["very_light"] & dust["very_high"], cleaning["clean"] % 0.7),
        ]
        return ctrl.ControlSystem(rules)
