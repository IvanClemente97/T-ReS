"""Registry of telemetry sources currently implemented by T-ReS."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from t_res.adapters.assetto_corsa.paths import (
    default_snapshot_path as ac_default_snapshot_path,
    default_tracks_root as ac_default_tracks_root,
)
from t_res.adapters.assetto_corsa.source import AssettoCorsaAdapter
from t_res.adapters.protocol import TelemetryAdapter


AdapterFactory = Callable[[Mapping[str, str]], TelemetryAdapter]
PathProvider = Callable[[], Path | None]


@dataclass(frozen=True, slots=True)
class AdapterRegistration:
    simulator_id: str
    display_name: str
    factory: AdapterFactory
    default_snapshot_path: PathProvider
    default_tracks_root: PathProvider


def _assetto_corsa_factory(options: Mapping[str, str]) -> TelemetryAdapter:
    value = options.get("snapshot_path", "").strip()
    return AssettoCorsaAdapter(Path(value) if value else None)


_REGISTRATIONS = (
    AdapterRegistration(
        simulator_id=AssettoCorsaAdapter.simulator_id,
        display_name=AssettoCorsaAdapter.display_name,
        factory=_assetto_corsa_factory,
        default_snapshot_path=ac_default_snapshot_path,
        default_tracks_root=ac_default_tracks_root,
    ),
)


def available_adapters() -> tuple[AdapterRegistration, ...]:
    return _REGISTRATIONS


def adapter_registration(simulator_id: str) -> AdapterRegistration:
    for registration in _REGISTRATIONS:
        if registration.simulator_id == simulator_id:
            return registration
    raise ValueError(f"No telemetry adapter is registered for {simulator_id!r}.")


def create_adapter(
    simulator_id: str,
    options: Mapping[str, str] | None = None,
) -> TelemetryAdapter:
    return adapter_registration(simulator_id).factory(options or {})
