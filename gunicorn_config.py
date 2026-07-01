"""
Gunicorn configuration for production deployment.

This file provides production-ready settings for Gunicorn WSGI server.
Use it by running: gunicorn -c gunicorn_config.py esign.wsgi:application
"""

import os

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
backlog = 2048

# Worker processes
# Default to 3 on shared PostgreSQL (CapRover). Override via GUNICORN_WORKERS.
# Avoid cpu_count() * 2 + 1 — it opens too many DB connections per container.
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = "-"  # Log to stdout (Render captures stdout)
errorlog = "-"   # Log to stderr (Render captures stderr)
loglevel = os.environ.get("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "esign-app"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (if needed - Render handles SSL termination)
# keyfile = None
# certfile = None

# Graceful timeout for worker restart
graceful_timeout = 30

