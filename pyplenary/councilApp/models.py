from django import forms
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Institution(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, null=True)
    shortName = models.CharField(max_length=100, null=True)
    state = models.CharField(max_length=100, null=True)
    votesWeight = models.IntegerField(default=1)
    is_node = models.BooleanField()

    class Meta:
        db_table = 'Institution'

    def __str__(self):
        output = f'{self.shortName} - {self.name}'
        return output

class Delegate(models.Model):
    ROLE_VIEWER = 'viewer'
    ROLE_DELEGATE = 'delegate'
    ROLE_REPRESENTATIVE = 'representative'
    ROLE_MODERATOR = 'moderator'
    ROLE_ADMIN = 'admin'
    ACCOUNT_ROLE_CHOICES = [
        (ROLE_VIEWER, 'Viewer'),
        (ROLE_DELEGATE, 'Delegate'),
        (ROLE_REPRESENTATIVE, 'Representative'),
        (ROLE_MODERATOR, 'Moderator'),
        (ROLE_ADMIN, 'Admin'),
    ]

    id = models.AutoField(primary_key=True)
    authClone = models.OneToOneField(User, models.PROTECT, db_column='authClone', null=True)
    name = models.CharField(max_length=100, null=True)
    email = models.EmailField(max_length=254, null=True, blank=True, unique=True)
    rep = models.BooleanField(default=False)
    superadmin = models.BooleanField(default=False)
    account_role = models.CharField(max_length=20, choices=ACCOUNT_ROLE_CHOICES, default=ROLE_DELEGATE)
    institution = models.ForeignKey(Institution, models.CASCADE, null=True)
    role = models.CharField(max_length=200, null=True)
    speakerNum = models.IntegerField(default=0)
    pronouns = models.CharField(max_length=100, null=True)
    first_time = models.BooleanField(default=False)

    class Meta:
        db_table = 'Delegate'

    def __str__(self):
        output = f'{self.name} ({self.institution.shortName})'
        return output

    def save(self, *args, **kwargs):
        self.rep = self.account_role == self.ROLE_REPRESENTATIVE
        super().save(*args, **kwargs)

    @property
    def can_create_discussions(self):
        return self.superadmin or self.account_role in [self.ROLE_MODERATOR, self.ROLE_ADMIN]

    @property
    def can_speak_in_informal_discussions(self):
        return self.account_role in [self.ROLE_DELEGATE, self.ROLE_REPRESENTATIVE, self.ROLE_MODERATOR, self.ROLE_ADMIN]

    @property
    def can_speak_in_formal_discussions(self):
        return self.account_role in [self.ROLE_REPRESENTATIVE, self.ROLE_ADMIN]

    @property
    def is_site_admin(self):
        return self.superadmin or self.account_role == self.ROLE_ADMIN

    def to_json(self):
        return {
            'id': self.id,
            'name': self.name,
            'role': self.role,
            'speakerNum': self.speakerNum,
            'first_time': self.first_time,
            'rep': self.rep,
            'account_role': self.account_role,
            'account_role_label': self.get_account_role_display(),
            'institution': self.institution.shortName if self.institution else '',
        }

class Poll(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=500, null=True)
    yesVotes = models.IntegerField(default=0)
    noVotes = models.IntegerField(default=0)
    abstainVotes = models.IntegerField(default=0)
    startTime = models.DateTimeField(auto_now_add=True, null=True)
    endTime = models.DateTimeField(null=True)
    active = models.BooleanField(default=False)
    anonymous = models.BooleanField(default=False)
    repsOnly = models.BooleanField(default=False)
    weighted = models.BooleanField(default=False)
    supermajority = models.BooleanField(default=False) #False for simple, True for super
    roll_call = models.BooleanField(default=False)
    outcome = models.IntegerField(default=0) # 0 for no result, 1 for pass, 2 for fail, 3 for chair's call

    # TODO: Separately store number of ballots and number of votes

    class Meta:
        db_table = 'Poll'

    def __str__(self):
        output = f'{self.id} - {self.title}'
        return output
    
    def describe(self):
        result = []
        result.append('AMSA Reps only' if self.repsOnly else 'Voting open to all')
        if self.roll_call:
            result.append('Roll call')
        result.append('Anonymous voting' if self.anonymous else 'Non-anonymous')
        result.append('Requires ⅔ supermajority' if self.supermajority else 'Requires ½ simple majority')
        result.append('Institutional-weighted votes' if self.weighted else 'Votes not weighted')
        return result

class Proxy(models.Model):
    id = models.AutoField(primary_key=True)
    voter = models.ForeignKey(Delegate, models.CASCADE, related_name='Proxy_voter')
    holder = models.ForeignKey(Delegate, models.CASCADE, related_name='Proxy_holder')
    active = models.BooleanField(default=True)
    activeTime = models.DateTimeField(auto_now_add=True, null=True)
    expiryTime = models.DateTimeField(null=True)

    class Meta:
        db_table = 'Proxy'

    def __str__(self):
        output = f'{self.holder.name} holds proxy for {self.voter.name}'
        return output

class Vote(models.Model):
    id = models.AutoField(primary_key=True)
    poll = models.ForeignKey(Poll, models.CASCADE)
    voter = models.ForeignKey(Delegate, models.CASCADE, related_name='Vote_voter')
    proxy = models.ForeignKey(Proxy, models.CASCADE, null=True)
    vote = models.IntegerField(default=0) # 0 for abstain, 1 for Yes, 2 for No 
    voteWeight = models.IntegerField(default=1)
    voteTime = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        db_table = 'Vote'

    def __str__(self):
        output = f'{self.poll.title} - {self.voter.institution} - {self.vote}'
        return output

    @property
    def display_delegate(self):
        return self.proxy.holder if self.proxy_id else self.voter

class ResetToken(models.Model):
    id = models.AutoField(primary_key=True)
    token = models.CharField(max_length=100, null=True)
    active = models.BooleanField(default = True)
    user = models.ForeignKey(User, models.DO_NOTHING, db_column = 'user', null=True)
    
    class Meta:
        db_table = 'ResetToken'

class PendingRego(models.Model):
    id = models.AutoField(primary_key=True)
    token = models.CharField(max_length=100, null=True)
    active = models.BooleanField(default = True)
    name = models.CharField(max_length=100, null=True)
    email = models.EmailField(max_length=254, null=True)
    institution = models.ForeignKey(Institution, models.CASCADE, null=True)
    account_role = models.CharField(max_length=20, choices=Delegate.ACCOUNT_ROLE_CHOICES, default=Delegate.ROLE_DELEGATE)
    role = models.CharField(max_length=200, null=True)
    pronouns = models.CharField(max_length=100, null=True)
    firstTime = models.BooleanField(default=False)

    class Meta:
        db_table = 'PendingRego'


class AdminAccessRequest(models.Model):
    delegate = models.OneToOneField(Delegate, models.CASCADE, related_name='admin_access_request')
    requested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'AdminAccessRequest'

    def __str__(self):
        return f'{self.delegate.name} requested admin access'


class AgendaDay(models.Model):
    title = models.CharField(max_length=120)
    date = models.CharField(max_length=80, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'AgendaDay'
        ordering = ['order', 'id']

    def __str__(self):
        return self.title


class AgendaItem(models.Model):
    day = models.ForeignKey(AgendaDay, models.CASCADE, related_name='items')
    time = models.CharField(max_length=40, blank=True)
    title = models.CharField(max_length=200)
    badge = models.CharField(max_length=80, blank=True)
    color = models.CharField(max_length=40, blank=True)
    category = models.CharField(max_length=120, blank=True)
    content = models.TextField(blank=True)
    links = models.TextField(blank=True, help_text='One markdown link or URL per line.')
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'AgendaItem'
        ordering = ['order', 'id']

    def __str__(self):
        return self.title

    @property
    def display_color(self):
        bootstrap_colors = {
            'primary': '#0d6efd',
            'secondary': '#6c757d',
            'success': '#198754',
            'danger': '#dc3545',
            'warning': '#ffc107',
            'info': '#0dcaf0',
            'light': '#f8f9fa',
            'dark': '#212529',
        }
        color = (self.color or '').strip()
        if color.startswith('#') and len(color) in {4, 7}:
            return color
        return bootstrap_colors.get(color, '#0d6efd')

    def links_list(self):
        return [line.strip() for line in self.links.splitlines() if line.strip()]


class Speaker(models.Model):
    """Legacy single-room speaker queue entry."""
    id = models.AutoField(primary_key=True)
    delegate = models.ForeignKey(Delegate, models.CASCADE)
    index = models.IntegerField()
    intention = models.IntegerField() # 0 = standard, 1 = point of order, 2 = for, 3 = against
    node = models.ForeignKey(Institution, models.CASCADE, null=True)
    
    class Meta:
        db_table = 'Speaker'
        ordering = ['index']
    
    # For legacy speaker queue websockets
    
    @staticmethod
    def speakers_for_ws():
        return [s.to_json() for s in Speaker.objects.all().select_related('delegate', 'delegate__institution', 'node')]
    
    def to_json(self):
        return {
            'delegate': {'id': self.delegate.id, 'name': self.delegate.name, 'role': self.delegate.role, 'speakerNum': self.delegate.speakerNum, 'first_time': self.delegate.first_time, 'institution': self.delegate.institution.shortName},
            'index': self.index,
            'intention': self.intention,
            'node': self.node.shortName if self.node is not None else '',
        }


class Discussion(models.Model):
    TYPE_INFORMAL = 'informal'
    TYPE_FORMAL = 'formal'
    DISCUSSION_TYPE_CHOICES = [
        (TYPE_INFORMAL, 'Informal'),
        (TYPE_FORMAL, 'Formal'),
    ]

    title = models.CharField(max_length=200)
    moderator = models.ForeignKey(Delegate, models.CASCADE, related_name='moderated_discussions')
    additional_moderators = models.ManyToManyField(Delegate, blank=True, related_name='co_moderated_discussions')
    discussion_type = models.CharField(max_length=20, choices=DISCUSSION_TYPE_CHOICES, default=TYPE_INFORMAL)
    default_speaker_seconds = models.PositiveIntegerField(default=60)
    active = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)
    current_speaker = models.ForeignKey('DiscussionSpeaker', models.SET_NULL, null=True, blank=True, related_name='current_for_discussions')
    timer_running = models.BooleanField(default=False)
    timer_started_at = models.DateTimeField(null=True, blank=True)
    timer_remaining_seconds = models.PositiveIntegerField(default=60)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'Discussion'
        ordering = ['-active', '-created_at']

    def __str__(self):
        return self.title

    def user_can_moderate(self, delegate):
        return delegate is not None and (
            self.moderator_id == delegate.id
            or delegate.is_site_admin
            or any(moderator.id == delegate.id for moderator in self.additional_moderators.all())
        )

    def user_can_manage_moderators(self, delegate):
        return delegate is not None and (self.moderator_id == delegate.id or delegate.is_site_admin)

    def status_label(self):
        if self.archived:
            return 'closed'
        if self.active:
            return 'active'
        return 'pending'

    def delegate_can_speak(self, delegate):
        if delegate is None:
            return False
        if self.discussion_type == self.TYPE_FORMAL:
            return delegate.can_speak_in_formal_discussions
        return delegate.can_speak_in_informal_discussions

    def timer_remaining(self):
        if not self.timer_running or not self.timer_started_at:
            return self.timer_remaining_seconds
        elapsed = int((timezone.now() - self.timer_started_at).total_seconds())
        return max(0, self.timer_remaining_seconds - elapsed)

    def next_waiting_speaker(self):
        return self.speakers.filter(status=DiscussionSpeaker.STATUS_WAITING).order_by('index').first()

    def waiting_speakers(self):
        return list(self.speakers.filter(status=DiscussionSpeaker.STATUS_WAITING).order_by('index'))

    @staticmethod
    def discussions_for_ws(delegate=None):
        discussions = Discussion.objects.all().select_related(
            'moderator',
            'moderator__institution',
            'current_speaker',
            'current_speaker__delegate',
            'current_speaker__delegate__institution',
        ).prefetch_related(
            'additional_moderators',
            'additional_moderators__institution',
            'participants__delegate',
            'participants__delegate__institution',
            'speakers__delegate',
            'speakers__delegate__institution',
            'questions__author',
            'questions__author__institution',
            'questions__reactions',
            'questions__reactions__delegate',
        )
        return [discussion.to_json(delegate) for discussion in discussions]

    def to_json(self, delegate=None):
        participants = [participant.to_json() for participant in self.participants.all()]
        speaker_objects = list(self.speakers.all())
        speakers = [speaker.to_json() for speaker in speaker_objects]
        questions = [question.to_json(delegate) for question in self.questions.all()]
        waiting_speakers = [speaker for speaker in speaker_objects if speaker.status == DiscussionSpeaker.STATUS_WAITING]
        current_speaker_object = self.current_speaker or (waiting_speakers[0] if waiting_speakers else None)
        next_speaker = self.next_waiting_speaker() if self.current_speaker else (waiting_speakers[1] if len(waiting_speakers) > 1 else None)
        moderator_options = []
        if self.user_can_manage_moderators(delegate):
            used_moderator_ids = [self.moderator_id] + list(self.additional_moderators.values_list('id', flat=True))
            moderator_options = [
                moderator.to_json()
                for moderator in Delegate.objects.filter(account_role=Delegate.ROLE_MODERATOR).exclude(id__in=used_moderator_ids).exclude(speakerNum=0).order_by('name')
            ]
        return {
            'id': self.id,
            'title': self.title,
            'moderator': self.moderator.to_json(),
            'discussion_type': self.discussion_type,
            'default_speaker_seconds': self.default_speaker_seconds,
            'active': self.active,
            'archived': self.archived,
            'status': self.status_label(),
            'timer_running': self.timer_running,
            'timer_remaining_seconds': self.timer_remaining(),
            'current_speaker': current_speaker_object.to_json() if current_speaker_object else None,
            'speaker_timer_started': self.current_speaker_id is not None,
            'next_speaker': next_speaker.to_json() if next_speaker else None,
            'participants': participants,
            'participant_count': len(participants),
            'additional_moderators': [moderator.to_json() for moderator in self.additional_moderators.all()],
            'moderator_options': moderator_options,
            'speakers': speakers,
            'questions': questions,
            'user_is_moderator': self.user_can_moderate(delegate),
            'user_can_manage_moderators': self.user_can_manage_moderators(delegate),
            'user_is_participant': any(participant['delegate']['id'] == getattr(delegate, 'id', None) for participant in participants),
            'user_is_on_speaker_queue': any(speaker['delegate']['id'] == getattr(delegate, 'id', None) and speaker['status'] in ('waiting', 'current') for speaker in speakers),
            'user_can_speak': self.delegate_can_speak(delegate),
        }


class DiscussionParticipant(models.Model):
    discussion = models.ForeignKey(Discussion, models.CASCADE, related_name='participants')
    delegate = models.ForeignKey(Delegate, models.CASCADE, related_name='discussion_participations')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'DiscussionParticipant'
        unique_together = ('discussion', 'delegate')
        ordering = ['joined_at']

    def __str__(self):
        return f'{self.delegate.name} in {self.discussion.title}'

    def to_json(self):
        return {
            'id': self.id,
            'delegate': self.delegate.to_json(),
        }


class DiscussionSpeaker(models.Model):
    STATUS_WAITING = 'waiting'
    STATUS_CURRENT = 'current'
    STATUS_DONE = 'done'
    STATUS_SKIPPED = 'skipped'
    STATUS_CHOICES = [
        (STATUS_WAITING, 'Waiting'),
        (STATUS_CURRENT, 'Current'),
        (STATUS_DONE, 'Done'),
        (STATUS_SKIPPED, 'Skipped'),
    ]

    discussion = models.ForeignKey(Discussion, models.CASCADE, related_name='speakers')
    delegate = models.ForeignKey(Delegate, models.CASCADE, related_name='discussion_speaker_entries')
    index = models.IntegerField()
    duration_seconds = models.PositiveIntegerField(default=60)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_WAITING)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'DiscussionSpeaker'
        ordering = ['index']

    def __str__(self):
        return f'{self.delegate.name} speaking in {self.discussion.title}'

    def to_json(self):
        return {
            'id': self.id,
            'delegate': self.delegate.to_json(),
            'index': self.index,
            'duration_seconds': self.duration_seconds,
            'status': self.status,
        }


class DiscussionQuestion(models.Model):
    discussion = models.ForeignKey(Discussion, models.CASCADE, related_name='questions')
    author = models.ForeignKey(Delegate, models.CASCADE, related_name='discussion_questions')
    parent = models.ForeignKey('self', models.CASCADE, null=True, blank=True, related_name='replies')
    text = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'DiscussionQuestion'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.author.name}: {self.text[:40]}'

    def to_json(self, delegate=None):
        reaction_counts = {}
        user_reactions = []
        for reaction in self.reactions.all():
            reaction_counts[reaction.reaction] = reaction_counts.get(reaction.reaction, 0) + 1
            if delegate is not None and reaction.delegate_id == delegate.id:
                user_reactions.append(reaction.reaction)
        return {
            'id': self.id,
            'discussion_id': self.discussion_id,
            'author': self.author.to_json(),
            'parent_id': self.parent_id,
            'text': self.text,
            'created_at': self.created_at.isoformat(),
            'reaction_counts': reaction_counts,
            'user_reactions': user_reactions,
        }


class DiscussionQuestionReaction(models.Model):
    REACTION_HEART = 'heart'
    REACTION_THUMBS_UP = 'thumbs_up'
    REACTION_THUMBS_DOWN = 'thumbs_down'
    REACTION_QUESTION = 'question'
    REACTION_CHOICES = [
        (REACTION_HEART, 'Heart'),
        (REACTION_THUMBS_UP, 'Thumbs up'),
        (REACTION_THUMBS_DOWN, 'Thumbs down'),
        (REACTION_QUESTION, 'Question'),
    ]

    question = models.ForeignKey(DiscussionQuestion, models.CASCADE, related_name='reactions')
    delegate = models.ForeignKey(Delegate, models.CASCADE, related_name='discussion_question_reactions')
    reaction = models.CharField(max_length=20, choices=REACTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'DiscussionQuestionReaction'
        unique_together = ('question', 'delegate', 'reaction')

    def __str__(self):
        return f'{self.delegate.name} {self.reaction} {self.question_id}'


class DiscussionEvent(models.Model):
    discussion = models.ForeignKey(Discussion, models.CASCADE, related_name='events')
    actor = models.ForeignKey(Delegate, models.SET_NULL, null=True, blank=True, related_name='discussion_events')
    event_type = models.CharField(max_length=80)
    message = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'DiscussionEvent'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.created_at}: {self.message}'
