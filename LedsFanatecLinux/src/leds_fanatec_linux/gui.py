"""GUI Qt para perfiles Fanatec, con una única ruta de escritura al hardware."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QColorDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .commands import send_test_command
from .models import FLAG_NAMES, LedProfile, default_profile
from .patterns import FLAG_ZONES, FlagPattern, RPM_ZONES
from .profiles import ProfileStore

STATUS_PATH = Path.home() / ".local/state/LedsFanatecLinux/status.json"
FLAG_LABELS = {
    "green": "Verde",
    "yellow": "Amarilla",
    "double_yellow": "Doble amarilla",
    "local_yellow": "Amarilla local",
    "red": "Roja",
    "blue": "Azul",
    "black": "Negra",
    "white": "Blanca",
    "checkered": "A cuadros",
    "penalty": "Penalización",
    "vsc": "VSC",
    "safety_car": "Safety car",
}
FLAG_DETAILS = {
    "green": "6 LED verdes durante 3 s",
    "yellow": "6 LED amarillos fijos",
    "double_yellow": "Alterna el bloque izquierdo y derecho",
    "local_yellow": "Un LED amarillo recorre las 6 posiciones",
    "red": "6 LED rojos fijos",
    "blue": "6 LED azules fijos",
    "black": "Patrón alternado blanco/apagado",
    "white": "6 LED blancos fijos",
    "checkered": "Patrón alternado; cambia de sentido",
    "penalty": "Tres destellos blancos",
    "vsc": "Luz ámbar itinerante",
    "safety_car": "Amarillo con extremos blancos",
}

STYLESHEET = """
QWidget {
    background: #0B0D11;
    color: #F1F3F5;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 13px;
}
QLabel { background-color: transparent; }
QFrame#card {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #191E25, stop:1 #12151A);
    border: 1px solid #2B313A;
    border-radius: 10px;
}
QFrame#flagRow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #191E25, stop:1 #12151A);
    border: 1px solid #2B313A;
    border-radius: 9px;
}
QFrame#ledCapsule {
    background: #0D1014;
    border: 1px solid #343B45;
    border-radius: 14px;
}
QLabel#title { font-size: 29px; font-weight: 800; color: #F5F6F7; }
QLabel#subtitle { color: #FF7A1A; font-size: 9px; font-weight: 700; letter-spacing: 2px; }
QLabel#muted { color: #9BA3AD; }
QLabel#section { font-size: 12px; font-weight: 750; color: #D2D7DE; letter-spacing: 1px; }
QPushButton, QComboBox, QLineEdit {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #272D35, stop:1 #1A1F26);
    border: 1px solid #3A424D;
    border-radius: 6px;
    padding: 8px 11px;
    min-height: 18px;
}
QPushButton:hover, QComboBox:hover { border-color: #FF6A00; }
QPushButton:checked, QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #71320F, stop:1 #25201D);
    border-color: #FF6A00;
}
QPushButton:disabled {
    color: #67717D;
    background: #15191F;
    border-color: #252D37;
}
QComboBox::drop-down { border: 0; width: 22px; }
QComboBox QAbstractItemView {
    background: #15191F;
    selection-background-color: #71320F;
}
QTabWidget::pane {
    border: 1px solid #2B313A;
    border-radius: 9px;
    top: -1px;
}
QTabBar::tab {
    background: #171B21;
    color: #9BA3AD;
    border: 1px solid #2B313A;
    padding: 10px 24px;
    margin-right: 5px;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    font-weight: 700;
}
QTabBar::tab:selected {
    color: #FFFFFF;
    border-color: #FF6A00;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #71320F, stop:1 #25201D);
}
QScrollArea { border: 0; }
"""


class FanatecWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LedsFanatecLinux")
        self.setMinimumSize(980, 720)
        self.resize(1120, 820)
        self.store = ProfileStore()
        self.store.ensure_default()
        self.profile: LedProfile | None = None
        self._selected_id: str | None = None
        self._active_id: str | None = None
        self._locked = False
        self._loading = False
        self._editable_widgets: list[QWidget] = []
        self._test_widgets: list[QWidget] = []
        self._hardware_ready = False
        self._rpm_buttons: list[QPushButton] = []
        self._max_buttons: list[QPushButton] = []
        self._flag_buttons: dict[str, QPushButton] = {}
        self._build_ui()
        self._load_active_profile()
        self._refresh_status()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_status)
        self.timer.start(400)

    def _build_ui(self) -> None:
        root = QWidget()
        page = QVBoxLayout(root)
        page.setContentsMargins(24, 20, 24, 18)
        page.setSpacing(14)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel("Fanatec LED Studio")
        title.setObjectName("title")
        subtitle = QLabel("PERFILES DE VOLANTE  /  CONTROL DE LEDS")
        subtitle.setObjectName("subtitle")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch(1)
        self.lock_status = QLabel("Conectando al servicio…")
        self.lock_status.setObjectName("muted")
        self.lock_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.lock_status)
        page.addLayout(header)

        profile_card, profile_layout = self._card()
        profile_layout.addWidget(self._section_label("Perfil activo"))
        row = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.currentIndexChanged.connect(self._profile_selected)
        row.addWidget(self.profile_combo, 1)
        self.new_button = self._button("Nuevo", self._new_profile)
        self.activate_button = self._button("Activar", self._activate_profile, primary=True)
        self.delete_button = self._button("Borrar", self._delete_profile)
        self.import_button = self._button("Importar", self._import_profile)
        self.export_button = self._button("Exportar", self._export_profile)
        for button in (
            self.new_button,
            self.activate_button,
            self.delete_button,
            self.import_button,
            self.export_button,
        ):
            row.addWidget(button)
        profile_layout.addLayout(row)
        details = QHBoxLayout()
        details.addWidget(QLabel("Nombre"))
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._save_profile)
        details.addWidget(self.name_edit, 1)
        details.addWidget(QLabel("Secuencia RPM"))
        self.sequence_combo = QComboBox()
        self.sequence_combo.addItem("Izquierda a derecha", "left_to_right")
        self.sequence_combo.addItem("Extremos al centro", "outer_to_center")
        self.sequence_combo.currentIndexChanged.connect(self._save_profile)
        details.addWidget(self.sequence_combo)
        details.addWidget(QLabel("Periodo blink RPM MAX"))
        self.blink_spin = QSpinBox()
        self.blink_spin.setRange(100, 4000)
        self.blink_spin.setSingleStep(50)
        self.blink_spin.setSuffix(" ms")
        self.blink_spin.setToolTip("Periodo completo de parpadeo; 500 ms equivalen a 2 Hz.")
        self.blink_spin.valueChanged.connect(self._save_profile)
        details.addWidget(self.blink_spin)
        self.blink_hz_label = self._muted_label("2.0 Hz")
        self.blink_spin.valueChanged.connect(self._update_blink_frequency)
        details.addWidget(self.blink_hz_label)
        self.save_button = self._button("Guardar perfil", self._save_profile)
        details.addWidget(self.save_button)
        profile_layout.addLayout(details)
        page.addWidget(profile_card)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_rpm_tab(), "RPM")
        self.tabs.addTab(self._build_flags_tab(), "Banderas")
        page.addWidget(self.tabs, 1)

        self.setCentralWidget(root)

    def _build_rpm_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(14)
        normal_card, normal_layout = self._card()
        normal_layout.addWidget(self._section_label("RPM del motor"))
        normal_layout.addWidget(self._muted_label("Nueve zonas RGB, cada una editable."))
        normal_layout.addLayout(self._color_row(self._rpm_buttons, self._choose_rpm_color))
        rpm_test_button = self._button(
            "Probar secuencia RPM", lambda: self._send_test("test_rpm")
        )
        self._test_widgets.append(rpm_test_button)
        normal_layout.addWidget(rpm_test_button)
        max_card, max_layout = self._card()
        max_layout.addWidget(self._section_label("RPM MAX"))
        max_layout.addWidget(
            self._muted_label(
                "Se activa al alcanzar el max_rpm publicado por el simulador; sin ese dato, "
                "las RPM permanecen apagadas."
            )
        )
        max_layout.addLayout(self._color_row(self._max_buttons, self._choose_max_color))
        max_test_button = self._button(
            "Probar RPM MAX", lambda: self._send_test("test_rpm_max")
        )
        self._test_widgets.append(max_test_button)
        max_layout.addWidget(max_test_button)
        layout.addWidget(normal_card)
        layout.addWidget(max_card)
        layout.addStretch(1)
        return page

    def _build_flags_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(12, 14, 12, 12)
        outer.addWidget(
            self._muted_label(
                "Vista del aro: tres LED a la izquierda y tres a la derecha. Colores y "
                "animaciones de bandera fijos; «Probar» funciona aunque el simulador esté cerrado."
            )
        )
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        rows = QVBoxLayout(content)
        rows.setContentsMargins(0, 8, 0, 0)
        rows.setSpacing(7)
        for flag in FLAG_NAMES:
            row = QFrame()
            row.setObjectName("flagRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 8, 12, 8)
            row_layout.setSpacing(14)

            pattern = FlagPattern().calculate_test(flag, now=0.0)
            active_color = next(
                (pattern[zone] for zone in FLAG_ZONES if pattern[zone] != (0, 0, 0)),
                (100, 110, 122),
            )
            marker = QLabel("●")
            marker.setStyleSheet(
                f"color: rgb({active_color[0]}, {active_color[1]}, {active_color[2]});"
                "font-size: 19px;"
            )
            row_layout.addWidget(marker)
            flag_name = QVBoxLayout()
            name_label = self._section_label(FLAG_LABELS[flag])
            name_label.setMinimumWidth(140)
            description = self._muted_label(FLAG_DETAILS[flag])
            description.setMinimumWidth(230)
            flag_name.addWidget(name_label)
            flag_name.addWidget(description)
            row_layout.addLayout(flag_name, 1)

            preview = QHBoxLayout()
            preview.setSpacing(8)
            preview.addWidget(self._flag_led_group(pattern, FLAG_ZONES[:3], "IZQ"))
            preview.addWidget(self._flag_led_group(pattern, FLAG_ZONES[3:], "DER"))
            row_layout.addLayout(preview)

            test_button = self._button(
                "Probar",
                lambda _checked=False, selected=flag: self._send_test(
                    "test_flag", selected
                ),
            )
            test_button.setMinimumWidth(100)
            self._test_widgets.append(test_button)
            row_layout.addWidget(test_button)
            rows.addWidget(row)
            self._flag_buttons[flag] = test_button
        rows.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        return page

    @staticmethod
    def _flag_led_group(pattern, zones: tuple[str, ...], side: str) -> QWidget:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        label = QLabel(side)
        label.setObjectName("muted")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        capsule = QFrame()
        capsule.setObjectName("ledCapsule")
        leds = QHBoxLayout(capsule)
        leds.setContentsMargins(7, 5, 7, 5)
        leds.setSpacing(5)
        for zone in zones:
            dot = QLabel()
            dot.setFixedSize(17, 17)
            color = pattern[zone]
            if color == (0, 0, 0):
                color_css = "#303945"
            else:
                color_css = f"rgb({color[0]}, {color[1]}, {color[2]})"
            dot.setStyleSheet(
                f"border-radius: 8px; background: {color_css};"
                "border: 1px solid #495563;"
            )
            dot.setToolTip(zone)
            leds.addWidget(dot)
        layout.addWidget(capsule)
        return group

    @staticmethod
    def _card() -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        return frame, layout

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("section")
        return label

    @staticmethod
    def _muted_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("muted")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _button(text: str, action, *, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(action)
        return button

    def _color_row(self, buttons: list[QPushButton], action) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(9)
        for index in range(9):
            button = QPushButton(str(index + 1))
            button.setFixedSize(68, 52)
            button.setToolTip(f"LED {index + 1} — clic para cambiar el color")
            button.clicked.connect(lambda _checked=False, position=index: action(position))
            row.addWidget(button)
            buttons.append(button)
            self._editable_widgets.append(button)
        row.addStretch(1)
        return row

    def _refresh_profiles(
        self, selected_id: str | None = None, *, active_id: str | None = None
    ) -> None:
        profiles = self.store.list_profiles()
        self._active_id = active_id or self.store.active_profile_id()
        wanted = selected_id or self._selected_id or self._active_id
        self._loading = True
        self.profile_combo.clear()
        for profile in profiles:
            active_mark = "  • ACTIVO" if profile.profile_id == self._active_id else ""
            self.profile_combo.addItem(profile.name + active_mark, profile.profile_id)
        selected_index = self.profile_combo.findData(wanted)
        if selected_index < 0 and self.profile_combo.count():
            selected_index = self.profile_combo.findData(self._active_id)
        self.profile_combo.setCurrentIndex(selected_index)
        self._loading = False
        self._selected_id = self.profile_combo.currentData()

    def _load_active_profile(self) -> None:
        self._refresh_profiles(self.store.active_profile_id())
        self._profile_selected(self.profile_combo.currentIndex())

    def _profile_selected(self, index: int) -> None:
        if self._loading or index < 0:
            return
        profile_id = self.profile_combo.itemData(index)
        if not profile_id:
            return
        self._selected_id = profile_id
        self.profile = self.store.get(profile_id)
        self._load_profile_widgets()
        self._update_activation_button()

    def _load_profile_widgets(self) -> None:
        if self.profile is None:
            return
        self._loading = True
        self.name_edit.setText(self.profile.name)
        self.sequence_combo.setCurrentIndex(
            self.sequence_combo.findData(self.profile.sequence)
        )
        self.blink_spin.setValue(self.profile.max_rpm_blink_ms)
        self._update_blink_frequency(self.profile.max_rpm_blink_ms)
        for button, color in zip(self._rpm_buttons, self.profile.rpm_colors):
            self._set_color_button(button, color)
        for button, color in zip(self._max_buttons, self.profile.max_rpm_colors):
            self._set_color_button(button, color)
        self._loading = False

    @staticmethod
    def _set_color_button(button: QPushButton, color: str) -> None:
        button.setProperty("led_color", color)
        button.setStyleSheet(
            "QPushButton { background: "
            f"{color}; color: #0B0D11; font-weight: 700; border: 2px solid #F1F3F5; "
            "border-radius: 8px; }"
            "QPushButton:disabled { border-color: #59636E; }"
        )

    def _edited_profile(self) -> LedProfile:
        if self.profile is None:
            raise ValueError("No hay ningún perfil seleccionado.")
        name = self.name_edit.text().strip()
        return LedProfile(
            profile_id=self.profile.profile_id,
            name=name,
            rpm_colors=tuple(
                button.property("led_color") or color
                for button, color in zip(self._rpm_buttons, self.profile.rpm_colors)
            ),
            max_rpm_colors=tuple(
                button.property("led_color") or color
                for button, color in zip(self._max_buttons, self.profile.max_rpm_colors)
            ),
            sequence=self.sequence_combo.currentData(),
            max_rpm_blink_ms=self.blink_spin.value(),
        )

    def _save_profile(self, *_args) -> None:
        if self._loading or self.profile is None:
            return
        if self._locked:
            self._show_warning("Edición bloqueada", "El coche debe estar detenido para editar perfiles.")
            self._load_profile_widgets()
            return
        try:
            self.profile = self._edited_profile()
            self.store.save(self.profile)
            self._refresh_profiles(self.profile.profile_id)
            self._load_profile_widgets()
            self._update_activation_button()
        except (OSError, ValueError) as error:
            self._show_warning("No se pudo guardar el perfil", str(error))
            self._load_profile_widgets()

    def _choose_color(self, position: int, *, max_rpm: bool) -> None:
        if self.profile is None or self._locked:
            return
        buttons = self._max_buttons if max_rpm else self._rpm_buttons
        attribute = "max_rpm_colors" if max_rpm else "rpm_colors"
        colors = list(getattr(self.profile, attribute))
        initial = QColor(buttons[position].property("led_color") or colors[position])
        selected = QColorDialog.getColor(initial, self, "Color del LED")
        if not selected.isValid():
            return
        color = selected.name().upper()
        buttons[position].setProperty("led_color", color)
        self._set_color_button(buttons[position], color)
        colors[position] = color
        try:
            self.profile = LedProfile(
                profile_id=self.profile.profile_id,
                name=self.name_edit.text().strip(),
                rpm_colors=tuple(
                    colors if not max_rpm else self._current_colors(self._rpm_buttons, self.profile.rpm_colors)
                ),
                max_rpm_colors=tuple(
                    colors if max_rpm else self._current_colors(self._max_buttons, self.profile.max_rpm_colors)
                ),
                sequence=self.sequence_combo.currentData(),
                max_rpm_blink_ms=self.blink_spin.value(),
            )
            self.store.save(self.profile)
            self._refresh_profiles(self.profile.profile_id)
            self._update_activation_button()
        except (OSError, ValueError) as error:
            self._show_warning("No se pudo guardar el color", str(error))
            self._load_profile_widgets()

    @staticmethod
    def _current_colors(buttons: list[QPushButton], original: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(button.property("led_color") or color for button, color in zip(buttons, original))

    def _choose_rpm_color(self, position: int) -> None:
        self._choose_color(position, max_rpm=False)

    def _choose_max_color(self, position: int) -> None:
        self._choose_color(position, max_rpm=True)

    def _update_blink_frequency(self, period_ms: int) -> None:
        hz = 2000 / period_ms
        rendered = f"{hz:.2f}".rstrip("0").rstrip(".")
        self.blink_hz_label.setText(f"{rendered} Hz")

    def _update_activation_button(self) -> None:
        is_active = self.profile is not None and self.profile.profile_id == self._active_id
        self.activate_button.setText("Perfil activo" if is_active else "Activar")
        self.activate_button.setEnabled(not self._locked and not is_active)

    def _activate_profile(self) -> None:
        if self.profile is None or self._locked:
            return
        try:
            self.store.activate(self.profile.profile_id)
            self._active_id = self.profile.profile_id
            self._refresh_profiles(self.profile.profile_id)
            self._update_activation_button()
        except (OSError, ValueError) as error:
            self._show_warning("No se pudo activar el perfil", str(error))

    def _new_profile(self) -> None:
        if self._locked:
            return
        profile = default_profile("Perfil nuevo")
        try:
            self.store.save(profile)
            self._refresh_profiles(profile.profile_id)
            self._profile_selected(self.profile_combo.currentIndex())
        except (OSError, ValueError) as error:
            self._show_warning("No se pudo crear el perfil", str(error))

    def _delete_profile(self) -> None:
        if self.profile is None or self._locked:
            return
        if QMessageBox.question(
            self,
            "Borrar perfil",
            f"¿Borrar «{self.profile.name}»? Esta acción no se puede deshacer.",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            deleting = self.profile.profile_id
            self.store.delete(deleting)
            self._refresh_profiles(self._active_id)
            self._profile_selected(self.profile_combo.currentIndex())
        except (OSError, ValueError) as error:
            self._show_warning("No se pudo borrar el perfil", str(error))

    def _import_profile(self) -> None:
        if self._locked:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Importar perfil", str(Path.home()), "Perfiles JSON (*.json)"
        )
        if not filename:
            return
        try:
            profile = self.store.import_file(Path(filename))
            self._refresh_profiles(profile.profile_id)
            self._profile_selected(self.profile_combo.currentIndex())
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self._show_warning("No se pudo importar el perfil", str(error))

    def _export_profile(self) -> None:
        if self.profile is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar perfil",
            str(Path.home() / f"{self.profile.name}.json"),
            "Perfiles JSON (*.json)",
        )
        if not filename:
            return
        try:
            self.store.export_file(self.profile.profile_id, Path(filename))
        except (OSError, ValueError) as error:
            self._show_warning("No se pudo exportar el perfil", str(error))

    def _send_test(self, action: str, flag: str | None = None) -> None:
        if self._locked:
            self._show_warning("Prueba bloqueada", "El coche debe estar detenido.")
            return
        if not self._hardware_ready:
            self._show_warning(
                "Volante no disponible",
                "Conecta el volante y comprueba que el servicio esté activo.",
            )
            return
        try:
            send_test_command(action, flag)
            self.lock_status.setText("PRUEBA ENVIADA AL VOLANTE…")
            self.lock_status.setStyleSheet("color: #FF8A3D; font-weight: 700;")
        except (OSError, ValueError) as error:
            self._show_warning("No se pudo iniciar la prueba", str(error))

    def _set_editing_enabled(self, enabled: bool) -> None:
        for widget in self._editable_widgets:
            widget.setEnabled(enabled)
        for widget in (
            self.profile_combo,
            self.name_edit,
            self.sequence_combo,
            self.blink_spin,
            self.new_button,
            self.activate_button,
            self.delete_button,
            self.import_button,
            self.save_button,
        ):
            widget.setEnabled(enabled)
        for button in self._test_widgets:
            button.setEnabled(enabled and self._hardware_ready)
        for button in self._flag_buttons.values():
            button.setEnabled(enabled and self._hardware_ready)
        self.export_button.setEnabled(self.profile is not None)
        self._update_activation_button()

    def _refresh_status(self) -> None:
        try:
            status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            status = {}
        except (OSError, json.JSONDecodeError) as error:
            self.lock_status.setText(f"Error leyendo estado del servicio: {error}")
            self.lock_status.setStyleSheet("color: #F87171;")
            return
        if not isinstance(status, dict):
            self.lock_status.setText("El estado del servicio no es válido.")
            self.lock_status.setStyleSheet("color: #F87171;")
            return
        self._locked = status.get("profile_locked") is True
        self._hardware_ready = status.get("hardware") == "ready"
        applied_profile_id = status.get("profile_id")
        if (
            isinstance(applied_profile_id, str)
            and applied_profile_id != self._active_id
        ):
            self._refresh_profiles(
                applied_profile_id, active_id=applied_profile_id
            )
            self._profile_selected(self.profile_combo.currentIndex())
        self._set_editing_enabled(not self._locked)
        if self._locked:
            self.lock_status.setText("EDICIÓN BLOQUEADA · VEHÍCULO EN MOVIMIENTO")
            self.lock_status.setStyleSheet("color: #FBBF24; font-weight: 700;")
        elif status.get("running"):
            test = status.get("test")
            if isinstance(test, dict):
                self.lock_status.setText("PRUEBA DE LEDS EN CURSO")
                self.lock_status.setStyleSheet(
                    "color: #FF8A3D; font-weight: 700;"
                )
            elif self._hardware_ready:
                self.lock_status.setText("SERVICIO ACTIVO · PERFILES Y PRUEBAS DISPONIBLES")
                self.lock_status.setStyleSheet("color: #4ADE80; font-weight: 700;")
            else:
                self.lock_status.setText("SERVICIO ACTIVO · VOLANTE NO DETECTADO")
                self.lock_status.setStyleSheet("color: #FBBF24; font-weight: 700;")
        else:
            self.lock_status.setText("SERVICIO NO DISPONIBLE")
            self.lock_status.setStyleSheet("color: #F87171; font-weight: 700;")

    @staticmethod
    def _show_warning(title: str, message: str) -> None:
        QMessageBox.warning(None, title, message)


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    window = FanatecWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
