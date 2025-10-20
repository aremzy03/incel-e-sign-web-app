from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import RegisterView, LoginView, LogoutView, ProfileView, UserSearchView, UserDetailView, ConfirmEmailView, UserProfileDetailView


urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('confirm-email/', ConfirmEmailView.as_view(), name='auth-confirm-email'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('profile/', ProfileView.as_view(), name='auth-profile'),
    path('profile/detail/', UserProfileDetailView.as_view(), name='auth-profile-detail'),
    path('users/', UserSearchView.as_view(), name='auth-users-search'),
    path('users/<uuid:id>/', UserDetailView.as_view(), name='auth-user-detail'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]


