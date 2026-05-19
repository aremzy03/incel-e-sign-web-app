"""
Tests for document list filtering.
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from documents.models import Document

User = get_user_model()


class DocumentListFilterTestCase(APITestCase):
    """Tests for GET /api/documents/ status filter."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='doc_owner',
            email='owner@test.com',
            password='testpass123',
            full_name='Document Owner',
        )
        self.other_user = User.objects.create_user(
            username='other_owner',
            email='other@test.com',
            password='testpass123',
            full_name='Other Owner',
        )

        self.draft_doc = Document.objects.create(
            owner=self.user,
            file_url='/media/draft.pdf',
            file_name='draft.pdf',
            file_size=100,
            status='draft',
        )
        self.sent_doc = Document.objects.create(
            owner=self.user,
            file_url='/media/sent.pdf',
            file_name='annual_report.pdf',
            file_size=100,
            status='sent',
        )
        Document.objects.create(
            owner=self.other_user,
            file_url='/media/other.pdf',
            file_name='other.pdf',
            file_size=100,
            status='draft',
        )

    def _auth_headers(self, user):
        refresh = RefreshToken.for_user(user)
        return {'HTTP_AUTHORIZATION': f'Bearer {refresh.access_token}'}

    def test_list_documents_without_status_returns_all_owned(self):
        response = self.client.get('/api/documents/', **self._auth_headers(self.user))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        result_ids = {item['id'] for item in response.data['results']}
        self.assertEqual(
            result_ids,
            {str(self.draft_doc.id), str(self.sent_doc.id)},
        )

    def test_list_documents_filter_by_status(self):
        response = self.client.get(
            '/api/documents/',
            {'status': 'draft'},
            **self._auth_headers(self.user),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], str(self.draft_doc.id))
        self.assertEqual(response.data['results'][0]['status'], 'draft')

    def test_list_documents_search_by_file_name(self):
        response = self.client.get(
            '/api/documents/',
            {'search': 'annual'},
            **self._auth_headers(self.user),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], str(self.sent_doc.id))

    def test_list_documents_search_combined_with_status(self):
        response = self.client.get(
            '/api/documents/',
            {'search': 'draft', 'status': 'draft'},
            **self._auth_headers(self.user),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], str(self.draft_doc.id))

    def test_list_documents_search_no_match_returns_empty(self):
        response = self.client.get(
            '/api/documents/',
            {'search': 'nonexistent-file'},
            **self._auth_headers(self.user),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.data['results'], [])

    def test_list_documents_invalid_status_returns_400(self):
        response = self.client.get(
            '/api/documents/',
            {'status': 'pending'},
            **self._auth_headers(self.user),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', response.data)
