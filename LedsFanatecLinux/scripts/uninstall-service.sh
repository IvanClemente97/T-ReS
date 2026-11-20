#!/usr/bin/env bash
set -euo pipefail

UNIT_NAME="leds-fanatec-linux.service"
UNIT_FILE="$HOME/.config/systemd/user/$UNIT_NAME"

systemctl --user disable --now "$UNIT_NAME" || true
rm -f "$UNIT_FILE"
systemctl --user daemon-reload

echo "Servicio detenido y unidad de usuario retirada. El proyecto y los perfiles se conservan."
