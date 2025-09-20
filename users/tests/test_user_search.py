"""
Unit tests for user search functionality.

This module tests the user search endpoint and serializer
validation logic.
"""

import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class UserSearchTestCase(APITestCase):
    """
    Test cases for user search endpoint.
    """
    
    def setUp(self):
        """Set up test data."""
        # Create test users
        self.user1 = User.objects.create_user(
            email='john.doe@example.com',
            username='john.doe',
            full_name='John Doe',
            password='testpass123'
        )
        
        self.user2 = User.objects.create_user(
            email='jane.smith@example.com',
            username='jane.smith',
            full_name='Jane Smith',
            password='testpass123'
        )
        
        self.user3 = User.objects.create_user(
            email='bob.wilson@test.com',
            username='bob.wilson',
            full_name='Bob Wilson',
            password='testpass123'
        )
        
        # Create an inactive user
        self.inactive_user = User.objects.create_user(
            email='inactive@example.com',
            username='inactive',
            full_name='Inactive User',
            password='testpass123',
            is_active=False
        )
        
        # Get JWT token for authentication
        refresh = RefreshToken.for_user(self.user1)
        self.token = str(refresh.access_token)
        
        # Set up authentication header
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
    
    def test_search_users_by_email(self):
        """Test searching users by email address."""
        url = reverse('auth-users-search')
        
        response = self.client.get(url, {'search': 'john.doe@example.com'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(len(response.data['data']['results']), 1)
        self.assertEqual(response.data['data']['results'][0]['email'], 'john.doe@example.com')
    
    def test_search_users_by_full_name(self):
        """Test searching users by full name."""
        url = reverse('auth-users-search')
        
        response = self.client.get(url, {'search': 'Jane Smith'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(len(response.data['data']['results']), 1)
        self.assertEqual(response.data['data']['results'][0]['full_name'], 'Jane Smith')
    
    def test_search_users_partial_match(self):
        """Test searching users with partial matches."""
        url = reverse('auth-users-search')
        
        response = self.client.get(url, {'search': 'example.com'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(len(response.data['data']['results']), 2)  # john.doe and jane.smith
    
    def test_search_users_case_insensitive(self):
        """Test that search is case insensitive."""
        url = reverse('auth-users-search')
        
        response = self.client.get(url, {'search': 'JOHN.DOE'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(len(response.data['data']['results']), 1)
        self.assertEqual(response.data['data']['results'][0]['email'], 'john.doe@example.com')
    
    def test_search_users_no_results(self):
        """Test searching with no matching results."""
        url = reverse('auth-users-search')
        
        response = self.client.get(url, {'search': 'nonexistent@example.com'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(len(response.data['data']['results']), 0)
    
    def test_search_users_no_query_returns_all_active_users(self):
        """Test that no search query returns all active users."""
        url = reverse('auth-users-search')
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(len(response.data['data']['results']), 3)  # All active users
    
    def test_search_users_excludes_inactive_users(self):
        """Test that inactive users are excluded from search results."""
        url = reverse('auth-users-search')
        
        response = self.client.get(url, {'search': 'inactive'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(len(response.data['data']['results']), 0)  # No inactive users
    
    def test_search_users_pagination(self):
        """Test pagination functionality."""
        url = reverse('auth-users-search')
        
        response = self.client.get(url, {'page_size': 2})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(len(response.data['data']['results']), 2)
        self.assertIsNotNone(response.data['data']['next'])  # Should have next page
    
    def test_search_users_large_page_size(self):
        """Test that page_size is capped at maximum."""
        url = reverse('auth-users-search')
        
        response = self.client.get(url, {'page_size': 1000})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        # Should return all users, not exceed max_page_size
        self.assertLessEqual(len(response.data['data']['results']), 100)
    
    def test_unauthenticated_request_returns_401(self):
        """Test unauthenticated request returns 401."""
        # Remove authentication
        self.client.credentials()
        
        url = reverse('auth-users-search')
        
        response = self.client.get(url, {'search': 'test'})
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_response_format(self):
        """Test that response has correct format."""
        url = reverse('auth-users-search')
        
        response = self.client.get(url, {'search': 'john'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('status', response.data)
        self.assertIn('message', response.data)
        self.assertIn('data', response.data)
        self.assertIn('count', response.data['data'])
        self.assertIn('results', response.data['data'])
        
        # Check user data format
        if response.data['data']['results']:
            user_data = response.data['data']['results'][0]
            required_fields = ['id', 'email', 'full_name', 'is_active', 'created_at']
            for field in required_fields:
                self.assertIn(field, user_data)
