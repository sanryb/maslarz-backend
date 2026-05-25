from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Answer, Choice, Question, Survey, SurveyAccess, SurveyResponse


class ChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choice
        fields = ('id', 'text', 'order')
        read_only_fields = ('id',)


class QuestionSerializer(serializers.ModelSerializer):
    type = serializers.ChoiceField(
        choices=Question.QuestionType.choices,
        source='question_type',
    )
    choices = ChoiceSerializer(many=True, required=False)
    answers = ChoiceSerializer(many=True, required=False, write_only=True)

    class Meta:
        model = Question
        fields = ('id', 'text', 'type', 'required', 'order', 'choices', 'answers')
        read_only_fields = ('id',)

    def validate(self, attrs):
        question_type = attrs.get('question_type')
        choices = attrs.get('choices')
        answers = attrs.pop('answers', None)

        if choices is not None and answers is not None:
            raise serializers.ValidationError(
                {'answers': 'Use either choices or answers, not both.'}
            )

        option_data = choices if choices is not None else answers
        attrs['choices'] = option_data or []

        if question_type == Question.QuestionType.TEXT and attrs['choices']:
            raise serializers.ValidationError(
                {'choices': 'Text questions cannot have selectable answers.'}
            )

        if question_type in (
            Question.QuestionType.SINGLE_SELECT,
            Question.QuestionType.MULTI_SELECT,
        ) and not attrs['choices']:
            raise serializers.ValidationError(
                {'choices': 'Select questions require at least one answer choice.'}
            )

        return attrs


class SurveySerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, required=False)
    owner = serializers.StringRelatedField(read_only=True)
    allowed_emails = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        write_only=True,
    )
    access_emails = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Survey
        fields = (
            'id',
            'uuid',
            'title',
            'description',
            'is_public',
            'open_at',
            'close_at',
            'owner',
            'allowed_emails',
            'access_emails',
            'questions',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'uuid', 'owner', 'created_at', 'updated_at')

    def validate_questions(self, value):
        if not value:
            raise serializers.ValidationError('A survey requires at least one question.')
        return value

    def validate(self, attrs):
        if self.instance is None and 'questions' not in attrs:
            raise serializers.ValidationError({'questions': 'This field is required.'})

        open_at = attrs.get('open_at', getattr(self.instance, 'open_at', None))
        close_at = attrs.get('close_at', getattr(self.instance, 'close_at', None))
        if open_at and close_at and open_at >= close_at:
            raise serializers.ValidationError(
                {'close_at': 'Close time must be after open time.'}
            )
        return attrs

    def validate_allowed_emails(self, value):
        return sorted({email.lower() for email in value})

    @extend_schema_field(serializers.ListField(child=serializers.EmailField()))
    def get_access_emails(self, obj):
        return [entry.email for entry in obj.access_entries.all()]

    @transaction.atomic
    def create(self, validated_data):
        questions_data = validated_data.pop('questions')
        allowed_emails = validated_data.pop('allowed_emails', [])
        survey = Survey.objects.create(**validated_data)

        SurveyAccess.objects.bulk_create(
            SurveyAccess(survey=survey, email=email)
            for email in allowed_emails
        )

        self.create_questions(survey, questions_data)

        return survey

    @transaction.atomic
    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions', None)
        allowed_emails = validated_data.pop('allowed_emails', None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if allowed_emails is not None:
            instance.access_entries.all().delete()
            SurveyAccess.objects.bulk_create(
                SurveyAccess(survey=instance, email=email)
                for email in allowed_emails
            )

        if questions_data is not None:
            instance.questions.all().delete()
            self.create_questions(instance, questions_data)

        return instance

    def create_questions(self, survey, questions_data):
        for question_index, question_data in enumerate(questions_data):
            choices_data = question_data.pop('choices', [])
            question_order = question_data.pop('order', question_index)
            question = Question.objects.create(
                survey=survey,
                order=question_order,
                **question_data,
            )

            Choice.objects.bulk_create(
                Choice(
                    question=question,
                    text=choice_data['text'],
                    order=choice_data.get('order', choice_index),
                )
                for choice_index, choice_data in enumerate(choices_data)
            )


class AnswerSubmissionSerializer(serializers.Serializer):
    question = serializers.PrimaryKeyRelatedField(queryset=Question.objects.all())
    text = serializers.CharField(required=False, allow_blank=True)
    choice = serializers.PrimaryKeyRelatedField(
        queryset=Choice.objects.all(),
        required=False,
        write_only=True,
    )
    choices = serializers.PrimaryKeyRelatedField(
        queryset=Choice.objects.all(),
        many=True,
        required=False,
        write_only=True,
    )


class AnswerSerializer(serializers.ModelSerializer):
    question = serializers.PrimaryKeyRelatedField(read_only=True)
    selected_choices = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Answer
        fields = ('id', 'question', 'text', 'selected_choices')


class SurveyResponseSerializer(serializers.ModelSerializer):
    answers = AnswerSubmissionSerializer(many=True, write_only=True)
    saved_answers = AnswerSerializer(source='answers', many=True, read_only=True)
    respondent_email = serializers.EmailField(required=False, allow_blank=True)

    class Meta:
        model = SurveyResponse
        fields = (
            'id',
            'survey',
            'respondent',
            'respondent_email',
            'answers',
            'saved_answers',
            'created_at',
        )
        read_only_fields = ('id', 'survey', 'respondent', 'saved_answers', 'created_at')

    def validate(self, attrs):
        survey = self.context['survey']
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        now = timezone.now()

        if survey.open_at and now < survey.open_at:
            raise serializers.ValidationError('This survey is not open yet.')
        if survey.close_at and now > survey.close_at:
            raise serializers.ValidationError('This survey is closed.')

        is_authenticated = bool(user and user.is_authenticated)

        if is_authenticated:
            if survey.responses.filter(respondent=user).exists():
                raise serializers.ValidationError('This user has already responded.')

        respondent_email = attrs.get('respondent_email', '').lower()
        if not is_authenticated and not respondent_email:
            raise serializers.ValidationError(
                {'respondent_email': 'This field is required for anonymous responses.'}
            )
        if respondent_email and survey.responses.filter(respondent_email=respondent_email).exists():
            raise serializers.ValidationError('This email has already responded.')
        attrs['respondent_email'] = respondent_email

        return attrs

    def validate_answers(self, value):
        survey = self.context['survey']
        survey_questions = {
            question.id: question
            for question in survey.questions.prefetch_related('choices')
        }
        submitted_question_ids = set()

        for answer_data in value:
            question = answer_data['question']
            if question.id not in survey_questions:
                raise serializers.ValidationError(
                    f'Question {question.id} does not belong to this survey.'
                )
            if question.id in submitted_question_ids:
                raise serializers.ValidationError(
                    f'Question {question.id} has more than one answer.'
                )
            submitted_question_ids.add(question.id)

            question_type = question.question_type
            text = answer_data.get('text', '')
            choice = answer_data.get('choice')
            choices = answer_data.get('choices')

            if question_type == Question.QuestionType.TEXT:
                if choice is not None or choices:
                    raise serializers.ValidationError(
                        f'Question {question.id} expects a text answer.'
                    )
                if not text:
                    raise serializers.ValidationError(
                        f'Question {question.id} requires text.'
                    )

            if question_type == Question.QuestionType.SINGLE_SELECT:
                if choice is None or choices or text:
                    raise serializers.ValidationError(
                        f'Question {question.id} expects exactly one choice.'
                    )
                if choice.question_id != question.id:
                    raise serializers.ValidationError(
                        f'Choice {choice.id} does not belong to question {question.id}.'
                    )

            if question_type == Question.QuestionType.MULTI_SELECT:
                if not choices or choice is not None or text:
                    raise serializers.ValidationError(
                        f'Question {question.id} expects one or more choices.'
                    )
                choice_ids = set()
                for selected_choice in choices:
                    if selected_choice.question_id != question.id:
                        raise serializers.ValidationError(
                            f'Choice {selected_choice.id} does not belong to question {question.id}.'
                        )
                    choice_ids.add(selected_choice.id)
                if len(choice_ids) != len(choices):
                    raise serializers.ValidationError(
                        f'Question {question.id} contains duplicate choices.'
                    )

        missing_question_ids = {
            question_id
            for question_id, question in survey_questions.items()
            if question.required
        } - submitted_question_ids
        if missing_question_ids:
            missing = ', '.join(str(question_id) for question_id in sorted(missing_question_ids))
            raise serializers.ValidationError(f'Missing answers for questions: {missing}.')

        return value

    @transaction.atomic
    def create(self, validated_data):
        answers_data = validated_data.pop('answers')
        survey = self.context['survey']
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        respondent = user if user and user.is_authenticated else None

        response = SurveyResponse.objects.create(
            survey=survey,
            respondent=respondent,
            **validated_data,
        )

        for answer_data in answers_data:
            question = answer_data['question']
            selected_choices = []
            text = ''

            if question.question_type == Question.QuestionType.TEXT:
                text = answer_data.get('text', '')
            elif question.question_type == Question.QuestionType.SINGLE_SELECT:
                selected_choices = [answer_data['choice']]
            else:
                selected_choices = answer_data['choices']

            answer = Answer.objects.create(
                response=response,
                question=question,
                text=text,
            )
            if selected_choices:
                answer.selected_choices.set(selected_choices)

        return response


class ChoiceSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    text = serializers.CharField()
    count = serializers.IntegerField()


class TextAnswerSummarySerializer(serializers.Serializer):
    response = serializers.IntegerField()
    respondent_email = serializers.EmailField(allow_blank=True)
    text = serializers.CharField()
    created_at = serializers.DateTimeField()


class QuestionSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    text = serializers.CharField()
    type = serializers.CharField()
    total_answers = serializers.IntegerField()
    choices = ChoiceSummarySerializer(many=True)
    text_answers = TextAnswerSummarySerializer(many=True)


class SurveySummarySerializer(serializers.Serializer):
    survey = serializers.IntegerField()
    title = serializers.CharField()
    response_count = serializers.IntegerField()
    questions = QuestionSummarySerializer(many=True)


class DashboardSurveySerializer(serializers.Serializer):
    name = serializers.CharField()
    response_count = serializers.IntegerField()
    uuid = serializers.UUIDField()


class DashboardSerializer(serializers.Serializer):
    surveys_count = serializers.IntegerField()
    active_surveys_count = serializers.IntegerField()
    responses_count = serializers.IntegerField()
    surveys = DashboardSurveySerializer(many=True)
