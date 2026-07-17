import logging

import httpx

from ..config import Settings
from ..schemas import WeatherData

logger = logging.getLogger(__name__)


class WeatherServiceError(RuntimeError):
    pass


class WeatherService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def get_current_weather(self) -> WeatherData:
        if self.settings.latitude is None or self.settings.longitude is None:
            raise WeatherServiceError("LATITUDE and LONGITUDE must be configured for weather checks.")

        params = {
            "latitude": self.settings.latitude,
            "longitude": self.settings.longitude,
            "current": "wind_speed_10m,rain",
            "wind_speed_unit": "ms",
            "timezone": "auto",
        }
        logger.info("Weather request started")
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
                response.raise_for_status()
            payload = response.json()
            current = payload.get("current") or {}
            wind_speed = current.get("wind_speed_10m")
            rainfall = current.get("rain")
            if wind_speed is None or rainfall is None:
                raise WeatherServiceError("Open-Meteo response did not include wind_speed_10m and rain.")
            data = WeatherData(wind_speed_mps=float(wind_speed), rainfall_mm=float(rainfall))
            logger.info(
                "Weather values received: wind_speed_mps=%.2f rainfall_mm=%.2f",
                data.wind_speed_mps,
                data.rainfall_mm,
            )
            return data
        except WeatherServiceError:
            raise
        except Exception as exc:
            logger.exception("Weather request failed")
            raise WeatherServiceError(f"Weather data unavailable: {exc}") from exc
