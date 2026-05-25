from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    AuthResponseSerializer,
    LoginSerializer,
    MeResponseSerializer,
    RegisterSerializer,
    UserSerializer,
)


def auth_response(user, response_status=status.HTTP_200_OK):
    token, _ = Token.objects.get_or_create(user=user)
    return Response(
        {
            'token': token.key,
            'token_type': 'Bearer',
            'user': UserSerializer(user).data,
        },
        status=response_status,
    )


class RegisterView(APIView):
    permission_classes = (permissions.AllowAny,)

    @extend_schema(
        tags=['Auth'],
        request=RegisterSerializer,
        responses={201: AuthResponseSerializer},
        summary='Register a new user',
        description='Creates a user account and returns a Bearer token for API authentication.',
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return auth_response(user, status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = (permissions.AllowAny,)

    @extend_schema(
        tags=['Auth'],
        request=LoginSerializer,
        responses={200: AuthResponseSerializer},
        summary='Log in',
        description='Authenticates by email and password, then returns a Bearer token.',
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return auth_response(serializer.validated_data['user'])


class MeView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        tags=['Auth'],
        responses={200: MeResponseSerializer},
        summary='Get current user',
        description='Returns the user connected to the Bearer token.',
    )
    def get(self, request):
        return Response({'user': UserSerializer(request.user).data})


class LogoutView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        tags=['Auth'],
        request=None,
        responses={204: OpenApiResponse(description='Logged out successfully.')},
        summary='Log out',
        description='Deletes the current Bearer token.',
    )
    def post(self, request):
        request.user.auth_token.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
