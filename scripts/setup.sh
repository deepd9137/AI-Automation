#!/usr/bin/env bash
set -euo pipefail

echo "==> AI Engagement Assistant — Dev Setup"

# Check dependencies
command -v python3 >/dev/null 2>&1 || { echo "Python 3.11+ required"; exit 1; }
command -v node >/dev/null 2>&1    || { echo "Node 20+ required"; exit 1; }
command -v docker >/dev/null 2>&1  || { echo "Docker required"; exit 1; }

# Copy .env if not present
if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> Created .env from .env.example — fill in your secrets"
fi

# Backend virtualenv + deps
echo "==> Installing backend dependencies"
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements-dev.txt
cd ..

# Frontend deps
echo "==> Installing frontend dependencies"
cd frontend
npm ci --silent
cd ..

# Pre-commit
echo "==> Installing pre-commit hooks"
cd backend
source .venv/bin/activate
pre-commit install
cd ..

echo ""
echo "✓ Setup complete."
echo "  Run: cd infrastructure && docker compose up"
echo "  Backend docs: http://localhost:8000/api/docs"
echo "  Frontend:     http://localhost:3000"
