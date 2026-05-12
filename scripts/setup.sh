#!/usr/bin/env bash
set -euo pipefail

echo "==> AI Engagement Assistant — Dev Setup"

# Check dependencies
command -v uv >/dev/null 2>&1    || { echo "uv required — install: curl -Ls https://astral.sh/uv/install.sh | sh"; exit 1; }
command -v node >/dev/null 2>&1  || { echo "Node 20+ required"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Docker required"; exit 1; }

# Copy .env if not present
if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> Created .env from .env.example — fill in your secrets"
fi

# Backend virtualenv + deps (via uv — fast)
echo "==> Creating backend venv with Python 3.11 (uv)"
uv venv backend/.venv --python 3.11
echo "==> Installing backend dependencies (uv)"
uv pip install -r backend/requirements-dev.txt --python backend/.venv/bin/python

# Frontend deps
echo "==> Installing frontend dependencies"
cd frontend && npm ci --silent && cd ..

# Pre-commit
echo "==> Installing pre-commit hooks"
backend/.venv/bin/pre-commit install

echo ""
echo "✓ Setup complete."
echo "  Run: cd infrastructure && docker compose up"
echo "  Backend docs: http://localhost:8000/api/docs"
echo "  Frontend:     http://localhost:3000"
