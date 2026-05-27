#!/bin/bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

echo "📋 Running ruff linter..."
ruff check tg_bot/ tests/ --output-format=github || {
    echo "❌ Linter failed."
    exit 1
}

echo "🔎 Running type check (strict on core)..."
mypy --strict tg_bot/domain/ tg_bot/application/ tg_bot/bot_services/ --ignore-missing-imports --no-error-summary || {
    echo "❌ Type check failed."
    exit 1
}

echo "🧪 Running tests with coverage..."
export PYTHONPATH="."
pytest tests/ --tb=short -q --cov=tg_bot/domain --cov=tg_bot/application --cov=tg_bot/bot_services --cov=services --cov=utils --cov-report=term-missing || {
    echo "❌ Tests or coverage failed."
    exit 1
}

echo ""
echo "✅ Phase 1 checks passed. Ready to commit."
exit 0