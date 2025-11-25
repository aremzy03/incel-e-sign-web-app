#!/usr/bin/env bash
# Exit on error
set -o errexit

# Build commands for Render deployment
echo "Building application..."

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput || true

# Run migrations
echo "Running database migrations..."
python manage.py migrate --noinput || true

echo "Build complete!"

