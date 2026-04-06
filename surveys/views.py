from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count
from django.utils import timezone

import bleach

from .models import Survey, Option, Vote
from .serializers import SurveySerializer, OptionSerializer, VoteSerializer


class SurveyViewSet(viewsets.ModelViewSet):
    queryset = Survey.objects.all()
    serializer_class = SurveySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Survey.objects.filter(is_public=True) | Survey.objects.filter(created_by=user)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    # dodawanie opcji do ankiety
    @action(detail=True, methods=['post'])
    def add_option(self, request, pk=None):
        survey = self.get_object()

        raw_text = request.data.get('text')
        text = bleach.clean(raw_text) if raw_text else ""

        if not text:
            return Response({"error": "Brak tekstu opcji"}, status=400)

        serializer = OptionSerializer(data={"text": text})
        serializer.is_valid(raise_exception=True)
        serializer.save(survey=survey)

        return Response(serializer.data, status=201)

    # głosowanie
    @action(detail=True, methods=['post'])
    def vote(self, request, pk=None):
        option_id = request.data.get('option_id')

        if not option_id:
            return Response({"error": "Brak option_id"}, status=400)

        try:
            option = Option.objects.get(id=option_id)
        except Option.DoesNotExist:
            return Response({"error": "Opcja nie istnieje"}, status=404)

        survey = self.get_object()

        if survey.end_date and survey.end_date < timezone.now():
            return Response({"error": "Ankieta zakończona"}, status=400)

        if option.survey != survey:
            return Response({"error": "Opcja nie należy do tej ankiety"}, status=400)

        user = request.user

        if Vote.objects.filter(user=user, option__survey=survey).exists():
            return Response({"error": "Już głosowałeś w tej ankiecie"}, status=400)

        Vote.objects.create(user=user, option=option)

        return Response({"message": "Głos zapisany"}, status=201)

    #wyniki
    @action(detail=True, methods=['get'])
    def results(self, request, pk=None):
        survey = self.get_object()

        results = survey.options.annotate(votes_count=Count('vote'))

        data = [
            {
                "option": option.text,
                "votes": option.votes_count
            }
            for option in results
        ]

        return Response(data)


class OptionViewSet(viewsets.ModelViewSet):
    queryset = Option.objects.all()
    serializer_class = OptionSerializer
    permission_classes = [permissions.IsAuthenticated]


class VoteViewSet(viewsets.ModelViewSet):
    queryset = Vote.objects.all()
    serializer_class = VoteSerializer
    permission_classes = [permissions.IsAuthenticated]