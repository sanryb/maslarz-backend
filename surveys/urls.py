from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PublicSurveyViewSet, SurveyViewSet


router = DefaultRouter()
router.register('', SurveyViewSet, basename='survey')

public_router = DefaultRouter()
public_router.register('', PublicSurveyViewSet, basename='public-survey')

urlpatterns = [
    path('', include(router.urls)),
]

public_urlpatterns = [
    path('', include(public_router.urls)),
]
