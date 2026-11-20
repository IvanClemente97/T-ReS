"""Generación pura de patrones RGB para RPM y banderas."""

from __future__ import annotations

import math
import time

from .models import FLAG_NAMES, LedProfile, Telemetry, parse_color

RPM_ZONES = tuple(f"RPM{index}" for index in range(1, 10))
FLAG_ZONES = tuple(
    [f"LFLAG{index}" for index in range(1, 4)]
    + [f"RFLAG{index}" for index in range(1, 4)]
)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
PIT_RED = (255, 0, 0)
PIT_AMBER = (255, 140, 0)
PIT_MAGENTA = (255, 0, 255)
FLAG_RGB = {
    "green": (0, 255, 0),
    "yellow": (255, 255, 0),
    "red": (255, 0, 0),
    "blue": (0, 0, 255),
    "black": WHITE,
    "white": WHITE,
    "checkered": WHITE,
    "penalty": WHITE,
    "vsc": (255, 140, 0),
    "safety_car": (255, 255, 0),
}


def _sequence_order(sequence: str) -> tuple[str, ...]:
    if sequence == "left_to_right":
        return RPM_ZONES
    if sequence == "outer_to_center":
        return (
            "RPM1",
            "RPM9",
            "RPM2",
            "RPM8",
            "RPM3",
            "RPM7",
            "RPM4",
            "RPM6",
            "RPM5",
        )
    raise ValueError(f"Secuencia RPM desconocida: {sequence}")


class RpmPattern:
    zones = RPM_ZONES

    def __init__(self) -> None:
        self._shift_active = False

    def reset(self) -> None:
        self._shift_active = False

    def calculate(
        self,
        rpm: float | None,
        max_rpm: int | None,
        profile: LedProfile,
        *,
        blink_on: bool,
        hysteresis_rpm: float = 150,
    ) -> dict[str, tuple[int, int, int]]:
        if rpm is None or max_rpm is None:
            self.reset()
            return {zone: BLACK for zone in RPM_ZONES}
        if not math.isfinite(rpm) or rpm < 0 or max_rpm <= 0:
            raise ValueError("RPM o límite de cambio inválido.")
        if not self._shift_active and rpm >= max_rpm:
            self._shift_active = True
        elif self._shift_active and rpm < max(0, max_rpm - hysteresis_rpm):
            self._shift_active = False
        if self._shift_active:
            return {
                zone: parse_color(profile.max_rpm_colors[index]) if blink_on else BLACK
                for index, zone in enumerate(RPM_ZONES)
            }

        order = _sequence_order(profile.sequence)
        count = min(9, math.floor(min(1.0, rpm / max_rpm) * 9 + 1e-12))
        lit = set(order[:count])
        colors = {
            zone: parse_color(profile.rpm_colors[index]) if zone in lit else BLACK
            for index, zone in enumerate(RPM_ZONES)
        }
        return colors

    def test_frame(
        self, profile: LedProfile, elapsed: float, *, max_rpm: bool = False
    ) -> dict[str, tuple[int, int, int]]:
        if elapsed < 0:
            raise ValueError("elapsed no puede ser negativo.")
        if max_rpm:
            half_period_s = profile.max_rpm_blink_ms / 2000
            blink_on = int(elapsed / half_period_s) % 2 == 0
            return {
                zone: parse_color(profile.max_rpm_colors[index]) if blink_on else BLACK
                for index, zone in enumerate(RPM_ZONES)
            }
        order = _sequence_order(profile.sequence)
        count = min(9, int(elapsed / 0.3) + 1)
        lit = set(order[:count])
        return {
            zone: parse_color(profile.rpm_colors[index]) if zone in lit else BLACK
            for index, zone in enumerate(RPM_ZONES)
        }


class FlagPattern:
    zones = FLAG_ZONES

    def __init__(self, blink_interval: float = 0.25) -> None:
        self.blink_interval = blink_interval
        self._green_started_at: float | None = None
        self._penalty_started_at: float | None = None

    def reset(self) -> None:
        self._green_started_at = None
        self._penalty_started_at = None

    def calculate(self, telemetry: Telemetry, *, now: float | None = None) -> dict[str, tuple[int, int, int]]:
        now = time.monotonic() if now is None else now
        return self.calculate_flags(
            telemetry.active_flags,
            available=telemetry.flags_available,
            is_in_pit_lane=telemetry.is_in_pit_lane,
            pit_limiter_on=telemetry.pit_limiter_on,
            now=now,
        )

    def calculate_test(
        self, flag: str, *, now: float | None = None
    ) -> dict[str, tuple[int, int, int]]:
        if flag not in FLAG_NAMES:
            raise ValueError(f"Bandera desconocida: {flag}")
        return self.calculate_flags(
            frozenset({flag}),
            available=True,
            is_in_pit_lane=False,
            pit_limiter_on=False,
            now=now,
        )

    def calculate_flags(
        self,
        flags: frozenset[str],
        *,
        available: bool,
        is_in_pit_lane: bool | None,
        pit_limiter_on: bool | None,
        now: float | None = None,
    ) -> dict[str, tuple[int, int, int]]:
        now = time.monotonic() if now is None else now
        off = {zone: BLACK for zone in FLAG_ZONES}
        if not available:
            self.reset()
            return off

        if "green" in flags and self._green_started_at is None:
            self._green_started_at = now
        if "green" not in flags:
            self._green_started_at = None
        if "penalty" in flags and self._penalty_started_at is None:
            self._penalty_started_at = now
        if "penalty" not in flags:
            self._penalty_started_at = None

        phase = int(now / self.blink_interval)
        if "checkered" in flags:
            colors = (WHITE, BLACK, WHITE, BLACK, WHITE, BLACK)
            if phase % 2:
                colors = tuple(reversed(colors))
            return dict(zip(FLAG_ZONES, colors))
        if is_in_pit_lane:
            if pit_limiter_on:
                color = PIT_AMBER if phase % 2 == 0 else PIT_MAGENTA
                zones = FLAG_ZONES[:3] if phase % 2 == 0 else FLAG_ZONES[3:]
                return {
                    zone: color if zone in zones else BLACK for zone in FLAG_ZONES
                }
            color = PIT_RED if phase % 2 == 0 else WHITE
            return {zone: color for zone in FLAG_ZONES}
        if not flags:
            return off
        if "red" in flags:
            return {zone: FLAG_RGB["red"] for zone in FLAG_ZONES}
        if "safety_car" in flags:
            yellow = FLAG_RGB["safety_car"]
            result = {zone: yellow for zone in FLAG_ZONES}
            result["LFLAG1"] = result["RFLAG1"] = WHITE
            return result
        if "vsc" in flags:
            index = phase % len(FLAG_ZONES)
            zone = FLAG_ZONES[index]
            color = FLAG_RGB["vsc"] if index % 2 == 0 else WHITE
            return {name: color if name == zone else BLACK for name in FLAG_ZONES}
        if "double_yellow" in flags:
            zones = FLAG_ZONES[:3] if phase % 2 == 0 else FLAG_ZONES[3:]
            return {
                zone: FLAG_RGB["yellow"] if zone in zones else BLACK
                for zone in FLAG_ZONES
            }
        if "local_yellow" in flags:
            zone = FLAG_ZONES[phase % len(FLAG_ZONES)]
            return {
                name: FLAG_RGB["yellow"] if name == zone else BLACK
                for name in FLAG_ZONES
            }
        if "yellow" in flags:
            return {zone: FLAG_RGB["yellow"] for zone in FLAG_ZONES}
        if "blue" in flags:
            return {zone: FLAG_RGB["blue"] for zone in FLAG_ZONES}
        if "black" in flags:
            color = WHITE if phase % 2 == 0 else BLACK
            other = BLACK if color == WHITE else WHITE
            return {
                zone: color if zone in ("LFLAG1", "LFLAG3", "RFLAG1", "RFLAG3") else other
                for zone in FLAG_ZONES
            }
        if "white" in flags:
            return {zone: FLAG_RGB["white"] for zone in FLAG_ZONES}
        if "penalty" in flags:
            if self._penalty_started_at is not None and now - self._penalty_started_at < 2:
                color = FLAG_RGB["penalty"]
                return {
                    zone: color if zone in FLAG_ZONES[1:3] + FLAG_ZONES[4:6] else BLACK
                    for zone in FLAG_ZONES
                }
            return off
        if "green" in flags and self._green_started_at is not None:
            if now - self._green_started_at < 3:
                return {zone: FLAG_RGB["green"] for zone in FLAG_ZONES}
        return off
