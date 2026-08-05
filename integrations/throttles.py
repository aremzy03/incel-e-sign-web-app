"""
Rate throttles for integration endpoints.

Dedicated scope for the token-exchange endpoint so partner credential
attempts can be rate-limited independently of general anonymous traffic.
"""

from rest_framework.throttling import AnonRateThrottle


class IntegrationTokenThrottle(AnonRateThrottle):
    """
    Throttle POST /api/v1/integrations/token/ by client IP.

    Uses the ``integration_token`` DRF throttle scope (defaults to the same
    rate as ``auth`` when configured in settings).
    """

    scope = "integration_token"
