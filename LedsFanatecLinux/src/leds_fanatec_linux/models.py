"""Tipos validados para telemetría y patrones del volante."""

from __future__ import annotations

from dataclasses import dataclass
import math


FLAG_NAMES = (
    "green",
    "yellow",
    "double_yellow",
    "local_yellow",
    "red",
    "blue",
    "black",
    "white",
    "checkered",
    "penalty",
    "vsc",
    "safety_car",
)

AC_FLAG_MAP = {
    1: "blue",
    2: "yellow",
    3: "black",
    4: "white",
    5: "checkered",
    6: "penalty",
}


class TelemetryDataError(ValueError):
    """Una muestra de telemetría está mal formada o fuera de rango."""


@dataclass(frozen=True, slots=True)
class Telemetry:
    simulator: str
    source: str
    received_at: float
    rpm: float | None = None
    max_rpm: int | None = None
    speed_kmh: float | None = None
    gear: int | None = None
    throttle: float | None = None
    brake: float | None = None
    is_in_pit_lane: bool | None = None
    pit_limiter_on: bool | None = None
    active_flags: frozenset[str] = frozenset()
    flags_available: bool = False

    def __post_init__(self) -> None:
        if not self.simulator or not self.source:
            raise TelemetryDataError("El simulador y el origen son obligatorios.")
        if (
            isinstance(self.received_at, bool)
            or not isinstance(self.received_at, (int, float))
            or not math.isfinite(self.received_at)
            or self.received_at < 0
        ):
            raise TelemetryDataError("La marca temporal monotónica no es válida.")
        for field in ("rpm", "speed_kmh"):
            value = getattr(self, field)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise TelemetryDataError(f"{field} no es válido.")
        if self.max_rpm is not None and (
            type(self.max_rpm) is not int or not 1000 <= self.max_rpm <= 30000
        ):
            raise TelemetryDataError("max_rpm debe estar entre 1000 y 30000.")
        if self.gear is not None and (
            type(self.gear) is not int or not -1 <= self.gear <= 10
        ):
            raise TelemetryDataError("gear debe estar entre -1 y 10.")
        for field in ("throttle", "brake"):
            value = getattr(self, field)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise TelemetryDataError(f"{field} debe estar entre 0 y 1.")
        for field in ("is_in_pit_lane", "pit_limiter_on"):
            value = getattr(self, field)
            if value is not None and type(value) is not bool:
                raise TelemetryDataError(f"{field} debe ser booleano o None.")
        if not isinstance(self.active_flags, frozenset) or not self.active_flags.issubset(
            FLAG_NAMES
        ):
            raise TelemetryDataError("La muestra contiene banderas desconocidas.")
        if type(self.flags_available) is not bool:
            raise TelemetryDataError("flags_available debe ser booleano.")
        if self.active_flags and not self.flags_available:
            raise TelemetryDataError("No puede haber banderas si el dato no está disponible.")


def parse_color(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise ValueError("El color debe estar expresado como #RRGGBB.")
    normalized = value.removeprefix("#")
    if len(normalized) != 6:
        raise ValueError("El color debe tener seis dígitos hexadecimales.")
    try:
        return tuple(int(normalized[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError as error:
        raise ValueError("El color debe estar expresado como #RRGGBB.") from error


@dataclass(frozen=True, slots=True)
class LedProfile:
    profile_id: str
    name: str
    rpm_colors: tuple[str, ...]
    max_rpm_colors: tuple[str, ...]
    sequence: str
    max_rpm_blink_ms: int = 500

    def __post_init__(self) -> None:
        import uuid

        try:
            uuid.UUID(self.profile_id)
        except (ValueError, AttributeError) as error:
            raise ValueError("El identificador del perfil debe ser un UUID.") from error
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("El nombre del perfil no puede estar vacío.")
        if len(self.rpm_colors) != 9 or len(self.max_rpm_colors) != 9:
            raise ValueError("El perfil debe definir nueve colores RPM y nueve RPM MAX.")
        for color in (*self.rpm_colors, *self.max_rpm_colors):
            parse_color(color)
        if self.sequence not in {"left_to_right", "outer_to_center"}:
            raise ValueError("La secuencia RPM seleccionada no es válida.")
        if (
            type(self.max_rpm_blink_ms) is not int
            or not 100 <= self.max_rpm_blink_ms <= 4000
        ):
            raise ValueError("El periodo de parpadeo MAX debe estar entre 100 y 4000 ms.")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 3,
            "profile_id": self.profile_id,
            "name": self.name,
            "rpm_colors": list(self.rpm_colors),
            "max_rpm_colors": list(self.max_rpm_colors),
            "sequence": self.sequence,
            "max_rpm_blink_ms": self.max_rpm_blink_ms,
        }

    @classmethod
    def from_dict(cls, data: object) -> "LedProfile":
        import uuid

        if not isinstance(data, dict) or data.get("schema_version") not in (1, 2, 3):
            raise ValueError("Formato de perfil no compatible.")
        rpm_colors = data.get("rpm_colors")
        if not isinstance(rpm_colors, list) or len(rpm_colors) != 9:
            raise ValueError("El perfil debe contener nueve colores RPM.")
        for color in rpm_colors:
            parse_color(color)
        if data.get("schema_version") == 1:
            legacy_color = data.get("shift_color")
            parse_color(legacy_color)
            max_rpm_colors = [legacy_color] * 9
        else:
            max_rpm_colors = data.get("max_rpm_colors")
            if not isinstance(max_rpm_colors, list) or len(max_rpm_colors) != 9:
                raise ValueError("El perfil debe contener nueve colores RPM MAX.")
            for color in max_rpm_colors:
                parse_color(color)
        blink_ms = data.get("max_rpm_blink_ms", 500)
        profile_id = data.get("profile_id")
        if not isinstance(profile_id, str):
            raise ValueError("El identificador del perfil no es válido.")
        uuid.UUID(profile_id)
        return cls(
            profile_id=profile_id,
            name=data.get("name"),
            rpm_colors=tuple(color.upper() for color in rpm_colors),
            max_rpm_colors=tuple(color.upper() for color in max_rpm_colors),
            sequence=data.get("sequence"),
            max_rpm_blink_ms=blink_ms,
        )


def default_profile(name: str = "Predeterminado") -> LedProfile:
    import uuid

    rpm_colors = []
    for position in range(1, 10):
        fraction = position / 9
        if fraction <= 0.45:
            color = "#00FF00"
        elif fraction <= 0.65:
            color = "#FFFF00"
        elif fraction <= 0.82:
            color = "#FF8000"
        else:
            color = "#FF0000"
        rpm_colors.append(color)
    return LedProfile(
        profile_id=str(uuid.uuid4()),
        name=name,
        rpm_colors=tuple(rpm_colors),
        max_rpm_colors=("#8000FF",) * 9,
        sequence="left_to_right",
        max_rpm_blink_ms=500,
    )
