"""
API views for first-party integrations.

Exposes token exchange so trusted partner apps can obtain a user-scoped JWT.
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.serializers import TokenExchangeSerializer
from integrations.services.ip_allowlist import get_client_ip
from integrations.services.token_exchange import (
    ClientIpNotAllowedError,
    InvalidClientError,
    exchange_token,
)
from integrations.services.users import UserInactiveError, UserNotFoundError
from integrations.throttles import IntegrationTokenThrottle

logger = logging.getLogger(__name__)


class TokenExchangeView(APIView):
    """
    Exchange integration client credentials + user email for SimpleJWT tokens.

    POST /api/v1/integrations/token/

    Auth: AllowAny (credentials in body). Throttled via integration_token scope.
    When Integration.allowed_cidrs is non-empty, requests from non-matching
    IPs receive 403.
    """

    permission_classes = [AllowAny]
    throttle_classes = [IntegrationTokenThrottle]

    def post(self, request):
        """
        Validate the request body, run token exchange, and return JWT pair.
        """
        serializer = TokenExchangeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Invalid request",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        try:
            result = exchange_token(
                client_id=data["client_id"],
                client_secret=data["client_secret"],
                email=data["email"],
                full_name=data.get("full_name") or None,
                external_user_id=data.get("external_user_id") or None,
                client_ip=get_client_ip(request),
                request=request,
            )
        except InvalidClientError:
            return Response(
                {
                    "status": "error",
                    "message": "Invalid client credentials",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except ClientIpNotAllowedError:
            return Response(
                {
                    "status": "error",
                    "message": "Client IP is not allowed for this integration",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except UserNotFoundError:
            return Response(
                {
                    "status": "error",
                    "message": "User not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except UserInactiveError:
            return Response(
                {
                    "status": "error",
                    "message": "User account is inactive",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except Exception:
            # Do not leak secrets; avoid including request body in logs.
            logger.exception("Unexpected error during integration token exchange")
            return Response(
                {
                    "status": "error",
                    "message": "Unable to issue token",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "status": "success",
                "message": "Token issued successfully",
                "data": result,
            },
            status=status.HTTP_200_OK,
        )
