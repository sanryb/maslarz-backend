from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import Answer, Choice, Question, Survey, SurveyAccess, SurveyResponse


User = get_user_model()


class SurveyApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='survey-owner',
            email='owner@example.com',
            password='StrongPass123!',
        )
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token.key}')

    def test_create_survey_with_supported_question_types(self):
        response = self.client.post(
            '/api/surveys/',
            {
                'title': 'Customer feedback',
                'description': 'Quarterly product survey',
                'is_public': True,
                'questions': [
                    {
                        'text': 'How satisfied are you?',
                        'type': 'single_select',
                        'choices': [
                            {'text': 'Satisfied'},
                            {'text': 'Neutral'},
                            {'text': 'Unsatisfied'},
                        ],
                    },
                    {
                        'text': 'Which features do you use?',
                        'type': 'multi_select',
                        'answers': [
                            {'text': 'Decks'},
                            {'text': 'Sharing'},
                        ],
                    },
                    {
                        'text': 'What should we improve?',
                        'type': 'text',
                        'required': False,
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Customer feedback')
        self.assertTrue(response.data['is_public'])
        self.assertEqual(len(response.data['questions']), 3)
        self.assertTrue(response.data['uuid'])
        self.assertFalse(response.data['questions'][2]['required'])
        self.assertEqual(Survey.objects.count(), 1)
        self.assertEqual(Question.objects.count(), 3)
        self.assertEqual(Choice.objects.count(), 5)

    def test_dashboard_returns_owner_metrics_and_all_surveys(self):
        other_user = User.objects.create_user(
            username='other-owner',
            email='other@example.com',
            password='StrongPass123!',
        )
        active_survey = Survey.objects.create(
            owner=self.user,
            title='Active survey',
            description='Open',
            is_public=True,
        )
        closed_survey = Survey.objects.create(
            owner=self.user,
            title='Closed survey',
            description='Closed',
            is_public=True,
            close_at=timezone.now() - timedelta(days=1),
        )
        scheduled_survey = Survey.objects.create(
            owner=self.user,
            title='Scheduled survey',
            description='Future',
            is_public=True,
            open_at=timezone.now() + timedelta(days=1),
        )
        oldest_survey = Survey.objects.create(
            owner=self.user,
            title='Oldest survey',
            description='Still included',
            is_public=True,
        )
        other_survey = Survey.objects.create(
            owner=other_user,
            title='Other survey',
            description='Not mine',
            is_public=True,
        )
        SurveyResponse.objects.create(survey=active_survey, respondent_email='a@example.com')
        SurveyResponse.objects.create(survey=active_survey, respondent_email='b@example.com')
        SurveyResponse.objects.create(survey=closed_survey, respondent_email='c@example.com')
        SurveyResponse.objects.create(survey=other_survey, respondent_email='d@example.com')

        response = self.client.get('/api/surveys/dashboard/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['surveys_count'], 4)
        self.assertEqual(response.data['active_surveys_count'], 2)
        self.assertEqual(response.data['responses_count'], 3)
        self.assertEqual(len(response.data['surveys']), 4)
        self.assertEqual(response.data['surveys'][0]['name'], 'Oldest survey')
        self.assertEqual(response.data['surveys'][1]['uuid'], str(scheduled_survey.uuid))
        self.assertEqual(response.data['surveys'][2]['response_count'], 1)
        self.assertIn(
            str(oldest_survey.uuid),
            [survey['uuid'] for survey in response.data['surveys']],
        )

    def test_select_question_requires_choices(self):
        response = self.client.post(
            '/api/surveys/',
            {
                'title': 'Invalid survey',
                'description': '',
                'questions': [
                    {
                        'text': 'Choose one',
                        'type': 'single_select',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_text_question_rejects_choices(self):
        response = self.client.post(
            '/api/surveys/',
            {
                'title': 'Invalid survey',
                'description': '',
                'questions': [
                    {
                        'text': 'Tell us more',
                        'type': 'text',
                        'choices': [{'text': 'Option'}],
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_survey_routes_require_bearer_token(self):
        self.client.credentials()

        response = self.client.get('/api/surveys/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_private_survey_with_allowed_emails(self):
        response = self.client.post(
            '/api/surveys/',
            {
                'title': 'Private feedback',
                'description': 'Only invited users',
                'is_public': False,
                'allowed_emails': [
                    'Responder@example.com',
                    'responder@example.com',
                ],
                'questions': [
                    {
                        'text': 'What do you think?',
                        'type': 'text',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data['is_public'])
        self.assertEqual(response.data['access_emails'], ['responder@example.com'])
        self.assertEqual(SurveyAccess.objects.count(), 1)

    def test_allowed_user_can_read_private_survey(self):
        responder = User.objects.create_user(
            username='responder',
            email='responder@example.com',
            password='StrongPass123!',
        )
        responder_token = Token.objects.create(user=responder)
        survey = Survey.objects.create(
            owner=self.user,
            title='Private survey',
            description='Invited only',
            is_public=False,
        )
        SurveyAccess.objects.create(survey=survey, email='responder@example.com')
        Question.objects.create(
            survey=survey,
            text='Tell us more',
            question_type=Question.QuestionType.TEXT,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {responder_token.key}')

        response = self.client.get(f'/api/surveys/{survey.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Private survey')

    def test_owner_can_read_survey_by_uuid(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='UUID survey',
            description='Lookup by UUID',
            is_public=False,
        )
        Question.objects.create(
            survey=survey,
            text='Tell us more',
            question_type=Question.QuestionType.TEXT,
        )

        response = self.client.get(f'/api/surveys/by-uuid/{survey.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'UUID survey')
        self.assertEqual(response.data['uuid'], str(survey.uuid))

    def test_non_allowed_user_cannot_read_private_survey(self):
        outsider = User.objects.create_user(
            username='outsider',
            email='outsider@example.com',
            password='StrongPass123!',
        )
        outsider_token = Token.objects.create(user=outsider)
        survey = Survey.objects.create(
            owner=self.user,
            title='Private survey',
            description='Invited only',
            is_public=False,
        )
        SurveyAccess.objects.create(survey=survey, email='responder@example.com')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {outsider_token.key}')

        response = self.client.get(f'/api/surveys/{survey.id}/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_survey_can_be_read_without_account(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Public survey',
            description='Open to everyone',
            is_public=True,
        )
        question = Question.objects.create(
            survey=survey,
            text='Pick one',
            question_type=Question.QuestionType.SINGLE_SELECT,
        )
        Choice.objects.create(question=question, text='Yes')
        self.client.credentials()

        response = self.client.get(f'/api/public/surveys/{survey.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Public survey')

    def test_public_survey_can_be_read_by_uuid_without_account(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Public UUID survey',
            description='Open to everyone',
            is_public=True,
        )
        question = Question.objects.create(
            survey=survey,
            text='Pick one',
            question_type=Question.QuestionType.SINGLE_SELECT,
        )
        Choice.objects.create(question=question, text='Yes')
        self.client.credentials()

        response = self.client.get(f'/api/public/surveys/by-uuid/{survey.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Public UUID survey')
        self.assertEqual(response.data['uuid'], str(survey.uuid))

    def test_private_survey_is_not_visible_on_public_routes(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Private survey',
            description='Requires account',
            is_public=False,
        )
        self.client.credentials()

        response = self.client.get(f'/api/public/surveys/{survey.id}/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_list_excludes_private_surveys(self):
        Survey.objects.create(
            owner=self.user,
            title='Public survey',
            description='Open',
            is_public=True,
        )
        Survey.objects.create(
            owner=self.user,
            title='Private survey',
            description='Closed',
            is_public=False,
        )
        self.client.credentials()

        response = self.client.get('/api/public/surveys/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [survey['title'] for survey in response.data]
        self.assertEqual(titles, ['Public survey'])

    def test_public_user_can_save_answers_without_account(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Public survey',
            description='Open',
            is_public=True,
        )
        single_question = Question.objects.create(
            survey=survey,
            text='Pick one',
            question_type=Question.QuestionType.SINGLE_SELECT,
        )
        single_choice = Choice.objects.create(question=single_question, text='Yes')
        multi_question = Question.objects.create(
            survey=survey,
            text='Pick many',
            question_type=Question.QuestionType.MULTI_SELECT,
            order=1,
        )
        first_multi_choice = Choice.objects.create(question=multi_question, text='A')
        second_multi_choice = Choice.objects.create(question=multi_question, text='B')
        text_question = Question.objects.create(
            survey=survey,
            text='Tell us more',
            question_type=Question.QuestionType.TEXT,
            order=2,
        )
        self.client.credentials()

        response = self.client.post(
            f'/api/surveys/{survey.id}/responses/',
            {
                'respondent_email': 'anon@example.com',
                'answers': [
                    {
                        'question': single_question.id,
                        'choice': single_choice.id,
                    },
                    {
                        'question': multi_question.id,
                        'choices': [first_multi_choice.id, second_multi_choice.id],
                    },
                    {
                        'question': text_question.id,
                        'text': 'Great survey',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SurveyResponse.objects.count(), 1)
        self.assertEqual(Answer.objects.count(), 3)
        self.assertEqual(response.data['respondent_email'], 'anon@example.com')

    def test_public_user_can_skip_optional_question(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Optional survey',
            description='Has optional question',
            is_public=True,
        )
        required_question = Question.objects.create(
            survey=survey,
            text='Required comment',
            question_type=Question.QuestionType.TEXT,
            required=True,
        )
        Question.objects.create(
            survey=survey,
            text='Optional comment',
            question_type=Question.QuestionType.TEXT,
            required=False,
            order=1,
        )
        self.client.credentials()

        response = self.client.post(
            f'/api/surveys/{survey.id}/responses/',
            {
                'respondent_email': 'optional@example.com',
                'answers': [
                    {
                        'question': required_question.id,
                        'text': 'Required answer',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SurveyResponse.objects.count(), 1)
        self.assertEqual(Answer.objects.count(), 1)

    def test_anonymous_public_response_requires_email(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Email required',
            description='Anonymous identity required',
            is_public=True,
        )
        question = Question.objects.create(
            survey=survey,
            text='Question',
            question_type=Question.QuestionType.TEXT,
        )
        self.client.credentials()

        response = self.client.post(
            f'/api/surveys/{survey.id}/responses/',
            {'answers': [{'question': question.id, 'text': 'Answer'}]},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('respondent_email', response.data)
        self.assertEqual(SurveyResponse.objects.count(), 0)

    def test_allowed_user_can_save_private_survey_answers(self):
        responder = User.objects.create_user(
            username='responder',
            email='responder@example.com',
            password='StrongPass123!',
        )
        responder_token = Token.objects.create(user=responder)
        survey = Survey.objects.create(
            owner=self.user,
            title='Private survey',
            description='Invited only',
            is_public=False,
        )
        SurveyAccess.objects.create(survey=survey, email='responder@example.com')
        question = Question.objects.create(
            survey=survey,
            text='Tell us more',
            question_type=Question.QuestionType.TEXT,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {responder_token.key}')

        response = self.client.post(
            f'/api/surveys/{survey.id}/responses/',
            {
                'answers': [
                    {
                        'question': question.id,
                        'text': 'Looks useful',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        saved_response = SurveyResponse.objects.get()
        self.assertEqual(saved_response.respondent, responder)

    def test_public_response_rejects_choice_from_other_question(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Public survey',
            description='Open',
            is_public=True,
        )
        question = Question.objects.create(
            survey=survey,
            text='Pick one',
            question_type=Question.QuestionType.SINGLE_SELECT,
        )
        other_question = Question.objects.create(
            survey=survey,
            text='Other',
            question_type=Question.QuestionType.SINGLE_SELECT,
        )
        other_choice = Choice.objects.create(question=other_question, text='Wrong')
        self.client.credentials()

        response = self.client.post(
            f'/api/surveys/{survey.id}/responses/',
            {
                'answers': [
                    {
                        'question': question.id,
                        'choice': other_choice.id,
                    },
                    {
                        'question': other_question.id,
                        'choice': other_choice.id,
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SurveyResponse.objects.count(), 0)

    def test_private_survey_response_requires_authentication(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Private survey',
            description='Closed',
            is_public=False,
        )
        question = Question.objects.create(
            survey=survey,
            text='Tell us more',
            question_type=Question.QuestionType.TEXT,
        )
        self.client.credentials()

        response = self.client.post(
            f'/api/surveys/{survey.id}/responses/',
            {
                'answers': [
                    {
                        'question': question.id,
                        'text': 'No token',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_can_partially_update_survey(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Old title',
            description='Old description',
            is_public=False,
        )
        Question.objects.create(
            survey=survey,
            text='Original question',
            question_type=Question.QuestionType.TEXT,
        )

        response = self.client.patch(
            f'/api/surveys/{survey.id}/',
            {
                'title': 'Updated title',
                'is_public': True,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        survey.refresh_from_db()
        self.assertEqual(survey.title, 'Updated title')
        self.assertTrue(survey.is_public)
        self.assertEqual(survey.questions.count(), 1)

    def test_owner_can_replace_questions_and_allowed_emails(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Editable survey',
            description='Before',
            is_public=False,
        )
        Question.objects.create(
            survey=survey,
            text='Old question',
            question_type=Question.QuestionType.TEXT,
        )
        SurveyAccess.objects.create(survey=survey, email='old@example.com')

        response = self.client.patch(
            f'/api/surveys/{survey.id}/',
            {
                'description': 'After',
                'allowed_emails': ['New@example.com'],
                'questions': [
                    {
                        'text': 'New single choice',
                        'type': 'single_select',
                        'choices': [
                            {'text': 'One'},
                            {'text': 'Two'},
                        ],
                    },
                    {
                        'text': 'New text',
                        'type': 'text',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        survey.refresh_from_db()
        self.assertEqual(survey.description, 'After')
        self.assertEqual(list(survey.access_entries.values_list('email', flat=True)), ['new@example.com'])
        self.assertEqual(survey.questions.count(), 2)
        self.assertEqual(Choice.objects.filter(question__survey=survey).count(), 2)

    def test_allowed_user_cannot_update_private_survey(self):
        responder = User.objects.create_user(
            username='responder-update',
            email='responder-update@example.com',
            password='StrongPass123!',
        )
        responder_token = Token.objects.create(user=responder)
        survey = Survey.objects.create(
            owner=self.user,
            title='Private survey',
            description='Invited only',
            is_public=False,
        )
        SurveyAccess.objects.create(survey=survey, email='responder-update@example.com')
        Question.objects.create(
            survey=survey,
            text='Tell us more',
            question_type=Question.QuestionType.TEXT,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {responder_token.key}')

        response = self.client.patch(
            f'/api/surveys/{survey.id}/',
            {'title': 'Not allowed'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        survey.refresh_from_db()
        self.assertEqual(survey.title, 'Private survey')

    def test_owner_can_delete_survey(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Delete me',
            description='Temporary',
            is_public=False,
        )
        Question.objects.create(
            survey=survey,
            text='Question',
            question_type=Question.QuestionType.TEXT,
        )

        response = self.client.delete(f'/api/surveys/{survey.id}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Survey.objects.filter(id=survey.id).exists())

    def test_allowed_user_cannot_delete_private_survey(self):
        responder = User.objects.create_user(
            username='delete-responder',
            email='delete-responder@example.com',
            password='StrongPass123!',
        )
        responder_token = Token.objects.create(user=responder)
        survey = Survey.objects.create(
            owner=self.user,
            title='Private survey',
            description='Invited only',
            is_public=False,
        )
        SurveyAccess.objects.create(survey=survey, email='delete-responder@example.com')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {responder_token.key}')

        response = self.client.delete(f'/api/surveys/{survey.id}/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Survey.objects.filter(id=survey.id).exists())

    def test_owner_can_view_survey_summary(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Summary survey',
            description='Has responses',
            is_public=True,
        )
        single_question = Question.objects.create(
            survey=survey,
            text='Pick one',
            question_type=Question.QuestionType.SINGLE_SELECT,
        )
        yes_choice = Choice.objects.create(question=single_question, text='Yes')
        Choice.objects.create(question=single_question, text='No')
        text_question = Question.objects.create(
            survey=survey,
            text='Comment',
            question_type=Question.QuestionType.TEXT,
            order=1,
        )
        survey_response = SurveyResponse.objects.create(
            survey=survey,
            respondent_email='person@example.com',
        )
        single_answer = Answer.objects.create(
            response=survey_response,
            question=single_question,
        )
        single_answer.selected_choices.set([yes_choice])
        Answer.objects.create(
            response=survey_response,
            question=text_question,
            text='Nice survey',
        )

        response = self.client.get(f'/api/surveys/{survey.id}/summary/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['response_count'], 1)
        self.assertEqual(len(response.data['questions']), 2)
        self.assertEqual(response.data['questions'][0]['choices'][0]['count'], 1)
        self.assertEqual(response.data['questions'][1]['text_answers'][0]['text'], 'Nice survey')

    def test_survey_response_rejects_before_open_time(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Future survey',
            description='Not open',
            is_public=True,
            open_at=timezone.now() + timedelta(days=1),
        )
        question = Question.objects.create(
            survey=survey,
            text='Question',
            question_type=Question.QuestionType.TEXT,
        )
        self.client.credentials()

        response = self.client.post(
            f'/api/surveys/{survey.id}/responses/',
            {'answers': [{'question': question.id, 'text': 'Too early'}]},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_survey_response_rejects_after_close_time(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Closed survey',
            description='Closed',
            is_public=True,
            close_at=timezone.now() - timedelta(days=1),
        )
        question = Question.objects.create(
            survey=survey,
            text='Question',
            question_type=Question.QuestionType.TEXT,
        )
        self.client.credentials()

        response = self.client.post(
            f'/api/surveys/{survey.id}/responses/',
            {'answers': [{'question': question.id, 'text': 'Too late'}]},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_authenticated_user_can_only_respond_once(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='One response',
            description='Only once',
            is_public=True,
        )
        question = Question.objects.create(
            survey=survey,
            text='Question',
            question_type=Question.QuestionType.TEXT,
        )
        payload = {'answers': [{'question': question.id, 'text': 'Answer'}]}

        first_response = self.client.post(
            f'/api/surveys/{survey.id}/responses/',
            payload,
            format='json',
        )
        second_response = self.client.post(
            f'/api/surveys/{survey.id}/responses/',
            payload,
            format='json',
        )

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SurveyResponse.objects.count(), 1)

    def test_respondent_email_can_only_respond_once(self):
        survey = Survey.objects.create(
            owner=self.user,
            title='Email once',
            description='Only once',
            is_public=True,
        )
        question = Question.objects.create(
            survey=survey,
            text='Question',
            question_type=Question.QuestionType.TEXT,
        )
        payload = {
            'respondent_email': 'Person@example.com',
            'answers': [{'question': question.id, 'text': 'Answer'}],
        }
        self.client.credentials()

        first_response = self.client.post(
            f'/api/surveys/{survey.id}/responses/',
            payload,
            format='json',
        )
        second_response = self.client.post(
            f'/api/surveys/{survey.id}/responses/',
            payload,
            format='json',
        )

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SurveyResponse.objects.count(), 1)
