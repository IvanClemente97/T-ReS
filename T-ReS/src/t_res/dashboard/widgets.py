"""Compact dashboard widgets that render only validated game snapshots."""

from __future__ import annotations

import configparser
import json
import math
from pathlib import Path
import re

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from t_res.domain.models import CarTelemetry, TelemetrySnapshot


COLORS = {
    "background": "#0B0D11",
    "panel": "#15191F",
    "grid": "#343B45",
    "text": "#F1F3F5",
    "muted": "#9BA3AD",
    "orange": "#FF6A00",
    "throttle": "#22C55E",
    "brake": "#EF4444",
    "speed": "#38BDF8",
    "gear": "#FACC15",
    "green": "#22C55E",
    "purple": "#A855F7",
    "yellow": "#FACC15",
    "lapped": "#3B82F6",
    "lapping_player": "#C8F135",
}

CLASS_COLORS = {
    "lmp": "#FF6A00",
    "gt3": "#38BDF8",
    "gt2": "#B77AFF",
    "gt4": "#A3E635",
    "gt1": "#F472B6",
    "tcr": "#FACC15",
    "f1": "#FB7185",
    "single-seater": "#FB923C",
}

_FALLBACK_CLASS_COLORS = (
    "#38BDF8", "#B77AFF", "#A3E635", "#F472B6", "#FACC15", "#2DD4BF"
)


def _format_lap_time(value: int | None) -> str:
    if value is None or value <= 0:
        return "—"
    minutes, remainder = divmod(value, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{minutes}:{seconds:02d}.{milliseconds:03d}"


def _ranking_positions(cars: tuple[CarTelemetry, ...]) -> dict[int, int | None]:
    if not cars:
        return {}
    candidates = []
    for preference, field in enumerate(("realtime_position", "official_position")):
        available = [getattr(car, field) for car in cars]
        ranks = [rank for rank in available if rank is not None]
        unique_ranks = set(ranks)
        complete_unique = len(ranks) == len(cars) and len(unique_ranks) == len(cars)
        candidates.append((
            (int(complete_unique), len(unique_ranks), len(ranks), -preference),
            available,
        ))
    available = max(candidates, key=lambda candidate: candidate[0])[1]
    counts: dict[int, int] = {}
    for rank in available:
        if rank is not None:
            counts[rank] = counts.get(rank, 0) + 1
    return {
        car.car_id: rank if rank is not None and counts[rank] == 1 else None
        for car, rank in zip(cars, available)
    }


def _gap_labels(
    cars: tuple[CarTelemetry, ...],
    positions: dict[int, int | None],
    track_length_m: float | None,
) -> dict[int, str]:
    labels = {car.car_id: "—" for car in cars}
    ordered = sorted(
        (car for car in cars if positions.get(car.car_id) is not None),
        key=lambda car: positions[car.car_id] or 999,
    )
    progress = {
        car.car_id: car.lap_count + car.track_position
        for car in ordered
        if car.lap_count is not None and car.track_position is not None
    }
    for ahead, car in zip(ordered, ordered[1:]):
        if ahead.car_id not in progress or car.car_id not in progress:
            continue
        difference = progress[ahead.car_id] - progress[car.car_id]
        if difference < 0:
            continue
        if difference >= 1:
            labels[car.car_id] = f"+{int(difference)} V"
        elif track_length_m is not None and track_length_m > 0:
            gap_m = difference * track_length_m
            labels[car.car_id] = (
                f"+{gap_m:.0f} m" if gap_m < 1000
                else f"+{gap_m / 1000:.2f} km"
            )
    return labels


def _car_display_name(car: CarTelemetry) -> str:
    if car.display_name:
        return car.display_name
    if not car.car_name:
        return "—"
    return " ".join(
        part.capitalize() for part in re.split(r"[_-]+", car.car_name) if part
    )


def _leaderboard_class_key(value: str | None) -> str:
    return " ".join(value.split()).casefold() if value and value.strip() else "unclassified"


def _leaderboard_class_label(value: str | None) -> str:
    if not value or not value.strip():
        return "Clase no disponible"
    normalized = " ".join(value.split())
    match = re.match(r"^(lmp[123]?|gt[1-4]|tcr|f1)\b", normalized, re.IGNORECASE)
    return match.group(1).upper() if match else normalized


def _track_length_from_ui_track(
    track_root: Path, track: str, layout: str | None
) -> float | None:
    base = track_root / track
    metadata_paths = []
    if layout:
        metadata_paths.append(base / "ui" / layout / "ui_track.json")
    metadata_paths.append(base / "ui" / "ui_track.json")
    for path in metadata_paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        value = raw.get("length")
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            length = float(value)
            unit = "m"
        elif isinstance(value, str):
            match = re.fullmatch(
                r"\s*(\d+(?:\.\d+)?)\s*(km|m)?\s*", value, re.IGNORECASE
            )
            if not match:
                continue
            length = float(match.group(1))
            unit = (match.group(2) or "m").lower()
        else:
            continue
        if unit == "km":
            length *= 1000
        if math.isfinite(length) and 100 <= length <= 100000:
            return length
    return None


def _pedal_percent(value: float | None) -> float | None:
    return value * 100.0 if value is not None else None


def _class_key(value: str | None) -> str | None:
    if not value:
        return None
    normalized = "".join(character for character in value.casefold() if character.isalnum())
    for prefix in ("lmp", "gt1", "gt2", "gt3", "gt4", "tcr", "f1"):
        if normalized.startswith(prefix):
            return prefix
    if normalized == "formula1":
        return "f1"
    if normalized == "singleseater":
        return "single-seater"
    return normalized or None


def _map_car_color(snapshot: TelemetrySnapshot, car: CarTelemetry) -> str:
    category = _class_key(car.vehicle_class)
    if car.team_color and (
        snapshot.simulator.casefold().startswith("f1") or category == "f1"
    ):
        return car.team_color

    car_classes = [_class_key(entry.vehicle_class) for entry in snapshot.cars]
    classes = sorted({key for key in car_classes if key is not None})
    all_classes_known = bool(car_classes) and all(key is not None for key in car_classes)
    if len(classes) <= 1:
        if all_classes_known:
            return "#F1F3F5"
        brands = [entry.brand.casefold() if entry.brand else None for entry in snapshot.cars]
        if brands and all(brand is not None for brand in brands) and len(set(brands)) == 1:
            return "#F1F3F5"
        return "#AAB2BD"
    if category is None:
        return "#AAB2BD"
    if category in CLASS_COLORS:
        return CLASS_COLORS[category]
    return _FALLBACK_CLASS_COLORS[classes.index(category) % len(_FALLBACK_CLASS_COLORS)]


def _lap_ring_color(
    snapshot: TelemetrySnapshot, car: CarTelemetry
) -> str | None:
    if car.is_player or car.lap_count is None:
        return None
    player_laps = snapshot.player.completed_laps
    if player_laps is None:
        return None
    if car.lap_count < player_laps:
        return COLORS["lapped"]
    if car.lap_count <= player_laps:
        return None

    player_position = snapshot.player.track_position
    player_speed = snapshot.player.speed_kmh
    if (
        player_position is None
        or player_speed is None
        or car.track_position is None
        or car.speed_kmh is None
    ):
        return None
    gap_behind = (player_position - car.track_position) % 1.0
    if gap_behind <= 0.025 and car.speed_kmh > player_speed + 3.0:
        return COLORS["lapping_player"]
    return None


class RaceMapWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(360, 250)
        self._track_root: Path | None = None
        self._track_key: tuple[str | None, str | None] | None = None
        self._pixmap = QPixmap()
        self._map_parameters: tuple[float, float, float, float] | None = None
        self._track_length_m: float | None = None
        self._snapshot: TelemetrySnapshot | None = None
        self._trace: list[tuple[float, float, int | None]] = []
        self._message = "Selecciona la carpeta content/tracks de Assetto Corsa"

    @property
    def track_length_m(self) -> float | None:
        return self._track_length_m

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
        self._track_length_m = None
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
        self._track_length_m = _track_length_from_ui_track(
            self._track_root, track, layout
        )
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
        bounds = self._map_bounds()
        if self._pixmap.isNull():
            return QRectF(bounds)
        size = self._pixmap.size()
        scale = min(bounds.width() / size.width(), bounds.height() / size.height())
        width = size.width() * scale
        height = size.height() * scale
        return QRectF(
            bounds.left() + (bounds.width() - width) / 2,
            bounds.top() + (bounds.height() - height) / 2,
            width,
            height,
        )

    def _status_column_width(self) -> float:
        return min(168.0, max(138.0, self.width() * 0.25))

    def _map_bounds(self) -> QRectF:
        bounds = QRectF(self.rect()).adjusted(16, 16, -16, -16)
        column_width = min(self._status_column_width(), bounds.width() - 120.0)
        left = bounds.left() + column_width + 10
        return QRectF(left, bounds.top(), max(80.0, bounds.right() - left), bounds.height())

    def _status_overlay_rects(self) -> tuple[QRectF, QRectF]:
        column_width = self._status_column_width()
        box_width = column_width - 12
        first = QRectF(
            self.rect().left() + 8, self.rect().top() + 8, box_width, 46
        )
        second = QRectF(
            first.left(), first.bottom() + 8, box_width, first.height()
        )
        return first, second

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
        background = QLinearGradient(0, 0, self.width(), self.height())
        background.setColorAt(0, QColor("#171B21"))
        background.setColorAt(1, QColor("#0D1014"))
        painter.fillRect(self.rect(), background)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._pixmap.isNull():
            painter.setPen(QColor(COLORS["muted"]))
            painter.drawText(self._map_bounds().adjusted(8, 8, -8, -8),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                             self._message)
            if self._snapshot is not None:
                self._draw_status_overlays(painter)
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
        positions = _ranking_positions(self._snapshot.cars)
        ordered_cars = sorted(self._snapshot.cars, key=lambda car: car.is_player)
        for car in ordered_cars:
            point = self._map_point(car.world_x, car.world_z, target)
            if point is None:
                continue
            marker_color = QColor(_map_car_color(self._snapshot, car))
            ring_color = _lap_ring_color(self._snapshot, car)
            if ring_color:
                painter.setPen(QPen(QColor(ring_color), 2.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(point, 13, 13)
            painter.setPen(QPen(
                QColor(COLORS["orange"] if car.is_player else "#101318"),
                2 if car.is_player else 1.5,
            ))
            painter.setBrush(marker_color)
            painter.drawEllipse(point, 10, 10)
            position = positions.get(car.car_id)
            if position is not None:
                font = QFont()
                font.setBold(True)
                font.setPointSize(7)
                painter.setFont(font)
                contrast = "#111318" if marker_color.lightness() > 155 else "#FFFFFF"
                painter.setPen(QColor(contrast))
                painter.drawText(
                    QRectF(point.x() - 11, point.y() - 8, 22, 16),
                    Qt.AlignmentFlag.AlignCenter,
                    f"P{position}",
                )
            if car.is_player:
                painter.drawText(QRectF(point.x() + 8, point.y() - 10, 70, 20),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 "TÚ")
        self._draw_status_overlays(painter)

    def _draw_status_overlays(self, painter: QPainter) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return
        fastest_time = None
        fastest_id = snapshot.fastest_lap_car_id
        if fastest_id is not None:
            fastest_car = next(
                (car for car in snapshot.cars if car.car_id == fastest_id), None
            )
            fastest_time = _format_lap_time(
                fastest_car.best_lap_time_ms if fastest_car else None
            )
        first, second = self._status_overlay_rects()
        self._draw_overlay_box(
            painter, first,
            "VUELTAS RESTANTES",
            str(snapshot.laps_remaining) if snapshot.laps_remaining is not None else "—",
            COLORS["orange"],
        )
        self._draw_overlay_box(
            painter, second,
            "VUELTA RÁPIDA", fastest_time or "—", COLORS["purple"],
        )

    @staticmethod
    def _draw_overlay_box(
        painter: QPainter, rect: QRectF, title: str, value: str, accent: str
    ) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(8, 10, 13, 225))
        painter.drawRoundedRect(rect, 7, 7)
        painter.setBrush(QColor(accent))
        painter.drawRoundedRect(QRectF(rect.left(), rect.top(), 3, rect.height()), 1, 1)
        painter.setPen(QColor(COLORS["muted"]))
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(7)
        painter.setFont(title_font)
        painter.drawText(
            QRectF(rect.left() + 10, rect.top() + 4, rect.width() - 16, 13),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )
        value_font = QFont()
        value_font.setBold(True)
        value_font.setPointSize(15)
        painter.setFont(value_font)
        painter.setPen(QColor(COLORS["text"]))
        painter.drawText(
            QRectF(rect.left() + 10, rect.top() + 16, rect.width() - 16, 25),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            value,
        )


class LeaderboardWidget(QScrollArea):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content = QWidget()
        self._content.setObjectName("leaderboardContent")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(8)
        self._tables_by_class: dict[str, QTableWidget] = {}
        self._headings_by_class: dict[str, QLabel] = {}
        self._class_order: list[str] = []
        self._group_signature: tuple[tuple[str, tuple[int, ...]], ...] = ()
        self._empty_message: QLabel | None = None
        self.setWidget(self._content)
        self.setStyleSheet(
            "QScrollArea { border: 0; background: transparent; } "
            "QScrollArea QWidget#leaderboardContent { background: transparent; }"
        )

    @property
    def class_tables(self) -> dict[str, QTableWidget]:
        return dict(self._tables_by_class)

    def _clear_groups(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._tables_by_class.clear()
        self._headings_by_class.clear()
        self._empty_message = None

    def _create_table(
        self,
        class_key: str,
        row_count: int,
    ) -> QTableWidget:
        table = QTableWidget(row_count, 5, self._content)
        table.setObjectName(f"classLeaderboard_{class_key}")
        table.setHorizontalHeaderLabels(("Pos.", "Piloto", "Coche", "Vueltas", "GAP"))
        table.horizontalHeaderItem(0).setToolTip(
            "Posición independiente dentro de esta categoría. Se ordena usando "
            "una única fuente global completa y sin rangos duplicados."
        )
        table.horizontalHeaderItem(4).setToolTip(
            "Distancia al siguiente coche de la misma categoría, derivada del "
            "progreso normalizado y la longitud oficial del circuito."
        )
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(False)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for column in (0, 3, 4):
            table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setMinimumHeight(36 + row_count * 28)
        table.setMaximumHeight(36 + row_count * 28)
        return table

    @staticmethod
    def _update_table(
        table: QTableWidget,
        cars: list[CarTelemetry],
        class_ranks: dict[int, int | None],
        gaps: dict[int, str],
        fastest_id: int | None,
    ) -> None:
        table.setUpdatesEnabled(False)
        try:
            for row, car in enumerate(cars):
                class_position = class_ranks.get(car.car_id)
                position_label = (
                    f"P{class_position}" if class_position is not None else "—"
                )
                position_tooltip = ""
                if car.finished is True:
                    position_label += "  ✓"
                    position_tooltip = "Finalizó la carrera"
                elif car.finished is False:
                    position_label += "  ▶"
                    position_tooltip = "Sigue en carrera"
                driver_name = car.driver_name or ("Jugador" if car.is_player else "—")
                if car.is_player:
                    driver_name = f"▶ {driver_name}"
                values = (
                    position_label,
                    driver_name,
                    _car_display_name(car),
                    str(car.lap_count) if car.lap_count is not None else "—",
                    "—" if class_position == 1 else gaps.get(car.car_id, "—"),
                )
                for column, value in enumerate(values):
                    item = table.item(row, column)
                    if item is None:
                        item = QTableWidgetItem()
                        table.setItem(row, column, item)
                    if item.text() != value:
                        item.setText(value)
                    if column == 0 and item.toolTip() != position_tooltip:
                        item.setToolTip(position_tooltip)
                    if column == 1:
                        color = QColor(
                            COLORS["purple"] if car.car_id == fastest_id
                            else COLORS["text"]
                        )
                        if item.foreground().color() != color:
                            item.setForeground(color)
        finally:
            table.setUpdatesEnabled(True)

    def set_snapshot(
        self, snapshot: TelemetrySnapshot | None, track_length_m: float | None = None
    ) -> None:
        if snapshot is None:
            if self._group_signature or self._empty_message is not None:
                self._clear_groups()
                self._group_signature = ()
                self._class_order.clear()
            return
        if not snapshot.cars:
            if self._empty_message is None:
                self._clear_groups()
                self._group_signature = ()
                self._class_order.clear()
                self._empty_message = QLabel(
                    "Sin datos de rivales; hace falta el complemento Python de Assetto Corsa."
                )
                self._empty_message.setWordWrap(True)
                self._empty_message.setStyleSheet(
                    f"color: {COLORS['muted']}; padding: 8px;"
                )
                self._layout.addWidget(self._empty_message)
            return
        positions = _ranking_positions(snapshot.cars)
        cars = sorted(snapshot.cars, key=lambda car: (
            positions.get(car.car_id) is None,
            positions.get(car.car_id) or 999,
            car.car_id,
        ))
        fastest_id = snapshot.fastest_lap_car_id
        groups: dict[str, list[CarTelemetry]] = {}
        labels: dict[str, str] = {}
        for car in cars:
            class_key = _leaderboard_class_key(car.vehicle_class)
            groups.setdefault(class_key, []).append(car)
            labels.setdefault(class_key, _leaderboard_class_label(car.vehicle_class))

        for class_key in groups:
            if class_key not in self._class_order:
                self._class_order.append(class_key)
        class_keys = [key for key in self._class_order if key in groups]
        signature = tuple(
            (key, tuple(sorted(car.car_id for car in groups[key])))
            for key in class_keys
        )
        if signature != self._group_signature:
            self._clear_groups()
            for class_key in class_keys:
                class_cars = groups[class_key]
                class_color = CLASS_COLORS.get(
                    _class_key(class_cars[0].vehicle_class), COLORS["orange"]
                )
                heading = QLabel()
                heading.setObjectName("classLeaderboardHeading")
                heading.setStyleSheet(
                    f"color: {class_color}; font-size: 13px; font-weight: 800; "
                    "padding: 5px 3px; border-bottom: 1px solid #343B45;"
                )
                self._layout.addWidget(heading)
                table = self._create_table(class_key, len(class_cars))
                self._layout.addWidget(table)
                self._headings_by_class[class_key] = heading
                self._tables_by_class[class_key] = table
            self._layout.addStretch(1)
            self._group_signature = signature

        for class_key in class_keys:
            class_cars = groups[class_key]
            known_positions = [
                car for car in class_cars if positions.get(car.car_id) is not None
            ]
            class_ranks = {
                car.car_id: index
                for index, car in enumerate(known_positions, start=1)
            }
            if len(known_positions) == len(class_cars):
                gaps = _gap_labels(tuple(class_cars), positions, track_length_m)
            else:
                gaps = {car.car_id: "—" for car in class_cars}

            self._headings_by_class[class_key].setText(
                f"{labels[class_key]}  ·  {len(class_cars)} coches"
            )
            self._update_table(
                self._tables_by_class[class_key],
                class_cars,
                class_ranks,
                gaps,
                fastest_id,
            )


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
