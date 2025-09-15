from django.urls import reverse
from rest_framework.test import APIClient
from django.test import TestCase
from .models import CustomUser
from django.conf import settings


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_valid(self):
        res = self.client.post(reverse('auth-register'), {
            'email': 'user@example.com',
            'full_name': 'Test User',
            'password': 'StrongPassw0rd!'
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertTrue(CustomUser.objects.filter(email='user@example.com').exists())

    def test_register_invalid_missing_fields(self):
        res = self.client.post(reverse('auth-register'), {
            'email': 'user2@example.com',
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_env_loaded(self):
        # Ensure critical env-based settings are present
        self.assertIsNotNone(settings.SECRET_KEY)
        self.assertIn('localhost', settings.ALLOWED_HOSTS)

    def test_login_success_and_profile(self):
        user = CustomUser.objects.create_user(username='user@example.com', email='user@example.com', full_name='User', password='StrongPassw0rd!')
        res = self.client.post(reverse('auth-login'), {
            'email': 'user@example.com',
            'password': 'StrongPassw0rd!'
        }, format='json')
        self.assertEqual(res.status_code, 200)
        access = res.data['data']['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        profile = self.client.get(reverse('auth-profile'))
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.data['data']['email'], 'user@example.com')

    def test_login_failure(self):
        res = self.client.post(reverse('auth-login'), {
            'email': 'missing@example.com',
            'password': 'wrong'
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_logout(self):
        user = CustomUser.objects.create_user(username='u@e.com', email='u@e.com', full_name='U', password='StrongPassw0rd!')
        res = self.client.post(reverse('auth-login'), {'email': 'u@e.com', 'password': 'StrongPassw0rd!'}, format='json')
        refresh = res.data['data']['refresh']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {res.data['data']['access']}')
        out = self.client.post(reverse('auth-logout'), {'refresh': refresh}, format='json')
        self.assertEqual(out.status_code, 200)
        # Attempt to use blacklisted refresh token
        refresh_attempt = self.client.post(reverse('token_refresh'), {'refresh': refresh}, format='json')
        self.assertEqual(refresh_attempt.status_code, 401)

    def test_register_duplicate_email(self):
        CustomUser.objects.create_user(username='dup@example.com', email='dup@example.com', full_name='Dup', password='StrongPassw0rd!')
        res = self.client.post(reverse('auth-register'), {
            'email': 'dup@example.com',
            'full_name': 'Dup Two',
            'password': 'StrongPassw0rd!'
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_login_inactive_user(self):
        user = CustomUser.objects.create_user(username='inactive@example.com', email='inactive@example.com', full_name='Inactive', password='StrongPassw0rd!')
        user.is_active = False
        user.save()
        res = self.client.post(reverse('auth-login'), {
            'email': 'inactive@example.com',
            'password': 'StrongPassw0rd!'
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid credentials', str(res.data))

    def test_profile_unauthenticated_401(self):
        res = self.client.get(reverse('auth-profile'))
        self.assertEqual(res.status_code, 401)

from django.test import TestCase

# Create your tests here.
