from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.test import TestCase, override_settings
from unittest.mock import Mock, patch

from .models import Delegate, Institution, Poll, Vote


class ResendEmailBackendTests(TestCase):
    @override_settings(
        EMAIL_BACKEND="councilApp.email_backends.ResendEmailBackend",
        RESEND_API_KEY="test-api-key",
        RESEND_API_URL="https://api.resend.test/emails",
        RESEND_TIMEOUT=5,
        DEFAULT_FROM_EMAIL="PyPlenary <no-reply@example.com>",
    )
    @patch("councilApp.email_backends.requests.post")
    def test_send_mail_posts_to_resend_api(self, mock_post):
        response = Mock()
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        sent_count = send_mail(
            "Activation",
            "Plain text body",
            "PyPlenary <no-reply@example.com>",
            ["delegate@example.com"],
            html_message="<p>HTML body</p>",
        )

        self.assertEqual(sent_count, 1)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-api-key")
        self.assertEqual(kwargs["json"]["to"], ["delegate@example.com"])
        self.assertEqual(kwargs["json"]["subject"], "Activation")
        self.assertEqual(kwargs["json"]["text"], "Plain text body")
        self.assertEqual(kwargs["json"]["html"], "<p>HTML body</p>")


class AdminWithoutDelegateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin@example.com",
            email="admin@example.com",
            password="password",
        )
        self.client.login(username="admin@example.com", password="password")

    def test_home_renders_without_delegate_profile(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

    def test_profile_renders_helpful_message_without_delegate_profile(self):
        response = self.client.get("/profile/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not linked to a council delegate profile yet")


class MutatingEndpointMethodTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name="University of Melbourne",
            shortName="UMelb",
            state="VIC",
            votesWeight=2,
            is_node=False,
        )
        self.user = User.objects.create_user(
            username="delegate@example.com",
            email="delegate@example.com",
            password="password",
        )
        self.delegate = Delegate.objects.create(
            authClone=self.user,
            name="Test Delegate",
            email="delegate@example.com",
            rep=True,
            superadmin=True,
            institution=self.institution,
            role="Delegate",
            speakerNum=1,
        )
        self.client.login(username="delegate@example.com", password="password")

    def test_close_poll_requires_post(self):
        poll = Poll.objects.create(title="Motion", active=True)

        response = self.client.get(f"/poll/close/{poll.id}/")

        poll.refresh_from_db()
        self.assertEqual(response.status_code, 405)
        self.assertTrue(poll.active)

    def test_close_poll_post_closes_poll(self):
        poll = Poll.objects.create(title="Motion", active=True)

        response = self.client.post(f"/poll/close/{poll.id}/")

        poll.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(poll.active)

    def test_submit_votes_requires_post(self):
        poll = Poll.objects.create(title="Motion", active=True)

        response = self.client.get(
            "/ajax/submitVotes/",
            {"pollId": poll.id, "checkedIds[]": ["ownRadio_1"]},
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(Vote.objects.count(), 0)

    def test_submit_votes_post_records_vote(self):
        poll = Poll.objects.create(title="Motion", active=True, weighted=True)

        response = self.client.post(
            "/ajax/submitVotes/",
            {"pollId": poll.id, "checkedIds[]": ["ownRadio_1"]},
        )

        vote = Vote.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(vote.voter, self.delegate)
        self.assertEqual(vote.vote, 1)
        self.assertEqual(vote.voteWeight, self.institution.votesWeight)
