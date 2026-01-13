FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies
# - build-essential, libpq-dev: required for some Python deps (e.g. psycopg2)
# - libreoffice: required for Word → PDF conversion (documents upload)
# - locales, fonts, gosu, netcat-openbsd: misc tooling and better UX
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      build-essential \
      libpq-dev \
      libreoffice \
      locales \
      fonts-dejavu-core \
      curl \
      netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Python dependencies layer
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Make entrypoint script executable
RUN chmod +x entrypoint.sh

# Ensure static and media directories exist (can be overridden/mounted)
ENV STATIC_ROOT=/app/staticfiles \
    MEDIA_ROOT=/app/media \
    DJANGO_SETTINGS_MODULE=esign.settings

RUN mkdir -p "${STATIC_ROOT}" "${MEDIA_ROOT}" && \
    chown -R appuser:appuser /app

USER appuser

# Collect static files during build for production images
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

# Default environment values (override in real deployments)
ENV PORT=8000 \
    DEBUG=False

# Entrypoint allows role selection (web / worker) and optional migrations
ENTRYPOINT ["./entrypoint.sh"]

# Default command: run Gunicorn web server
CMD ["web"]

