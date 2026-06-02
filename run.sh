#!/usr/bin/env bash
# Arranca JMFConta usando el venv local.
set -e
cd "$(dirname "$0")"
PYTHONPATH=src ./.venv/bin/python -m jmfconta "$@"
