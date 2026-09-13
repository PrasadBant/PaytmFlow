#!/usr/bin/env bash
set -e

echo "Running database migrations..."
alembic upgrade head

if [ "$SEED_DEMO_ON_STARTUP" = "true" ] || [ "$APP_ENV" = "demo" ]; then
    echo "Seeding demo journeys and initial state..."
    python -m app.db.seed || echo "Seed warning (may already be populated)"
fi

echo "Starting PaytmFlow API application server..."
exec "$@"
