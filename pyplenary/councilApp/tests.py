from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Q
from django.test import TestCase, override_settings
from unittest.mock import Mock, patch

from .models import AgendaDay, AgendaItem, Delegate, Discussion, DiscussionEvent, DiscussionParticipant, DiscussionQuestion, DiscussionQuestionReaction, DiscussionSpeaker, Institution, PendingRego, Poll, Proxy, Vote


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


class AgendaEditorTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name="University of Melbourne",
            shortName="UMelb",
            state="VIC",
            votesWeight=2,
            is_node=False,
        )
        self.user = User.objects.create_user(
            username="admin@example.com",
            email="admin@example.com",
            password="password",
        )
        self.delegate = Delegate.objects.create(
            authClone=self.user,
            name="Agenda Admin",
            email="admin@example.com",
            account_role=Delegate.ROLE_ADMIN,
            institution=self.institution,
            role="Admin",
            speakerNum=1,
        )
        self.client.login(username="admin@example.com", password="password")

    def test_bulk_save_updates_days_and_items_without_redirect(self):
        response = self.client.post(
            "/agenda/",
            {
                "action": "save_agenda",
                "day_key": ["new-day-1"],
                "day_id": [""],
                "day_title": ["Day One"],
                "day_date": ["24 June 2026"],
                "day_order": ["1"],
                "item_key": ["new-item-1"],
                "item_day_key": ["new-day-1"],
                "item_id": [""],
                "item_time": ["9:00 AM"],
                "item_title": ["Opening"],
                "item_color": ["#198754"],
                "item_order": ["1"],
                "item_badge": ["Session"],
                "item_category": ["Governance"],
                "item_links": ["[Agenda pack](https://example.com)"],
                "item_content": ["Welcome and setup."],
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        day = AgendaDay.objects.get()
        item = AgendaItem.objects.get()
        self.assertEqual(day.title, "Day One")
        self.assertEqual(item.day, day)
        self.assertEqual(item.title, "Opening")
        self.assertEqual(item.color, "#198754")


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

    def test_proxy_vote_display_delegate_is_holder(self):
        holder_user = User.objects.create_user(
            username="holder@example.com",
            email="holder@example.com",
            password="password",
        )
        holder = Delegate.objects.create(
            authClone=holder_user,
            name="Proxy Holder",
            email="holder@example.com",
            account_role=Delegate.ROLE_REPRESENTATIVE,
            institution=self.institution,
            role="Delegate",
            speakerNum=2,
        )
        poll = Poll.objects.create(title="Motion", active=True)
        proxy = Proxy.objects.create(voter=self.delegate, holder=holder)

        vote = Vote.objects.create(poll=poll, voter=self.delegate, proxy=proxy, vote=1)

        self.assertEqual(vote.display_delegate, holder)


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

    def test_moderator_can_update_discussion_settings(self):
        discussion = Discussion.objects.create(
            title="Settings discussion",
            moderator=self.moderator,
            discussion_type=Discussion.TYPE_INFORMAL,
            default_speaker_seconds=30,
            timer_remaining_seconds=30,
        )
        rep_speaker = DiscussionSpeaker.objects.create(
            discussion=discussion,
            delegate=self.rep,
            index=1,
            duration_seconds=30,
        )
        non_rep_speaker = DiscussionSpeaker.objects.create(
            discussion=discussion,
            delegate=self.non_rep,
            index=2,
            duration_seconds=30,
        )

        response = self.client.post(
            "/ajax/discussionSettings/",
            {
                "discussionId": discussion.id,
                "title": "Updated settings",
                "discussionType": Discussion.TYPE_FORMAL,
                "defaultSpeakerSeconds": 120,
                "applyDefaultToQueue": "true",
            },
        )

        discussion.refresh_from_db()
        rep_speaker.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(discussion.title, "Updated settings")
        self.assertEqual(discussion.discussion_type, Discussion.TYPE_FORMAL)
        self.assertEqual(discussion.default_speaker_seconds, 120)
        self.assertEqual(discussion.timer_remaining_seconds, 120)
        self.assertEqual(rep_speaker.duration_seconds, 120)
        self.assertFalse(DiscussionSpeaker.objects.filter(id=non_rep_speaker.id).exists())
        self.assertTrue(DiscussionEvent.objects.filter(event_type="settings_update").exists())

    def test_discussion_question_can_be_posted_and_replied_to(self):
        discussion = Discussion.objects.create(
            title="Questions",
            moderator=self.moderator,
            discussion_type=Discussion.TYPE_INFORMAL,
            default_speaker_seconds=30,
        )

        response = self.client.post(
            "/ajax/discussionQuestionAdd/",
            {"discussionId": discussion.id, "text": "What is the timeline?"},
        )
        question = DiscussionQuestion.objects.get()

        reply_response = self.client.post(
            "/ajax/discussionQuestionAdd/",
            {"discussionId": discussion.id, "parentId": question.id, "text": "Following this too."},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(reply_response.status_code, 200)
        self.assertEqual(DiscussionQuestion.objects.count(), 2)
        self.assertEqual(DiscussionQuestion.objects.exclude(id=question.id).get().parent, question)
        self.assertTrue(DiscussionEvent.objects.filter(Q(message__contains='Following this too.') & Q(message__contains='What is the timeline?')).exists())

    def test_author_can_edit_and_delete_discussion_question(self):
        discussion = Discussion.objects.create(
            title="Questions",
            moderator=self.moderator,
            discussion_type=Discussion.TYPE_INFORMAL,
            default_speaker_seconds=30,
        )
        question = DiscussionQuestion.objects.create(
            discussion=discussion,
            author=self.moderator,
            text="Original question",
        )

        edit_response = self.client.post(
            "/ajax/discussionQuestionEdit/",
            {"questionId": question.id, "text": "Edited question"},
        )
        question.refresh_from_db()
        delete_response = self.client.post(
            "/ajax/discussionQuestionDelete/",
            {"questionId": question.id},
        )

        self.assertEqual(edit_response.status_code, 200)
        self.assertEqual(question.text, "Edited question")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(DiscussionQuestion.objects.count(), 0)

    def test_discussion_question_reaction_toggles(self):
        discussion = Discussion.objects.create(
            title="Questions",
            moderator=self.moderator,
            discussion_type=Discussion.TYPE_INFORMAL,
            default_speaker_seconds=30,
        )
        question = DiscussionQuestion.objects.create(
            discussion=discussion,
            author=self.moderator,
            text="Support?",
        )

        first = self.client.post(
            "/ajax/discussionQuestionReact/",
            {"questionId": question.id, "reaction": "heart"},
        )
        second = self.client.post(
            "/ajax/discussionQuestionReact/",
            {"questionId": question.id, "reaction": "heart"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(DiscussionQuestionReaction.objects.count(), 0)

    def test_duplicate_delegate_email_activation_shows_error(self):
        pending = PendingRego.objects.create(
            token="duplicate-token",
            active=True,
            name="Duplicate",
            email=self.moderator.email,
            institution=self.institution,
            account_role=Delegate.ROLE_MODERATOR,
            role="Delegate",
        )

        response = self.client.get(f"/activate/{pending.token}/")

        pending.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already has an active account")
        self.assertFalse(pending.active)
