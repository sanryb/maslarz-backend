from django.urls import path

from .views import LoginView, LogoutView, MeView, RegisterView


urlpatterns = [
    path('signup/', RegisterView.as_view(), name='auth-signup'),
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
]
