#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_NAME="leds-fanatec-linux.service"
UNIT_DIR="$HOME/.config/systemd/user"
PYTHON="$(command -v python3)"

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "Se requiere Python 3.11 o posterior." >&2
    exit 1
fi

if systemctl --user is-active --quiet fanatec-leds.service; then
    echo "El servicio legado fanatec-leds.service está activo; deténlo antes de instalar el nuevo servicio." >&2
    exit 1
fi

mkdir -p "$UNIT_DIR"
sed \
    -e "s|@PROJECT_ROOT@|$ROOT|g" \
    -e "s|@PYTHON@|$PYTHON|g" \
    "$ROOT/systemd/$UNIT_NAME" > "$UNIT_DIR/$UNIT_NAME"
systemctl --user daemon-reload
systemctl --user enable --now "$UNIT_NAME"
if command -v loginctl >/dev/null 2>&1; then
    if ! loginctl enable-linger "$USER"; then
        echo "Aviso: no se pudo habilitar linger; el servicio arrancará al iniciar sesión." >&2
    fi
fi

echo "Servicio instalado y habilitado para el usuario actual."
echo "Estado: systemctl --user status $UNIT_NAME"
