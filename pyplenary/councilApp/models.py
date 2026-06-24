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
    id = models.AutoField(primary_key=True)
    authClone = models.OneToOneField(User, models.PROTECT, db_column='authClone', null=True)
    name = models.CharField(max_length=100, null=True)
    email = models.EmailField(max_length=254, null=True, blank=True, unique=True)
    rep = models.BooleanField(default=False)
    superadmin = models.BooleanField(default=False)
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

    def to_json(self):
        return {
            'id': self.id,
            'name': self.name,
            'role': self.role,
            'speakerNum': self.speakerNum,
            'first_time': self.first_time,
            'rep': self.rep,
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
    role = models.CharField(max_length=200, null=True)
    pronouns = models.CharField(max_length=100, null=True)
    firstTime = models.BooleanField(default=False)

    class Meta:
        db_table = 'PendingRego'


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
        return delegate is not None and (self.moderator_id == delegate.id or delegate.superadmin)

    def timer_remaining(self):
        if not self.timer_running or not self.timer_started_at:
            return self.timer_remaining_seconds
        elapsed = int((timezone.now() - self.timer_started_at).total_seconds())
        return max(0, self.timer_remaining_seconds - elapsed)

    def next_waiting_speaker(self):
        return self.speakers.filter(status=DiscussionSpeaker.STATUS_WAITING).order_by('index').first()

    @staticmethod
    def discussions_for_ws(delegate=None):
        discussions = Discussion.objects.filter(archived=False).select_related(
            'moderator',
            'moderator__institution',
            'current_speaker',
            'current_speaker__delegate',
            'current_speaker__delegate__institution',
        ).prefetch_related(
            'participants__delegate',
            'participants__delegate__institution',
            'speakers__delegate',
            'speakers__delegate__institution',
        )
        return [discussion.to_json(delegate) for discussion in discussions]

    def to_json(self, delegate=None):
        participants = [participant.to_json() for participant in self.participants.all()]
        speakers = [speaker.to_json() for speaker in self.speakers.all().order_by('index')]
        current = self.current_speaker.to_json() if self.current_speaker else None
        next_speaker = self.next_waiting_speaker()
        return {
            'id': self.id,
            'title': self.title,
            'moderator': self.moderator.to_json(),
            'discussion_type': self.discussion_type,
            'default_speaker_seconds': self.default_speaker_seconds,
            'active': self.active,
            'timer_running': self.timer_running,
            'timer_remaining_seconds': self.timer_remaining(),
            'current_speaker': current,
            'next_speaker': next_speaker.to_json() if next_speaker else None,
            'participants': participants,
            'speakers': speakers,
            'user_is_moderator': self.user_can_moderate(delegate),
            'user_is_participant': any(participant['delegate']['id'] == getattr(delegate, 'id', None) for participant in participants),
            'user_is_on_speaker_list': any(speaker['delegate']['id'] == getattr(delegate, 'id', None) and speaker['status'] in ('waiting', 'current') for speaker in speakers),
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
