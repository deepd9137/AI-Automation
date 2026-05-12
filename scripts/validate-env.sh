#!/usr/bin/env bash
set -euo pipefail

REQUIRED_VARS=(
  "DATABASE_URL"
  "OPENAI_API_KEY"
  "JWT_SECRET"
)

MISSING=()

for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    MISSING+=("$var")
  fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
  echo "ERROR: Missing required environment variables:"
  for var in "${MISSING[@]}"; do
    echo "  - $var"
  done
  exit 1
fi

echo "All required environment variables are set."
