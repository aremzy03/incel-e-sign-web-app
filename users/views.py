from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.generics import ListAPIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.db.models import Q

from .serializers import RegisterSerializer, LoginSerializer, UserSerializer, UserSearchSerializer


# Create your views here.


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            data = UserSerializer(user).data
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
