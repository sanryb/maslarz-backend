import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Survey(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_public = models.BooleanField(default=False)
    open_at = models.DateTimeField(null=True, blank=True)
    close_at = models.DateTimeField(null=True, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='surveys',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return self.title


class SurveyAccess(models.Model):
    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='access_entries',
    )
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('email',)
        constraints = [
            models.UniqueConstraint(
                fields=('survey', 'email'),
                name='unique_survey_access_email',
            ),
        ]

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class Question(models.Model):
    class QuestionType(models.TextChoices):
        SINGLE_SELECT = 'single_select', 'Single select'
        MULTI_SELECT = 'multi_select', 'Multi select'
        TEXT = 'text', 'Text'

    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='questions',
    )
    text = models.CharField(max_length=500)
    question_type = models.CharField(max_length=32, choices=QuestionType.choices)
    required = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('order', 'id')

    def __str__(self):
        return self.text


class Choice(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='choices',
    )
    text = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('order', 'id')

    def __str__(self):
        return self.text


class SurveyResponse(models.Model):
    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='responses',
    )
    respondent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='survey_responses',
        null=True,
        blank=True,
    )
    respondent_email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        constraints = [
            models.UniqueConstraint(
                fields=('survey', 'respondent'),
                condition=Q(respondent__isnull=False),
                name='unique_survey_response_user',
            ),
            models.UniqueConstraint(
                fields=('survey', 'respondent_email'),
                condition=~Q(respondent_email=''),
                name='unique_survey_response_email',
            ),
        ]

    def save(self, *args, **kwargs):
        self.respondent_email = self.respondent_email.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Response to {self.survey}'


class Answer(models.Model):
    response = models.ForeignKey(
        SurveyResponse,
        on_delete=models.CASCADE,
        related_name='answers',
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='answers',
    )
    text = models.TextField(blank=True)
    selected_choices = models.ManyToManyField(Choice, blank=True, related_name='answers')

    class Meta:
        ordering = ('id',)
        constraints = [
            models.UniqueConstraint(
                fields=('response', 'question'),
                name='unique_response_question_answer',
            ),
        ]

    def __str__(self):
        return f'Answer to {self.question}'
