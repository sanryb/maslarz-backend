from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, NotFound, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Question, Survey, SurveyResponse
from .serializers import (
    DashboardSerializer,
    SurveyResponseSerializer,
    SurveySerializer,
    SurveySummarySerializer,
)


@extend_schema_view(
    list=extend_schema(
        tags=['Surveys'],
        summary='List surveys',
        description=(
            'Lists surveys created by the authenticated user and private '
            'surveys where their email is allowlisted.'
        ),
    ),
    create=extend_schema(
        tags=['Surveys'],
        summary='Create survey',
        description=(
            'Creates a survey with questions. Question type must be '
            '`single_select`, `multi_select`, or `text`. Select questions '
            'require choices; text questions cannot have choices. Set '
            '`is_public` to true when responders should not need an account. '
            'For private surveys, use `allowed_emails` to grant access.'
        ),
    ),
    retrieve=extend_schema(
        tags=['Surveys'],
        parameters=[
            OpenApiParameter('id', OpenApiTypes.INT, OpenApiParameter.PATH),
        ],
        summary='Get survey',
        description=(
            'Returns one survey created by the authenticated user or a private '
            'survey where their email is allowlisted.'
        ),
    ),
    update=extend_schema(
        tags=['Surveys'],
        parameters=[
            OpenApiParameter('id', OpenApiTypes.INT, OpenApiParameter.PATH),
        ],
        summary='Update survey',
        description=(
            'Updates a survey owned by the authenticated user. If `questions` '
            'or `allowed_emails` are included, those nested collections are replaced.'
        ),
    ),
    partial_update=extend_schema(
        tags=['Surveys'],
        parameters=[
            OpenApiParameter('id', OpenApiTypes.INT, OpenApiParameter.PATH),
        ],
        summary='Partially update survey',
        description=(
            'Partially updates a survey owned by the authenticated user. If '
            '`questions` or `allowed_emails` are included, those nested collections are replaced.'
        ),
    ),
    destroy=extend_schema(
        tags=['Surveys'],
        parameters=[
            OpenApiParameter('id', OpenApiTypes.INT, OpenApiParameter.PATH),
        ],
        summary='Delete survey',
        description='Deletes a survey owned by the authenticated user.',
    ),
)
class SurveyViewSet(viewsets.ModelViewSet):
    serializer_class = SurveySerializer
    permission_classes = (IsAuthenticated,)
    http_method_names = ('get', 'post', 'put', 'patch', 'delete', 'head', 'options')

    def get_queryset(self):
        return (
            Survey.objects.filter(
                Q(owner=self.request.user)
                | Q(is_public=False, access_entries__email__iexact=self.request.user.email)
            )
            .prefetch_related('questions__choices', 'access_entries')
            .distinct()
        )

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.owner_id != self.request.user.id:
            raise PermissionDenied('Only the survey owner can update this survey.')
        serializer.save()

    def perform_destroy(self, instance):
        if instance.owner_id != self.request.user.id:
            raise PermissionDenied('Only the survey owner can delete this survey.')
        instance.delete()

    @extend_schema(
        tags=['Surveys'],
        parameters=[
            OpenApiParameter('survey_uuid', OpenApiTypes.UUID, OpenApiParameter.PATH),
        ],
        responses={200: SurveySerializer},
        summary='Get survey by UUID',
        description=(
            'Returns one survey by UUID if it was created by the authenticated '
            'user or their email is allowlisted.'
        ),
    )
    @action(
        detail=False,
        methods=['get'],
        url_path='by-uuid/(?P<survey_uuid>[^/.]+)',
    )
    def by_uuid(self, request, survey_uuid=None):
        survey = get_object_or_404(self.get_queryset(), uuid=survey_uuid)
        return Response(self.get_serializer(survey).data)

    @extend_schema(
        tags=['Dashboard'],
        responses={200: DashboardSerializer},
        summary='Get dashboard metrics',
        description=(
            'Returns survey count, active survey count, total response count, '
            'and all surveys for the authenticated owner.'
        ),
    )
    @action(detail=False, methods=['get'], url_path='dashboard')
    def dashboard(self, request):
        now = timezone.now()
        owner_surveys = Survey.objects.filter(owner=request.user)
        active_surveys = owner_surveys.filter(
            Q(open_at__isnull=True) | Q(open_at__lte=now),
            Q(close_at__isnull=True) | Q(close_at__gt=now),
        )
        surveys = (
            owner_surveys.annotate(response_count=Count('responses'))
            .order_by('-created_at', '-id')
        )

        return Response(
            {
                'surveys_count': owner_surveys.count(),
                'active_surveys_count': active_surveys.count(),
                'responses_count': SurveyResponse.objects.filter(
                    survey__owner=request.user,
                ).count(),
                'surveys': [
                    {
                        'name': survey.title,
                        'response_count': survey.response_count,
                        'uuid': str(survey.uuid),
                    }
                    for survey in surveys
                ],
            }
        )

    @extend_schema(
        tags=['Survey summary'],
        parameters=[
            OpenApiParameter('id', OpenApiTypes.INT, OpenApiParameter.PATH),
        ],
        responses={200: SurveySummarySerializer},
        summary='Get survey summary',
        description='Returns per-question response summaries for a survey owned by the authenticated user.',
    )
    @action(detail=True, methods=['get'], url_path='summary')
    def summary(self, request, pk=None):
        survey = self.get_object()
        if survey.owner_id != request.user.id:
            raise PermissionDenied('Only the survey owner can view the summary.')

        questions = survey.questions.prefetch_related(
            'choices',
            'answers__response__respondent',
            'answers__selected_choices',
        )
        question_summaries = []

        for question in questions:
            answer_rows = list(question.answers.select_related('response', 'response__respondent'))
            choice_summaries = []
            text_answers = []

            if question.question_type in (
                Question.QuestionType.SINGLE_SELECT,
                Question.QuestionType.MULTI_SELECT,
            ):
                for choice in question.choices.all():
                    choice_summaries.append(
                        {
                            'id': choice.id,
                            'text': choice.text,
                            'count': choice.answers.filter(response__survey=survey).count(),
                        }
                    )

            if question.question_type == Question.QuestionType.TEXT:
                for answer in answer_rows:
                    respondent = answer.response.respondent
                    text_answers.append(
                        {
                            'response': answer.response_id,
                            'respondent_email': answer.response.respondent_email
                            or (respondent.email if respondent else ''),
                            'text': answer.text,
                            'created_at': answer.response.created_at,
                        }
                    )

            question_summaries.append(
                {
                    'id': question.id,
                    'text': question.text,
                    'type': question.question_type,
                    'total_answers': len(answer_rows),
                    'choices': choice_summaries,
                    'text_answers': text_answers,
                }
            )

        return Response(
            {
                'survey': survey.id,
                'title': survey.title,
                'response_count': survey.responses.count(),
                'questions': question_summaries,
            }
        )

    @extend_schema(
        tags=['Survey responses'],
        parameters=[
            OpenApiParameter('id', OpenApiTypes.INT, OpenApiParameter.PATH),
        ],
        request=SurveyResponseSerializer,
        responses={201: SurveyResponseSerializer},
        summary='Save survey answers',
        description=(
            'Saves answers for a survey. Public surveys can be answered without '
            'an account. Private surveys require Bearer auth from the owner or '
            'an allowlisted user email.'
        ),
    )
    @action(
        detail=True,
        methods=['post'],
        url_path='responses',
        permission_classes=[AllowAny],
    )
    def responses(self, request, pk=None):
        survey = get_object_or_404(
            Survey.objects.prefetch_related('questions__choices', 'access_entries'),
            pk=pk,
        )
        self.check_response_access(request, survey)
        serializer = SurveyResponseSerializer(
            data=request.data,
            context={'survey': survey, 'request': request},
        )
        serializer.is_valid(raise_exception=True)
        response = serializer.save()
        return Response(
            SurveyResponseSerializer(response).data,
            status=status.HTTP_201_CREATED,
        )

    def check_response_access(self, request, survey):
        if survey.is_public:
            return

        user = request.user
        if not user or not user.is_authenticated:
            raise NotAuthenticated('Authentication is required for private surveys.')

        is_owner = survey.owner_id == user.id
        is_allowlisted = survey.access_entries.filter(email__iexact=user.email).exists()
        if not is_owner and not is_allowlisted:
            raise NotFound()


@extend_schema_view(
    list=extend_schema(
        tags=['Public surveys'],
        summary='List public surveys',
        description='Lists surveys that can be answered without an account.',
    ),
    retrieve=extend_schema(
        tags=['Public surveys'],
        parameters=[
            OpenApiParameter('id', OpenApiTypes.INT, OpenApiParameter.PATH),
        ],
        summary='Get public survey',
        description='Returns one public survey. Private surveys are not exposed here.',
    ),
)
class PublicSurveyViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SurveySerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        return (
            Survey.objects.filter(is_public=True)
            .prefetch_related('questions__choices', 'access_entries')
        )

    @extend_schema(
        tags=['Public surveys'],
        parameters=[
            OpenApiParameter('survey_uuid', OpenApiTypes.UUID, OpenApiParameter.PATH),
        ],
        responses={200: SurveySerializer},
        summary='Get public survey by UUID',
        description='Returns one public survey by UUID. Private surveys are not exposed here.',
    )
    @action(
        detail=False,
        methods=['get'],
        url_path='by-uuid/(?P<survey_uuid>[^/.]+)',
    )
    def by_uuid(self, request, survey_uuid=None):
        survey = get_object_or_404(self.get_queryset(), uuid=survey_uuid)
        return Response(self.get_serializer(survey).data)
