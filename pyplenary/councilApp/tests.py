from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.test import TestCase, override_settings
from unittest.mock import Mock, patch

from .models import Delegate, Discussion, DiscussionParticipant, DiscussionSpeaker, Institution, Poll, Vote


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
        response.status_code = 200
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


class GmailAPIEmailBackendTests(TestCase):
    @override_settings(
        EMAIL_BACKEND="councilApp.email_backends.GmailAPIEmailBackend",
        GMAIL_CLIENT_ID="client-id",
        GMAIL_CLIENT_SECRET="client-secret",
        GMAIL_REFRESH_TOKEN="refresh-token",
        GMAIL_TOKEN_URL="https://oauth2.test/token",
        GMAIL_SEND_URL="https://gmail.test/send",
        GMAIL_API_TIMEOUT=5,
        DEFAULT_FROM_EMAIL="amsaassistant@gmail.com",
    )
    @patch("councilApp.email_backends.requests.post")
    def test_send_mail_refreshes_token_and_posts_raw_message(self, mock_post):
        token_response = Mock()
        token_response.status_code = 200
        token_response.json.return_value = {"access_token": "access-token"}
        token_response.raise_for_status.return_value = None

        send_response = Mock()
        send_response.status_code = 200
        send_response.raise_for_status.return_value = None

        mock_post.side_effect = [token_response, send_response]

        sent_count = send_mail(
            "Activation",
            "Plain text body",
            "amsaassistant@gmail.com",
            ["delegate@example.com"],
            html_message="<p>HTML body</p>",
        )

        self.assertEqual(sent_count, 1)
        self.assertEqual(mock_post.call_count, 2)

        token_call = mock_post.call_args_list[0]
        self.assertEqual(token_call.args[0], "https://oauth2.test/token")
        self.assertEqual(token_call.kwargs["data"]["refresh_token"], "refresh-token")
        self.assertEqual(token_call.kwargs["data"]["grant_type"], "refresh_token")

        send_call = mock_post.call_args_list[1]
        self.assertEqual(send_call.args[0], "https://gmail.test/send")
        self.assertEqual(send_call.kwargs["headers"]["Authorization"], "Bearer access-token")
        self.assertIn("raw", send_call.kwargs["json"])


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
            superadmin=True,
            account_role=Delegate.ROLE_REPRESENTATIVE,
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


class DiscussionTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name="University of Melbourne",
            shortName="UMelb",
            state="VIC",
            votesWeight=2,
            is_node=False,
        )
        self.mod_user = User.objects.create_user(
            username="moderator@example.com",
            email="moderator@example.com",
            password="password",
        )
        self.moderator = Delegate.objects.create(
            authClone=self.mod_user,
            name="Moderator",
            email="moderator@example.com",
            superadmin=False,
            account_role=Delegate.ROLE_MODERATOR,
            institution=self.institution,
            role="Moderator",
            speakerNum=1,
        )
        self.rep_user = User.objects.create_user(
            username="rep@example.com",
            email="rep@example.com",
            password="password",
        )
        self.rep = Delegate.objects.create(
            authClone=self.rep_user,
            name="Rep",
            email="rep@example.com",
            account_role=Delegate.ROLE_REPRESENTATIVE,
            institution=self.institution,
            role="Rep",
            speakerNum=2,
        )
        self.non_rep_user = User.objects.create_user(
            username="delegate@example.com",
            email="delegate@example.com",
            password="password",
        )
        self.non_rep = Delegate.objects.create(
            authClone=self.non_rep_user,
            name="Delegate",
            email="delegate@example.com",
            account_role=Delegate.ROLE_DELEGATE,
            institution=self.institution,
            role="Delegate",
            speakerNum=3,
        )
        self.client.login(username="moderator@example.com", password="password")

    def test_create_discussion_from_page_form(self):
        response = self.client.post(
            "/discussions/",
            {
                "title": "Budget discussion",
                "discussion_type": "informal",
                "default_speaker_seconds": 90,
            },
        )

        discussion = Discussion.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(discussion.moderator, self.moderator)
        self.assertEqual(discussion.default_speaker_seconds, 90)
        self.assertTrue(DiscussionParticipant.objects.filter(discussion=discussion, delegate=self.moderator).exists())

    def test_delegate_cannot_create_discussion(self):
        self.client.login(username="delegate@example.com", password="password")

        response = self.client.post(
            "/discussions/",
            {
                "title": "Unauthorised discussion",
                "discussion_type": "informal",
                "default_speaker_seconds": 90,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Discussion.objects.count(), 0)

    def test_formal_discussion_rejects_non_rep_speaker(self):
        discussion = Discussion.objects.create(
            title="Formal debate",
            moderator=self.moderator,
            discussion_type=Discussion.TYPE_FORMAL,
            default_speaker_seconds=60,
        )
        DiscussionParticipant.objects.create(discussion=discussion, delegate=self.non_rep)

        response = self.client.post(
            "/ajax/discussionAddSpeaker/",
            {"discussionId": discussion.id, "delegateId": self.non_rep.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(DiscussionSpeaker.objects.count(), 0)
        self.assertEqual(response.json()["error"], "formal_requires_rep")

    def test_moderator_can_add_participant_to_informal_speaker_queue(self):
        discussion = Discussion.objects.create(
            title="Informal discussion",
            moderator=self.moderator,
            discussion_type=Discussion.TYPE_INFORMAL,
            default_speaker_seconds=45,
        )
        DiscussionParticipant.objects.create(discussion=discussion, delegate=self.non_rep)

        response = self.client.post(
            "/ajax/discussionAddSpeaker/",
            {"discussionId": discussion.id, "delegateId": self.non_rep.id},
        )

        speaker = DiscussionSpeaker.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(speaker.delegate, self.non_rep)
        self.assertEqual(speaker.duration_seconds, 45)

    def test_viewer_cannot_join_speaker_queue(self):
        viewer_user = User.objects.create_user(
            username="viewer@example.com",
            email="viewer@example.com",
            password="password",
        )
        viewer = Delegate.objects.create(
            authClone=viewer_user,
            name="Viewer",
            email="viewer@example.com",
            account_role=Delegate.ROLE_VIEWER,
            institution=self.institution,
            role="Viewer",
            speakerNum=4,
        )
        discussion = Discussion.objects.create(
            title="Informal discussion",
            moderator=self.moderator,
            discussion_type=Discussion.TYPE_INFORMAL,
            default_speaker_seconds=45,
        )
        DiscussionParticipant.objects.create(discussion=discussion, delegate=viewer)
        self.client.login(username="viewer@example.com", password="password")

        response = self.client.post(
            "/ajax/discussionAddSpeaker/",
            {"discussionId": discussion.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(DiscussionSpeaker.objects.count(), 0)
        self.assertEqual(response.json()["error"], "cannot_speak")

    def test_original_moderator_can_add_moderator(self):
        co_mod_user = User.objects.create_user(
            username="co@example.com",
            email="co@example.com",
            password="password",
        )
        co_moderator = Delegate.objects.create(
            authClone=co_mod_user,
            name="Co Moderator",
            email="co@example.com",
            account_role=Delegate.ROLE_MODERATOR,
            institution=self.institution,
            role="Moderator",
            speakerNum=5,
        )
        discussion = Discussion.objects.create(
            title="Shared moderation",
            moderator=self.moderator,
            discussion_type=Discussion.TYPE_INFORMAL,
            default_speaker_seconds=45,
        )

        response = self.client.post(
            "/ajax/discussionAddModerator/",
            {"discussionId": discussion.id, "delegateId": co_moderator.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(discussion.additional_moderators.filter(id=co_moderator.id).exists())
        self.assertTrue(DiscussionParticipant.objects.filter(discussion=discussion, delegate=co_moderator).exists())

    def test_start_timer_promotes_next_waiting_speaker(self):
        discussion = Discussion.objects.create(
            title="Timer discussion",
            moderator=self.moderator,
            discussion_type=Discussion.TYPE_INFORMAL,
            default_speaker_seconds=30,
        )
        speaker = DiscussionSpeaker.objects.create(
            discussion=discussion,
            delegate=self.rep,
            index=1,
            duration_seconds=75,
        )

        response = self.client.post(
            "/ajax/discussionTimerAction/",
            {"discussionId": discussion.id, "action": "start"},
        )

        discussion.refresh_from_db()
        speaker.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(discussion.active)
        self.assertTrue(discussion.timer_running)
        self.assertEqual(discussion.current_speaker_id, speaker.id)
        self.assertEqual(discussion.timer_remaining_seconds, 75)
        self.assertEqual(speaker.status, DiscussionSpeaker.STATUS_CURRENT)
