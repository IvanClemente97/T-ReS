#!/bin/sh
APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONPATH="$APP_DIR/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m t_res "$@"
