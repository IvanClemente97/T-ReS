"""Contracts implemented by simulator-specific telemetry adapters."""

from __future__ import annotations

from typing import Protocol

from t_res.domain.models import TelemetrySnapshot


class TelemetryAdapter(Protocol):
    simulator_id: str
    display_name: str

    def read(self) -> TelemetrySnapshot:
        """Return the latest validated snapshot or raise when no source is available."""
