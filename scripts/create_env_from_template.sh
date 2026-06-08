#!/usr/bin/env bash
# Copy .env.example to .env if .env does not already exist.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "${SCRIPT_DIR}")"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  echo ".env already exists at ${ROOT_DIR}/.env — not overwriting."
  echo "Delete it first if you want a fresh copy from .env.example."
  exit 0
fi

cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
echo "Created ${ROOT_DIR}/.env from .env.example"
echo "Edit it and fill in your Amazon credentials and Alexa device name."
