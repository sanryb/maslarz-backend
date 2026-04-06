from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Survey(models.Model):
    title = models.CharField(max_length=255)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_public = models.BooleanField(default=False)
    end_date = models.DateTimeField(null=True, blank=True)


    def __str__(self):
        return self.title


class Option(models.Model):
    survey = models.ForeignKey(Survey, related_name='options', on_delete=models.CASCADE)
    text = models.CharField(max_length=255)

    def __str__(self):
        return self.text


class Vote(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    option = models.ForeignKey(Option, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'option')