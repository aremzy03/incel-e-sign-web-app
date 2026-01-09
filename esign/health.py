"""
Health check endpoint for monitoring application status.

This module provides endpoints to check the health of various components
including database, Redis, and Celery connectivity.
"""

import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import connection
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def health_check(request):
    """
    Basic health check endpoint.
    
    Returns:
        JsonResponse: 200 OK with status information
    """
    return JsonResponse({
        'status': 'healthy',
        'service': 'e-sign-api'
    })


@require_http_methods(["GET"])
def health_detailed(request):
    """
    Detailed health check endpoint checking all services.
    
    Checks:
    - Database connectivity
    - Redis/Cache connectivity
    - Celery broker connectivity (if configured)
    
    Returns:
        JsonResponse: 200 OK if all services are healthy, 503 if any service is down
    """
    status = {
        'status': 'healthy',
        'service': 'e-sign-api',
        'checks': {}
    }
    overall_healthy = True
    
    # Check database
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        status['checks']['database'] = {
            'status': 'healthy',
            'engine': settings.DATABASES['default'].get('ENGINE', 'unknown')
        }
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}", exc_info=True)
        status['checks']['database'] = {
            'status': 'unhealthy',
            'error': str(e) if settings.DEBUG else 'Database connection failed'
        }
        overall_healthy = False
    
    # Check cache/Redis
    try:
        cache.set('health_check', 'ok', 10)
        result = cache.get('health_check')
        if result == 'ok':
            status['checks']['cache'] = {
                'status': 'healthy',
                'backend': settings.CACHES.get('default', {}).get('BACKEND', 'unknown')
            }
        else:
            raise Exception("Cache test failed")
    except Exception as e:
        logger.error(f"Cache health check failed: {str(e)}", exc_info=True)
        status['checks']['cache'] = {
            'status': 'unhealthy',
            'error': str(e) if settings.DEBUG else 'Cache connection failed'
        }
        # Cache is not critical for basic functionality
        # overall_healthy = False
    
    # Check Celery broker (if configured)
    try:
        from celery import current_app
        inspect = current_app.control.inspect()
        stats = inspect.stats()
        if stats:
            status['checks']['celery'] = {
                'status': 'healthy',
                'workers': len(stats)
            }
        else:
            status['checks']['celery'] = {
                'status': 'degraded',
                'warning': 'No Celery workers found'
            }
    except Exception as e:
        logger.warning(f"Celery health check failed: {str(e)}")
        status['checks']['celery'] = {
            'status': 'unknown',
            'warning': 'Celery check unavailable'
        }
        # Celery is not critical for basic functionality
    
    if not overall_healthy:
        status['status'] = 'degraded'
        return JsonResponse(status, status=503)
    
    return JsonResponse(status, status=200)


@require_http_methods(["GET"])
def sentry_debug(request):
    """
    Test endpoint that intentionally raises an exception so Sentry can capture it.

    Use this after configuring SENTRY_DSN to verify events appear in your Sentry project.
    """
    # This will be reported to Sentry as an unhandled error
    raise RuntimeError("Sentry debug endpoint triggered")

