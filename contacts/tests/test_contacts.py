from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from users.models import CustomUser
from contacts.models import Contact


class ContactsTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = CustomUser.objects.create_user(
            username='owner@example.com',
            email='owner@example.com',
            full_name='Owner User',
            password='StrongPassw0rd!'
        )
        login = self.client.post(reverse('auth-login'), {
            'email': 'owner@example.com',
            'password': 'StrongPassw0rd!'
        }, format='json')
        self.assertEqual(login.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['data']['access']}")

    def test_add_existing_user_as_contact(self):
        existing = CustomUser.objects.create_user(
            username='other@example.com',
            email='other@example.com',
            full_name='Other User',
            password='StrongPassw0rd!'
        )
        res = self.client.post(reverse('contacts:contacts_add'), {
            'email': 'other@example.com',
            'name': 'Other'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        contact = Contact.objects.get(owner=self.owner, email='other@example.com')
        self.assertEqual(contact.contact_user_id, existing.id)

    def test_search_existing_and_non_existing_user(self):
        CustomUser.objects.create_user(
            username='known@example.com',
            email='known@example.com',
            full_name='Known User',
            password='StrongPassw0rd!'
        )
        # Existing
        res1 = self.client.post(reverse('contacts:contacts_search'), {'email': 'known@example.com'}, format='json')
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(res1.data['data']['exists'])
        # Non-existing
        res2 = self.client.post(reverse('contacts:contacts_search'), {'email': 'missing@example.com'}, format='json')
        self.assertEqual(res2.status_code, 200)
        self.assertFalse(res2.data['data']['exists'])
        self.assertTrue(res2.data['data']['invite'])

    def test_invite_new_contact_sends_email_and_saves(self):
        res = self.client.post(reverse('contacts:contacts_invite'), {
            'email': 'newperson@example.com'
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(Contact.objects.filter(owner=self.owner, email='newperson@example.com').exists())

    def test_contact_list_user_isolation(self):
        other_user = CustomUser.objects.create_user(
            username='someone@example.com',
            email='someone@example.com',
            full_name='Someone Else',
            password='StrongPassw0rd!'
        )
        # Create contacts for both users
        Contact.objects.create(owner=self.owner, email='a@example.com')
        Contact.objects.create(owner=other_user, email='b@example.com')
        res = self.client.get(reverse('contacts:contacts_list'))
        self.assertEqual(res.status_code, 200)
        emails = [c['email'] for c in res.data['data']]
        self.assertIn('a@example.com', emails)
        self.assertNotIn('b@example.com', emails)

    def test_delete_contact(self):
        # Create a contact for owner
        contact = Contact.objects.create(owner=self.owner, email='del@example.com', name='Del')
        res = self.client.delete(reverse('contacts:contacts_delete', kwargs={'pk': str(contact.id)}))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Contact.objects.filter(id=contact.id).exists())


