"""Validated, simulator-neutral telemetry values used by the dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import time
from typing import Any, Mapping


PROTOCOL_VERSION = 1
SIMULATOR_ID = "assetto_corsa_2014"
MAX_CARS = 60
MAX_PACKET_AGE_SECONDS = 2.0
SECTOR_COLORS = frozenset({"green", "purple", "yellow"})


class Availability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"
    STALE = "stale"


class TelemetryValidationError(ValueError):
    """A snapshot is malformed, unsupported, or too old to display."""


def _number(value: Any, *, minimum: float | None = None,
            maximum: float | None = None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TelemetryValidationError("Expected a numeric telemetry value.")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise TelemetryValidationError("Telemetry value cannot be represented.") from error
    if not math.isfinite(result):
        raise TelemetryValidationError("Telemetry values must be finite.")
    if minimum is not None and result < minimum:
        raise TelemetryValidationError("Telemetry value is below its valid range.")
    if maximum is not None and result > maximum:
        raise TelemetryValidationError("Telemetry value is above its valid range.")
    return result


def _integer(value: Any, *, minimum: int | None = None,
             maximum: int | None = None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TelemetryValidationError("Expected an integer telemetry value.")
    if minimum is not None and value < minimum:
        raise TelemetryValidationError("Integer telemetry value is below its valid range.")
    if maximum is not None and value > maximum:
        raise TelemetryValidationError("Integer telemetry value is above its valid range.")
    return value


def _text(value: Any, *, maximum_length: int = 96) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TelemetryValidationError("Expected a text telemetry value.")
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > maximum_length:
        raise TelemetryValidationError("Text telemetry value is too long.")
    return cleaned


def _team_color(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        raise TelemetryValidationError("Team color must use #RRGGBB format.")
    if any(character not in "0123456789abcdefABCDEF" for character in value[1:]):
        raise TelemetryValidationError("Team color must use #RRGGBB format.")
    return value.upper()


def _availability(value: Any) -> Availability:
    if value is None:
        return Availability.UNAVAILABLE
    try:
        return Availability(value)
    except (ValueError, TypeError) as error:
        raise TelemetryValidationError("Unknown field availability.") from error


@dataclass(frozen=True, slots=True)
class PlayerTelemetry:
    source: str
    speed_kmh: float | None
    throttle: float | None
    brake: float | None
    gear: int | None
    rpm: int | None
    completed_laps: int | None
    total_laps: int | None
    track_position: float | None
    current_lap_time_ms: int | None
    last_lap_time_ms: int | None
    best_lap_time_ms: int | None
    current_sector_index: int | None
    last_sector_time_ms: int | None
    sector_colors: tuple[str | None, ...]
    availability: Mapping[str, Availability]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> PlayerTelemetry:
        source = _text(raw.get("source"))
        if source is None:
            raise TelemetryValidationError("Player telemetry source is unavailable.")
        availability_raw = raw.get("availability", {})
        if not isinstance(availability_raw, dict):
            raise TelemetryValidationError("Player availability must be an object.")
        availability = {
            str(name): _availability(value)
            for name, value in availability_raw.items()
        }

        colors_raw = raw.get("sector_colors", [])
        if not isinstance(colors_raw, list) or len(colors_raw) > 16:
            raise TelemetryValidationError("sector_colors must be a list of at most 16 items.")
        colors = []
        for color in colors_raw:
            if color is not None and (
                not isinstance(color, str) or color not in SECTOR_COLORS
            ):
                raise TelemetryValidationError("Sector color is not permitted.")
            colors.append(color)

        return cls(
            source=source,
            speed_kmh=_number(raw.get("speed_kmh"), minimum=0, maximum=600),
            throttle=_number(raw.get("throttle"), minimum=0, maximum=1),
            brake=_number(raw.get("brake"), minimum=0, maximum=1),
            gear=_integer(raw.get("gear"), minimum=-1, maximum=10),
            rpm=_integer(raw.get("rpm"), minimum=0, maximum=30000),
            completed_laps=_integer(raw.get("completed_laps"), minimum=0, maximum=10000),
            total_laps=_integer(raw.get("total_laps"), minimum=0, maximum=1000),
            track_position=_number(raw.get("track_position"), minimum=0, maximum=1),
            current_lap_time_ms=_integer(
                raw.get("current_lap_time_ms"), minimum=0, maximum=600000
            ),
            last_lap_time_ms=_integer(raw.get("last_lap_time_ms"), minimum=0, maximum=600000),
            best_lap_time_ms=_integer(raw.get("best_lap_time_ms"), minimum=0, maximum=600000),
            current_sector_index=_integer(
                raw.get("current_sector_index"), minimum=0, maximum=15
            ),
            last_sector_time_ms=_integer(
                raw.get("last_sector_time_ms"), minimum=0, maximum=600000
            ),
            sector_colors=tuple(colors),
            availability=availability,
        )


@dataclass(frozen=True, slots=True)
class CarTelemetry:
    car_id: int
    source: str
    is_player: bool
    driver_name: str | None
    car_name: str | None
    lap_count: int | None
    official_position: int | None
    realtime_position: int | None
    best_lap_time_ms: int | None
    world_x: float | None
    world_z: float | None
    track_position: float | None
    speed_kmh: float | None
    brand: str | None
    vehicle_class: str | None
    team_name: str | None
    team_color: str | None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> CarTelemetry:
        if not isinstance(raw.get("is_player"), bool):
            raise TelemetryValidationError("Car is_player must be boolean.")
        source = _text(raw.get("source"))
        if source is None:
            raise TelemetryValidationError("Car telemetry source is unavailable.")
        car_id = _integer(raw.get("car_id"), minimum=0, maximum=MAX_CARS - 1)
        if car_id is None:
            raise TelemetryValidationError("Car ID is unavailable.")
        return cls(
            car_id=car_id,
            source=source,
            is_player=raw["is_player"],
            driver_name=_text(raw.get("driver_name")),
            car_name=_text(raw.get("car_name")),
            lap_count=_integer(raw.get("lap_count"), minimum=0, maximum=10000),
            official_position=_integer(raw.get("official_position"), minimum=1, maximum=MAX_CARS),
            realtime_position=_integer(raw.get("realtime_position"), minimum=1, maximum=MAX_CARS),
            best_lap_time_ms=_integer(
                raw.get("best_lap_time_ms"), minimum=0, maximum=600000
            ),
            world_x=_number(raw.get("world_x"), minimum=-100000, maximum=100000),
            world_z=_number(raw.get("world_z"), minimum=-100000, maximum=100000),
            track_position=_number(raw.get("track_position"), minimum=0, maximum=1),
            speed_kmh=_number(raw.get("speed_kmh"), minimum=0, maximum=600),
            brand=_text(raw.get("brand"), maximum_length=64),
            vehicle_class=_text(raw.get("vehicle_class"), maximum_length=32),
            team_name=_text(raw.get("team_name"), maximum_length=96),
            team_color=_team_color(raw.get("team_color")),
        )


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    published_at: float
    simulator: str
    track: str | None
    layout: str | None
    session_type: str | None
    lap_times_complete: bool
    player: PlayerTelemetry
    cars: tuple[CarTelemetry, ...]

    @property
    def sources(self) -> frozenset[str]:
        return frozenset(
            source for source in (
                self.player.source, *(car.source for car in self.cars)
            ) if source != "unavailable"
        )

    @property
    def laps_remaining(self) -> int | None:
        total = self.player.total_laps
        completed = self.player.completed_laps
        if total is None or total <= 0 or completed is None or completed > total:
            return None
        return total - completed

    @property
    def fastest_lap_car_id(self) -> int | None:
        if not self.lap_times_complete:
            return None
        valid = [
            car for car in self.cars
            if car.best_lap_time_ms is not None and car.best_lap_time_ms > 0
        ]
        if not valid:
            return None
        return min(valid, key=lambda car: car.best_lap_time_ms).car_id


def parse_snapshot(
    payload: str | bytes,
    *,
    now: float | None = None,
    stale_after: float = MAX_PACKET_AGE_SECONDS,
    expected_simulator: str | None = None,
) -> TelemetrySnapshot:
    """Parse and validate a real game snapshot; missing fields remain unavailable."""
    import json

    if not math.isfinite(stale_after) or stale_after <= 0:
        raise ValueError("stale_after must be finite and positive.")
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
        raise TelemetryValidationError("Snapshot is not valid JSON.") from error
    if not isinstance(raw, dict):
        raise TelemetryValidationError("Snapshot root must be an object.")
    if raw.get("protocol_version") != PROTOCOL_VERSION:
        raise TelemetryValidationError("Unsupported snapshot protocol version.")
    simulator = _text(raw.get("simulator"))
    if simulator is None:
        raise TelemetryValidationError("Snapshot simulator is unavailable.")
    if expected_simulator is not None and simulator != expected_simulator:
        raise TelemetryValidationError("Snapshot does not match the selected simulator.")

    published_at = _number(raw.get("published_at_unix_s"), minimum=0)
    if published_at is None:
        raise TelemetryValidationError("Snapshot publication time is unavailable.")
    current_time = now if now is not None else time.time()
    if published_at > current_time + 2.0:
        raise TelemetryValidationError("Snapshot publication time is in the future.")
    if current_time - published_at > stale_after:
        raise TelemetryValidationError("Snapshot is stale.")

    player_raw = raw.get("player")
    cars_raw = raw.get("cars")
    if not isinstance(player_raw, dict) or not isinstance(cars_raw, list):
        raise TelemetryValidationError("Snapshot must include player and cars objects.")
    if len(cars_raw) > MAX_CARS:
        raise TelemetryValidationError("Snapshot contains too many cars.")
    cars = tuple(CarTelemetry.from_mapping(car) for car in cars_raw if isinstance(car, dict))
    if len(cars) != len(cars_raw):
        raise TelemetryValidationError("Every car entry must be an object.")
    ids = [car.car_id for car in cars]
    if len(ids) != len(set(ids)):
        raise TelemetryValidationError("Car IDs must be unique.")
    lap_times_complete = raw.get("lap_times_complete", False)
    if not isinstance(lap_times_complete, bool):
        raise TelemetryValidationError("lap_times_complete must be boolean.")
    if lap_times_complete and any(
        car.best_lap_time_ms is None or car.best_lap_time_ms <= 0 for car in cars
    ):
        raise TelemetryValidationError(
            "A complete lap-time classification requires a valid time for every car."
        )

    return TelemetrySnapshot(
        published_at=published_at,
        simulator=simulator,
        track=_text(raw.get("track")),
        layout=_text(raw.get("layout")),
        session_type=_text(raw.get("session_type")),
        lap_times_complete=lap_times_complete,
        player=PlayerTelemetry.from_mapping(player_raw),
        cars=cars,
    )


def classify_sector(
    sector_time_ms: int | None,
    personal_best_ms: int | None,
    session_best_ms: int | None,
) -> str | None:
    """Classify a completed sector only when real timing references are present."""
    if sector_time_ms is None or sector_time_ms <= 0:
        return None
    if session_best_ms is not None and session_best_ms > 0 and sector_time_ms <= session_best_ms:
        return "purple"
    if personal_best_ms is None or personal_best_ms <= 0 or sector_time_ms <= personal_best_ms:
        return "green"
    return "yellow"
