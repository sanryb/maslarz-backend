from rest_framework import serializers
from .models import Survey, Option, Vote

class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ['id', 'text']

class SurveySerializer(serializers.ModelSerializer):
    options = OptionSerializer(many=True, read_only=True)

    class Meta:
        model = Survey
        fields = ['id', 'title', 'created_by', 'created_at', 'options', 'is_public', 'end_date']

class VoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vote
        fields = ['id', 'user', 'option']

    def validate(self, data):
        if Vote.objects.filter(user=data['user'], option=data['option']).exists():
            raise serializers.ValidationError('Już głosowałeś')
        return data

class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ['id', 'text']
    def validate_text(self, value):
        if len(value) < 2:
            raise serializers.ValidationError("Za krótki tekst")
        return value