"""Compact dashboard widgets that render only validated game snapshots."""

from __future__ import annotations

import configparser
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QWidget

from t_res.domain.models import CarTelemetry, TelemetrySnapshot


COLORS = {
    "background": "#11151B",
    "panel": "#171D25",
    "grid": "#39424E",
    "text": "#E7ECF2",
    "muted": "#9AA7B5",
    "throttle": "#22C55E",
    "brake": "#EF4444",
    "speed": "#38BDF8",
    "gear": "#FACC15",
    "green": "#22C55E",
    "purple": "#A855F7",
    "yellow": "#FACC15",
}


def _format_lap_time(value: int | None) -> str:
    if value is None or value <= 0:
        return "—"
    minutes, remainder = divmod(value, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{minutes}:{seconds:02d}.{milliseconds:03d}"


def _pedal_percent(value: float | None) -> float | None:
    return value * 100.0 if value is not None else None


class RaceMapWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(360, 250)
        self._track_root: Path | None = None
        self._track_key: tuple[str | None, str | None] | None = None
        self._pixmap = QPixmap()
        self._map_parameters: tuple[float, float, float, float] | None = None
        self._snapshot: TelemetrySnapshot | None = None
        self._trace: list[tuple[float, float, int | None]] = []
        self._message = "Selecciona la carpeta content/tracks de Assetto Corsa"

    def set_track_root(self, path: Path | None) -> None:
        self._track_root = path
        self._track_key = None
        self._load_track_map()
        self.update()

    def clear_trace(self) -> None:
        self._trace.clear()
        self.update()

    def set_snapshot(self, snapshot: TelemetrySnapshot | None) -> None:
        self._snapshot = snapshot
        key = (snapshot.track, snapshot.layout) if snapshot else None
        if key != self._track_key:
            self._track_key = key
            self._trace.clear()
            self._load_track_map()
        self.update()

    def add_player_position(self, car: CarTelemetry, sector_index: int | None) -> None:
        if car.world_x is None or car.world_z is None:
            return
        if self._trace and self._trace[-1][:2] == (car.world_x, car.world_z):
            return
        self._trace.append((car.world_x, car.world_z, sector_index))
        if len(self._trace) > 20_000:
            self._trace = self._trace[-20_000:]
        self.update()

    def _load_track_map(self) -> None:
        self._pixmap = QPixmap()
        self._map_parameters = None
        snapshot = self._snapshot
        if snapshot is None or self._track_root is None:
            if snapshot is not None and "assetto_corsa_python_api" not in snapshot.sources:
                self._message = "Telemetría del jugador activa; el complemento es necesario para mapa y rivales"
            else:
                self._message = "Esperando circuito y carpeta de mapas"
            return
        track = snapshot.track
        layout = snapshot.layout
        if not track or track in (".", "..") or "/" in track or "\\" in track:
            self._message = "El juego no ha proporcionado un circuito válido"
            return
        if layout and (layout in (".", "..") or "/" in layout or "\\" in layout):
            self._message = "El juego no ha proporcionado un layout válido"
            return
        base = self._track_root / track
        folders = ([base / layout] if layout else []) + [base]
        for folder in folders:
            image = folder / "map.png"
            ini = folder / "data" / "map.ini"
            if not image.is_file() or not ini.is_file():
                continue
            parser = configparser.ConfigParser()
            try:
                parser.read(ini, encoding="utf-8")
                params = parser["PARAMETERS"]
                width = float(params["WIDTH"])
                height = float(params["HEIGHT"])
                offset_x = float(params["X_OFFSET"])
                offset_z = float(params["Z_OFFSET"])
                pixmap = QPixmap(str(image))
                if pixmap.isNull() or not all(
                    math.isfinite(value) for value in (width, height, offset_x, offset_z)
                ) or width <= 0 or height <= 0:
                    raise ValueError("Invalid map image or dimensions.")
            except (OSError, KeyError, ValueError, configparser.Error):
                self._message = f"El mapa de {track} no es válido"
                return
            self._pixmap = pixmap
            self._map_parameters = (width, height, offset_x, offset_z)
            self._message = ""
            return
        self._message = f"No se encontró map.png/map.ini para {track}"

    def _target_rect(self) -> QRectF:
        bounds = self.rect().adjusted(16, 16, -16, -16)
        if self._pixmap.isNull():
            return QRectF(bounds)
        size = self._pixmap.size()
        size.scale(bounds.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF(
            bounds.left() + (bounds.width() - size.width()) / 2,
            bounds.top() + (bounds.height() - size.height()) / 2,
            size.width(),
            size.height(),
        )

    def _map_point(self, x: float | None, z: float | None,
                   target: QRectF) -> QPointF | None:
        if (self._map_parameters is None or self._pixmap.isNull()
                or x is None or z is None):
            return None
        width, height, offset_x, offset_z = self._map_parameters
        px = (x + offset_x) / width * self._pixmap.width()
        py = (z + offset_z) / height * self._pixmap.height()
        if not (0 <= px <= self._pixmap.width() and 0 <= py <= self._pixmap.height()):
            return None
        return QPointF(target.left() + px / self._pixmap.width() * target.width(),
                       target.top() + py / self._pixmap.height() * target.height())

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(COLORS["background"]))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._pixmap.isNull():
            painter.setPen(QColor(COLORS["muted"]))
            painter.drawText(self.rect().adjusted(20, 20, -20, -20),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                             self._message)
            return

        target = self._target_rect()
        painter.drawPixmap(target, self._pixmap, self._pixmap.rect())
        colors: tuple[str | None, ...] = ()
        if self._snapshot is not None:
            colors = self._snapshot.player.sector_colors
        for left, right in zip(self._trace, self._trace[1:]):
            sector = left[2]
            color_name = colors[sector] if sector is not None and sector < len(colors) else None
            if color_name not in ("green", "purple", "yellow"):
                continue
            start = self._map_point(left[0], left[1], target)
            end = self._map_point(right[0], right[1], target)
            if start is not None and end is not None:
                painter.setPen(QPen(QColor(COLORS[color_name]), 3.0,
                                    Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(start, end)

        if self._snapshot is None:
            return
        for car in self._snapshot.cars:
            point = self._map_point(car.world_x, car.world_z, target)
            if point is None:
                continue
            if car.is_player:
                painter.setPen(QPen(QColor("#FFFFFF"), 2))
                painter.setBrush(QColor("#111827"))
                painter.drawEllipse(point, 7, 7)
                painter.drawText(QRectF(point.x() + 8, point.y() - 10, 70, 20),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 "TÚ")
            else:
                painter.setPen(QPen(QColor("#111827"), 1.5))
                painter.setBrush(QColor("#CBD5E1"))
                painter.drawEllipse(point, 5, 5)


class LeaderboardWidget(QTableWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, 5, parent)
        self.setHorizontalHeaderLabels(("Pos.", "Piloto", "Coche", "Vuelta", "Mejor"))
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(False)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (0, 2, 3, 4):
            self.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

    def set_snapshot(self, snapshot: TelemetrySnapshot | None) -> None:
        self.setRowCount(0)
        if snapshot is None:
            return
        if not snapshot.cars:
            self.insertRow(0)
            self.setSpan(0, 0, 1, 5)
            self.setItem(0, 0, QTableWidgetItem(
                "Sin datos de rivales; hace falta el complemento Python de Assetto Corsa."
            ))
            return
        cars = sorted(snapshot.cars, key=lambda car: (
            car.realtime_position is None and car.official_position is None,
            car.realtime_position or car.official_position or 999,
        ))
        fastest_id = snapshot.fastest_lap_car_id
        for car in cars:
            row = self.rowCount()
            self.insertRow(row)
            position = car.realtime_position or car.official_position
            values = (
                str(position) if position is not None else "—",
                car.driver_name or ("Jugador" if car.is_player else "—"),
                car.car_name or "—",
                str(car.lap_count) if car.lap_count is not None else "—",
                _format_lap_time(car.best_lap_time_ms),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if car.car_id == fastest_id:
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QColor(COLORS["purple"]))
                if car.is_player and column == 1:
                    item.setText(f"▶ {value}")
                self.setItem(row, column, item)


class TelemetryTraceWidget(QWidget):
    """Three synchronized traces: pedals, speed, and gear over lap time."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(260)
        self._samples: list[tuple[int, float | None, float | None,
                                   float | None, int | None]] = []
        self._last_published_at: float | None = None
        self._completed_laps: int | None = None
        self._snapshot: TelemetrySnapshot | None = None

    def clear(self) -> None:
        self._samples.clear()
        self._last_published_at = None
        self.update()

    def set_snapshot(self, snapshot: TelemetrySnapshot | None) -> None:
        self._snapshot = snapshot
        if snapshot is None:
            self.clear()
            return
        if (self._completed_laps is not None
                and snapshot.player.completed_laps is not None
                and snapshot.player.completed_laps != self._completed_laps):
            self._samples.clear()
        self._completed_laps = snapshot.player.completed_laps
        if (self._last_published_at != snapshot.published_at
                and snapshot.player.current_lap_time_ms is not None):
            self._samples.append((
                snapshot.player.current_lap_time_ms,
                _pedal_percent(snapshot.player.throttle),
                _pedal_percent(snapshot.player.brake),
                snapshot.player.speed_kmh,
                snapshot.player.gear,
            ))
            self._samples = self._samples[-3000:]
            self._last_published_at = snapshot.published_at
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(COLORS["panel"]))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if len(self._samples) < 2:
            painter.setPen(QColor(COLORS["muted"]))
            message = "Esperando muestras reales para dibujar las trazas"
            if self._snapshot and not self._samples:
                message = "El tiempo de vuelta o las señales aún no están disponibles"
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, message)
            return

        left, right = 54.0, max(100.0, float(self.width() - 20))
        top, bottom = 16.0, float(self.height() - 20)
        panel_height = (bottom - top) / 3.0
        x_values = [sample[0] for sample in self._samples]
        x_min, x_max = min(x_values), max(x_values)
        if x_max <= x_min:
            x_max = x_min + 1
        speed_values = [sample[3] for sample in self._samples if sample[3] is not None]
        gear_values = [sample[4] for sample in self._samples if sample[4] is not None]
        speed_max = max(50.0, max(speed_values, default=50.0))
        gear_min = min(-1, min(gear_values, default=0))
        gear_max = max(1, max(gear_values, default=1))
        panels = (
            ("Pedales (%)", 0.0, 100.0, (1, COLORS["throttle"]), (2, COLORS["brake"])),
            ("Velocidad (km/h)", 0.0, speed_max, (3, COLORS["speed"])),
            ("Marcha", float(gear_min), float(gear_max), (4, COLORS["gear"])),
        )
        for panel_index, panel in enumerate(panels):
            title, low, high, *series = panel
            y_top = top + panel_index * panel_height
            y_bottom = y_top + panel_height - 10
            painter.setPen(QColor(COLORS["muted"]))
            painter.drawText(6, int(y_top + 15), title)
            if panel_index == 0:
                painter.setPen(QColor(COLORS["throttle"]))
                painter.drawText(int(left + 8), int(y_top + 15), "Acelerador")
                painter.setPen(QColor(COLORS["brake"]))
                painter.drawText(int(left + 92), int(y_top + 15), "Freno")
            painter.setPen(QPen(QColor(COLORS["grid"]), 1))
            painter.drawLine(int(left), int(y_top + 22), int(right), int(y_top + 22))
            painter.drawLine(int(left), int(y_bottom), int(right), int(y_bottom))
            painter.drawText(8, int(y_top + 32), f"{high:g}")
            painter.drawText(8, int(y_bottom), f"{low:g}")
            for value_index, color in series:
                points: list[QPointF] = []
                for sample in self._samples:
                    value = sample[value_index]
                    if value is None:
                        if len(points) > 1:
                            painter.setPen(QPen(QColor(color), 1.8))
                            painter.drawPolyline(points)
                        points = []
                        continue
                    x = left + (sample[0] - x_min) / (x_max - x_min) * (right - left)
                    value = max(low, min(high, float(value)))
                    y = y_bottom - (value - low) / max(1.0, high - low) * (y_bottom - y_top - 24)
                    points.append(QPointF(x, y))
                if len(points) > 1:
                    painter.setPen(QPen(QColor(color), 1.8))
                    painter.drawPolyline(points)
        elapsed_start = x_min / 1000
        elapsed_end = x_max / 1000
        painter.setPen(QColor(COLORS["muted"]))
        painter.drawText(QRectF(left, bottom - 4, right - left, 18),
                         Qt.AlignmentFlag.AlignCenter,
                         f"Tiempo de vuelta (s): {elapsed_start:.1f} — {elapsed_end:.1f}")
