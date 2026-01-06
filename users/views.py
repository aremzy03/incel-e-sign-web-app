from urllib.parse import urlencode, urlparse

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserSerializer,
    UserSearchSerializer,
    UserProfileSerializer,
)
from envelopes.models import Envelope
from envelopes.serializers import EnvelopeSerializer


def _sanitize_next_path(raw_next: str | None) -> str:
    """
    Ensure the `next` path used in OAuth flow is a safe, relative URL.

    - Disallows absolute URLs (with scheme or netloc)
    - Forces a leading slash
    - Preserves query string and fragment for relative paths
    """
    if not raw_next:
        return "/"

    parsed = urlparse(raw_next)

    # Reject absolute URLs or protocol-relative URLs
    if parsed.scheme or parsed.netloc:
        return "/"

    path = parsed.path or "/"
    if not path.startswith("/"):
        path = "/" + path

    # Rebuild relative URL with query and fragment if present
    safe_next = path
    if parsed.query:
        safe_next += f"?{parsed.query}"
    if parsed.fragment:
        safe_next += f"#{parsed.fragment}"

    return safe_next


# Create your views here.

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            data = UserSerializer(user).data
            # Send email confirmation asynchronously (basic placeholder)
            try:
                from notifications.tasks import send_email_confirmation_task
                token = signing.dumps({"uid": str(user.id)})
                link = f"{settings.FRONTEND_BASE_URL}/confirm-email?token={token}"
                send_email_confirmation_task.delay(user.email, link, user.full_name)
            except Exception:
                pass
            return Response({"status": "success", "message": "Registered successfully", "data": data}, status=status.HTTP_201_CREATED)
        return Response({"status": "error", "message": "Validation error", "data": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": "error", "message": "Invalid credentials", "data": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)
        return Response({
            "status": "success",
            "message": "Login successful",
            "data": {
                "access": str(refresh.access_token),
                "refresh": str(refresh)
            }
        }, status=status.HTTP_200_OK)


class GoogleOAuthLoginView(APIView):
    """
    Starts the Google OAuth 2.0 flow by redirecting the user to Google's consent screen.

    Frontend should redirect the browser to this endpoint, e.g.:
    GET /api/auth/google/login/?next=/dashboard
    """

    permission_classes = [AllowAny]

    def get(self, request):
        client_id = settings.GOOGLE_OAUTH_CLIENT_ID
        if not client_id:
            return Response(
                {
                    "status": "error",
                    "message": "Google OAuth is not configured on the server.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Where Google will redirect back to on this backend
        callback_url = request.build_absolute_uri(
            reverse("auth-google-callback")
        )

        # Optional 'next' parameter to redirect the user after login
        raw_next = request.query_params.get("next") or "/"
        next_path = _sanitize_next_path(raw_next)
        state_payload = {"next": next_path}
        state = signing.dumps(state_payload)

        params = {
            "client_id": client_id,
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "include_granted_scopes": "true",
            "state": state,
            "prompt": "consent",
        }

        google_auth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
        )
        return redirect(google_auth_url)


class GoogleOAuthCallbackView(APIView):
    """
    Handles the redirect back from Google.

    - Exchanges the authorization code for tokens
    - Retrieves the user's profile
    - Creates or fetches the local user
    - Returns JWT access/refresh tokens to the frontend via redirect
    """

    permission_classes = [AllowAny]

    def get(self, request):
        # Extract and validate state first to get next_path; required for CSRF protection
        state = request.query_params.get("state")
        next_path = "/"

        if not state:
            # Missing state – treat as invalid OAuth attempt
            return self._redirect_to_frontend(
                status_param="error",
                next_path=next_path,
                message="Missing state parameter from Google OAuth callback.",
            )

        try:
            state_data = signing.loads(state, max_age=600)
            next_path = _sanitize_next_path(state_data.get("next"))
        except Exception:
            # Invalid or expired state – reject the callback
            return self._redirect_to_frontend(
                status_param="error",
                next_path=next_path,
                message="Invalid or expired login state. Please try signing in with Google again.",
            )

        error = request.query_params.get("error")
        if error:
            return self._redirect_to_frontend(
                status_param="error",
                next_path=next_path,
                message=f"Google OAuth error: {error}",
            )

        code = request.query_params.get("code")
        if not code:
            return self._redirect_to_frontend(
                status_param="error",
                next_path=next_path,
                message="Missing authorization code from Google OAuth callback.",
            )

        client_id = settings.GOOGLE_OAUTH_CLIENT_ID
        client_secret = settings.GOOGLE_OAUTH_CLIENT_SECRET
        if not client_id or not client_secret:
            return self._redirect_to_frontend(
                status_param="error",
                next_path=next_path,
                message="Google OAuth is not configured on the server.",
            )

        token_endpoint = "https://oauth2.googleapis.com/token"
        callback_url = request.build_absolute_uri(
            reverse("auth-google-callback")
        )

        token_data = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": callback_url,
            "grant_type": "authorization_code",
        }

        try:
            token_resp = requests.post(token_endpoint, data=token_data, timeout=10)
            token_resp.raise_for_status()
            token_json = token_resp.json()
        except Exception:
            return self._redirect_to_frontend(
                status_param="error",
                next_path=next_path,
                message="Failed to exchange code for tokens with Google.",
            )

        id_token = token_json.get("id_token")
        access_token = token_json.get("access_token")
        if not id_token:
            return self._redirect_to_frontend(
                status_param="error",
                next_path=next_path,
                message="Missing id_token in Google response.",
            )

        # Validate and decode id_token using Google's tokeninfo endpoint
        try:
            info_resp = requests.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
                timeout=10,
            )
            info_resp.raise_for_status()
            user_info = info_resp.json()
        except Exception:
            return self._redirect_to_frontend(
                status_param="error",
                next_path=next_path,
                message="Failed to validate Google id_token.",
            )

        email = user_info.get("email")
        email_verified = user_info.get("email_verified") in (True, "true", "1")
        full_name = user_info.get("name") or ""

        if not email or not email_verified:
            return self._redirect_to_frontend(
                status_param="error",
                next_path=next_path,
                message="Google account email is missing or not verified.",
            )

        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "full_name": full_name or email,
                "is_active": True,
            },
        )

        if not user.is_active:
            # If the account exists but is inactive, do not allow login
            return self._redirect_to_frontend(
                status_param="error",
                next_path=next_path,
                message="This account is inactive.",
            )

        refresh = RefreshToken.for_user(user)
        access = refresh.access_token

        # Redirect to the frontend with JWT tokens in the query string
        return self._redirect_to_frontend(
            status_param="success",
            next_path=next_path,
            access=str(access),
            refresh=str(refresh),
        )

    def _redirect_to_frontend(
        self,
        status_param: str,
        message: str | None = None,
        next_path: str = "/",
        access: str | None = None,
        refresh: str | None = None,
    ):
        """
        Helper to build a redirect URL back to the frontend app.
        """
        base_frontend = settings.FRONTEND_BASE_URL
        redirect_path = settings.GOOGLE_OAUTH_REDIRECT_PATH or "/auth/google/callback"

        # Validate that FRONTEND_BASE_URL is set
        if not base_frontend:
            return Response(
                {
                    "status": "error",
                    "message": "FRONTEND_BASE_URL is not configured. Please set FRONTEND_BASE_URL in your environment variables.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Ensure we don't end up with double slashes
        base_frontend = base_frontend.rstrip("/")

        if not redirect_path.startswith("/"):
            redirect_path = "/" + redirect_path

        redirect_url = f"{base_frontend}{redirect_path}"

        params = {
            "status": status_param,
            "next": next_path,
        }
        if message:
            params["message"] = message
        if access:
            params["access"] = access
        if refresh:
            params["refresh"] = refresh

        return redirect(f"{redirect_url}?{urlencode(params)}")


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"status": "error", "message": "Refresh token required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"status": "success", "message": "Logged out successfully"}, status=status.HTTP_200_OK)
        except Exception:
            return Response({"status": "error", "message": "Invalid refresh token"}, status=status.HTTP_400_BAD_REQUEST)


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = UserSerializer(request.user).data
        return Response({"status": "success", "data": data}, status=status.HTTP_200_OK)


class UserSearchPagination(PageNumberPagination):
    """
    Custom pagination for user search results.
    
    Provides pagination with configurable page size.
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class UserSearchView(ListAPIView):
    """
    API view for searching users by email or full name.
    
    Endpoint: GET /api/auth/users/?search=query&page_size=10
    Requires authentication.
    Returns paginated list of users matching the search query.
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = UserSearchSerializer
    pagination_class = UserSearchPagination
    
    def get_queryset(self):
        """
        Return users matching the search query.
        
        Searches in email and full_name fields.
        Only returns active users.
        """
        queryset = get_user_model().objects.filter(is_active=True)
        
        search_query = self.request.query_params.get('search', None)
        if search_query:
            # Search in both email and full_name fields
            queryset = queryset.filter(
                Q(email__icontains=search_query) | 
                Q(full_name__icontains=search_query)
            )
        
        # Order by email for consistent results
        return queryset.order_by('email')
    
    def list(self, request, *args, **kwargs):
        """
        Override list to return custom response format.
        """
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)
            
            return Response({
                "status": "success",
                "message": "Users retrieved successfully",
                "data": paginated_response.data
            }, status=status.HTTP_200_OK)
        
        # If no pagination, return all results
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "status": "success",
            "message": "Users retrieved successfully",
            "data": {
                "count": queryset.count(),
                "next": None,
                "previous": None,
                "results": serializer.data
            }
        }, status=status.HTTP_200_OK)


class UserDetailView(RetrieveAPIView):
    """
    API view for retrieving a specific user by ID.
    
    Endpoint: GET /api/auth/users/{user_id}/
    Requires authentication.
    Returns details of the specified user.
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = UserSearchSerializer
    lookup_field = 'id'
    
    def get_queryset(self):
        """
        Return active users only.
        """
        return get_user_model().objects.filter(is_active=True)
    
    def retrieve(self, request, *args, **kwargs):
        """
        Retrieve user details with custom response format.
        """
        try:
            user = self.get_object()
            serializer = self.get_serializer(user)
            return Response({
                "status": "success",
                "message": "User retrieved successfully",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "status": "error",
                "message": "User not found"
            }, status=status.HTTP_404_NOT_FOUND)


class ConfirmEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get('token')
        if not token:
            return Response({"status": "error", "message": "Token is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            data = signing.loads(token, max_age=60 * 60 * 24 * 2)
            uid = data.get("uid")
            user = get_user_model().objects.get(id=uid)
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=["is_active"])
            return Response({"status": "success", "message": "Email confirmed successfully"}, status=status.HTTP_200_OK)
        except Exception:
            return Response({"status": "error", "message": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)


class UserProfileDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        target_user_id = request.query_params.get('user_id')
        User = get_user_model()
        target_user = request.user if not target_user_id else get_object_or_404(User, id=target_user_id, is_active=True)

        involves_requester = Q(creator=request.user) | Q(signatures__signer=request.user)
        involves_target = Q(creator=target_user) | Q(signatures__signer=target_user)
        envelopes_qs = Envelope.objects.filter(involves_requester).filter(involves_target).distinct()

        user_data = UserProfileSerializer(target_user, context={'request': request}).data
        envelopes_data = EnvelopeSerializer(envelopes_qs, many=True, context={'request': request}).data
        return Response({
            "status": "success",
            "message": "Profile retrieved",
            "data": {"user": user_data, "envelopes_between_users": envelopes_data}
        }, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({
            "status": "success",
            "message": "Profile updated",
            "data": serializer.data
        }, status=status.HTTP_200_OK)
