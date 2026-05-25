from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient


User = get_user_model()


class AuthApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_swagger_documentation_routes_are_available(self):
        schema_response = self.client.get('/api/schema/')
        yaml_schema_response = self.client.get('/api/schema.yaml')
        docs_response = self.client.get('/api/docs/')

        self.assertEqual(schema_response.status_code, status.HTTP_200_OK)
        self.assertEqual(yaml_schema_response.status_code, status.HTTP_200_OK)
        self.assertEqual(docs_response.status_code, status.HTTP_200_OK)
        self.assertIn('api/auth/login', schema_response.content.decode())
        self.assertIn('application/vnd.oai.openapi', yaml_schema_response['Content-Type'])
        self.assertIn('/api/auth/login/', yaml_schema_response.content.decode())

    def test_register_returns_bearer_token_and_user(self):
        response = self.client.post(
            '/api/auth/register/',
            {
                'username': 'tester',
                'email': 'tester@example.com',
                'password': 'StrongPass123!',
                'confirm_password': 'StrongPass123!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['token_type'], 'Bearer')
        self.assertTrue(response.data['token'])
        self.assertEqual(response.data['user']['username'], 'tester')
        self.assertTrue(User.objects.filter(email='tester@example.com').exists())

    def test_signup_returns_bearer_token_and_user(self):
        response = self.client.post(
            '/api/auth/signup/',
            {
                'username': 'signup-tester',
                'email': 'signup-tester@example.com',
                'password': 'StrongPass123!',
                'confirm_password': 'StrongPass123!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['token_type'], 'Bearer')
        self.assertTrue(response.data['token'])
        self.assertEqual(response.data['user']['email'], 'signup-tester@example.com')

    def test_signup_requires_matching_confirm_password(self):
        response = self.client.post(
            '/api/auth/signup/',
            {
                'username': 'tester',
                'email': 'tester@example.com',
                'password': 'StrongPass123!',
                'confirm_password': 'DifferentPass123!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('confirm_password', response.data)

    def test_login_returns_bearer_token(self):
        User.objects.create_user(
            username='tester',
            email='tester@example.com',
            password='StrongPass123!',
        )

        response = self.client.post(
            '/api/auth/login/',
            {
                'email': 'tester@example.com',
                'password': 'StrongPass123!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['token_type'], 'Bearer')
        self.assertTrue(response.data['token'])

    def test_bearer_token_authenticates_me_route(self):
        register_response = self.client.post(
            '/api/auth/register/',
            {
                'username': 'tester',
                'email': 'tester@example.com',
                'password': 'StrongPass123!',
                'confirm_password': 'StrongPass123!',
            },
            format='json',
        )
        token = register_response.data['token']

        response = self.client.get(
            '/api/auth/me/',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['user']['email'], 'tester@example.com')
