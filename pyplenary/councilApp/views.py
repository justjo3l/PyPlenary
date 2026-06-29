import json
import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.models import User
from django.core.cache import caches
from django.core.mail import send_mail
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from django.http import JsonResponse, Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from .forms import *
from .models import *
from .utils import *
import csv
import datetime

channel_layer = get_channel_layer()
logger = logging.getLogger(__name__)


def current_delegate(request):
    return getattr(request.user, 'delegate', None) if request.user.is_authenticated else None


def current_user_is_site_admin(request):
    delegate = current_delegate(request)
    return delegate is not None and delegate.is_site_admin


def broadcast_discussions():
    async_to_sync(channel_layer.group_send)(
        'discussions',
        {'type': 'discussions_updated', 'discussions': Discussion.discussions_for_ws()},
    )


def discussion_or_404(discussion_id, include_archived=False):
    try:
        queryset = Discussion.objects.all() if include_archived else Discussion.objects.filter(archived=False)
        return queryset.get(id=discussion_id)
    except Discussion.DoesNotExist:
        raise Http404()


def require_discussion_moderator(request, discussion):
    delegate = current_delegate(request)
    if not discussion.user_can_moderate(delegate):
        return None
    return delegate


def seconds_from_request(request, field_name, default):
    try:
        seconds = int(request.POST.get(field_name, default))
    except (TypeError, ValueError):
        seconds = default
    return min(900, max(15, seconds))


def format_duration(seconds):
    seconds = max(0, int(seconds or 0))
    return f'{seconds // 60}:{seconds % 60:02d}'


def discussion_moderator_options(discussion):
    return Delegate.objects.filter(account_role=Delegate.ROLE_MODERATOR).exclude(
        id__in=[discussion.moderator_id] + list(discussion.additional_moderators.values_list('id', flat=True))
    ).exclude(speakerNum=0).order_by('name')


def log_discussion_event(discussion, actor, event_type, message):
    DiscussionEvent.objects.create(
        discussion=discussion,
        actor=actor,
        event_type=event_type,
        message=message[:500],
    )


def discussion_title_from_request(request, current_title):
    title = (request.POST.get('title') or '').strip()
    if not title or len(title) > 200:
        return None
    if title == current_title:
        return current_title
    return title

def index(request):
    return render(request, 'councilApp/index.html', {'active_tab':'index'})

@login_required
@ensure_csrf_cookie
def discussions(request):
    delegate = current_delegate(request)
    if delegate is None:
        return render(request, 'councilApp/authTemplates/noDelegate.html', {'active_tab':'discussions'})

    if request.method == 'POST':
        if not delegate.can_create_discussions:
            return HttpResponseForbidden()
        discussionForm = DiscussionCreateForm(request.POST)
        if discussionForm.is_valid():
            discussion = Discussion.objects.create(
                title=discussionForm.cleaned_data['title'],
                moderator=delegate,
                discussion_type=discussionForm.cleaned_data['discussion_type'],
                default_speaker_seconds=discussionForm.cleaned_data['default_speaker_seconds'],
                timer_remaining_seconds=discussionForm.cleaned_data['default_speaker_seconds'],
            )
            DiscussionParticipant.objects.get_or_create(discussion=discussion, delegate=delegate)
            log_discussion_event(discussion, delegate, 'discussion_create', f'{delegate.name} created the discussion.')
            broadcast_discussions()
            return redirect(f'/discussions/{discussion.id}/')
    else:
        discussionForm = DiscussionCreateForm()

    return render(request, 'councilApp/discussions.html', {
        'active_tab':'discussions',
        'discussionForm': discussionForm,
        'can_create_discussions': delegate.can_create_discussions,
    })


@login_required
@ensure_csrf_cookie
def discussionDetail(request, discussion_id):
    delegate = current_delegate(request)
    if delegate is None:
        return render(request, 'councilApp/authTemplates/noDelegate.html', {'active_tab':'discussions'})

    discussion = discussion_or_404(discussion_id, include_archived=True)
    return render(request, 'councilApp/discussion_detail.html', {
        'active_tab':'discussions',
        'discussion': discussion,
        'moderator_options': discussion_moderator_options(discussion),
    })


@login_required
def discussionLogs(request, discussion_id):
    delegate = current_delegate(request)
    discussion = discussion_or_404(discussion_id, include_archived=True)
    if not discussion.user_can_moderate(delegate):
        raise Http404()
    events = discussion.events.select_related('actor', 'actor__institution').order_by('-created_at')[:500]
    return render(request, 'councilApp/discussion_logs.html', {
        'active_tab': 'discussions',
        'discussion': discussion,
        'events': events,
    })

@login_required
@require_POST
def ajaxDiscussionJoin(request):
    delegate = current_delegate(request)
    if delegate is None:
        return JsonResponse({'raise404': True})
    discussion = discussion_or_404(request.POST.get('discussionId'))
    DiscussionParticipant.objects.get_or_create(discussion=discussion, delegate=delegate)
    log_discussion_event(discussion, delegate, 'join', f'{delegate.name} joined the discussion.')
    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionExit(request):
    delegate = current_delegate(request)
    if delegate is None:
        return JsonResponse({'raise404': True})
    discussion = discussion_or_404(request.POST.get('discussionId'))
    if discussion.moderator_id == delegate.id:
        return JsonResponse({'raise404': True, 'error': 'moderator_cannot_exit'})
    exiting_current_speaker = (
        discussion.current_speaker_id is not None
        and DiscussionSpeaker.objects.filter(id=discussion.current_speaker_id, delegate=delegate).exists()
    )
    DiscussionParticipant.objects.filter(discussion=discussion, delegate=delegate).delete()
    DiscussionSpeaker.objects.filter(discussion=discussion, delegate=delegate, status__in=[DiscussionSpeaker.STATUS_WAITING, DiscussionSpeaker.STATUS_CURRENT]).delete()
    if exiting_current_speaker:
        discussion.current_speaker = None
        discussion.timer_running = False
        discussion.save()
    log_discussion_event(discussion, delegate, 'exit', f'{delegate.name} left the discussion.')
    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionArchive(request):
    discussion = discussion_or_404(request.POST.get('discussionId'))
    if require_discussion_moderator(request, discussion) is None:
        return JsonResponse({'raise404': True})
    discussion.archived = True
    discussion.active = False
    discussion.timer_running = False
    discussion.save()
    log_discussion_event(discussion, current_delegate(request), 'close', f'{current_delegate(request).name} closed the discussion.')
    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionReopen(request):
    discussion = discussion_or_404(request.POST.get('discussionId'), include_archived=True)
    delegate = require_discussion_moderator(request, discussion)
    if delegate is None:
        return JsonResponse({'raise404': True})
    discussion.archived = False
    discussion.save()
    log_discussion_event(discussion, delegate, 'reopen', f'{delegate.name} reopened the discussion.')
    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionRename(request):
    discussion = discussion_or_404(request.POST.get('discussionId'), include_archived=True)
    delegate = require_discussion_moderator(request, discussion)
    if delegate is None:
        return JsonResponse({'raise404': True})
    title = discussion_title_from_request(request, discussion.title)
    if title is None:
        return JsonResponse({'raise404': True, 'error': 'invalid_title'})
    old_title = discussion.title
    discussion.title = title
    discussion.save()
    if old_title != title:
        log_discussion_event(discussion, delegate, 'rename', f'{delegate.name} renamed the discussion from "{old_title}" to "{title}".')
    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionTypeChange(request):
    discussion = discussion_or_404(request.POST.get('discussionId'))
    delegate = require_discussion_moderator(request, discussion)
    if delegate is None:
        return JsonResponse({'raise404': True})
    discussion_type = request.POST.get('discussionType')
    if discussion_type not in [Discussion.TYPE_INFORMAL, Discussion.TYPE_FORMAL]:
        return JsonResponse({'raise404': True})
    old_type = discussion.discussion_type
    discussion.discussion_type = discussion_type
    discussion.save()
    removed_count = 0
    if discussion_type == Discussion.TYPE_FORMAL:
        invalid_speakers = [
            speaker for speaker in DiscussionSpeaker.objects.filter(discussion=discussion, status__in=[DiscussionSpeaker.STATUS_WAITING, DiscussionSpeaker.STATUS_CURRENT]).select_related('delegate')
            if not discussion.delegate_can_speak(speaker.delegate)
        ]
        removed_count = len(invalid_speakers)
        if discussion.current_speaker_id in [speaker.id for speaker in invalid_speakers]:
            discussion.current_speaker = None
            discussion.timer_running = False
            discussion.save()
        DiscussionSpeaker.objects.filter(id__in=[speaker.id for speaker in invalid_speakers]).delete()
    message = f'{delegate.name} changed discussion type from {old_type} to {discussion_type}.'
    if removed_count:
        message += f' Removed {removed_count} ineligible speaker queue entr{"y" if removed_count == 1 else "ies"}.'
    log_discussion_event(discussion, delegate, 'type_change', message)
    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionSettings(request):
    discussion = discussion_or_404(request.POST.get('discussionId'), include_archived=True)
    delegate = require_discussion_moderator(request, discussion)
    if delegate is None:
        return JsonResponse({'raise404': True})

    title = discussion_title_from_request(request, discussion.title)
    if title is None:
        return JsonResponse({'raise404': True, 'error': 'invalid_title'})

    discussion_type = request.POST.get('discussionType')
    if discussion_type not in [Discussion.TYPE_INFORMAL, Discussion.TYPE_FORMAL]:
        return JsonResponse({'raise404': True, 'error': 'invalid_type'})

    default_seconds = seconds_from_request(request, 'defaultSpeakerSeconds', discussion.default_speaker_seconds)
    apply_default_to_queue = request.POST.get('applyDefaultToQueue') == 'true'

    with transaction.atomic():
        discussion = Discussion.objects.select_for_update().get(id=discussion.id)
        old_title = discussion.title
        old_type = discussion.discussion_type
        old_default_seconds = discussion.default_speaker_seconds

        discussion.title = title
        discussion.discussion_type = discussion_type
        discussion.default_speaker_seconds = default_seconds
        if old_default_seconds != default_seconds and discussion.current_speaker_id is None:
            discussion.timer_remaining_seconds = default_seconds
        discussion.save()

        updated_speakers_count = 0
        if apply_default_to_queue:
            updated_speakers_count = DiscussionSpeaker.objects.filter(
                discussion=discussion,
                status=DiscussionSpeaker.STATUS_WAITING,
            ).update(duration_seconds=default_seconds)

        removed_count = 0
        if discussion_type == Discussion.TYPE_FORMAL:
            invalid_speakers = [
                speaker for speaker in DiscussionSpeaker.objects.filter(discussion=discussion, status__in=[DiscussionSpeaker.STATUS_WAITING, DiscussionSpeaker.STATUS_CURRENT]).select_related('delegate')
                if not discussion.delegate_can_speak(speaker.delegate)
            ]
            removed_count = len(invalid_speakers)
            if discussion.current_speaker_id in [speaker.id for speaker in invalid_speakers]:
                discussion.current_speaker = None
                discussion.timer_running = False
                discussion.timer_started_at = None
                discussion.timer_remaining_seconds = discussion.default_speaker_seconds
                discussion.save()
            DiscussionSpeaker.objects.filter(id__in=[speaker.id for speaker in invalid_speakers]).delete()

        changes = []
        if old_title != discussion.title:
            changes.append(f'title from "{old_title}" to "{discussion.title}"')
        if old_type != discussion.discussion_type:
            changes.append(f'type from {old_type} to {discussion.discussion_type}')
        if old_default_seconds != discussion.default_speaker_seconds:
            changes.append(f'default speaker time from {format_duration(old_default_seconds)} to {format_duration(discussion.default_speaker_seconds)}')
        if updated_speakers_count:
            changes.append(f'applied the default time to {updated_speakers_count} queued speaker{"s" if updated_speakers_count != 1 else ""}')
        if removed_count:
            changes.append(f'removed {removed_count} ineligible speaker queue entr{"y" if removed_count == 1 else "ies"}')

        if changes:
            log_discussion_event(discussion, delegate, 'settings_update', f'{delegate.name} changed discussion settings: {", ".join(changes)}.')

    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionAddModerator(request):
    discussion = discussion_or_404(request.POST.get('discussionId'))
    if require_discussion_moderator(request, discussion) is None:
        return JsonResponse({'raise404': True})
    if not discussion.user_can_manage_moderators(current_delegate(request)):
        return JsonResponse({'raise404': True})
    try:
        moderator = Delegate.objects.get(id=request.POST.get('delegateId'), account_role=Delegate.ROLE_MODERATOR)
    except Delegate.DoesNotExist:
        return JsonResponse({'raise404': True})
    if moderator.id != discussion.moderator_id:
        discussion.additional_moderators.add(moderator)
        DiscussionParticipant.objects.get_or_create(discussion=discussion, delegate=moderator)
        log_discussion_event(discussion, current_delegate(request), 'moderator_add', f'{current_delegate(request).name} added {moderator.name} as a moderator.')
    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionAddSpeaker(request):
    delegate = current_delegate(request)
    if delegate is None:
        return JsonResponse({'raise404': True})
    discussion = discussion_or_404(request.POST.get('discussionId'))
    target_delegate_id = request.POST.get('delegateId') or delegate.id
    try:
        target = Delegate.objects.get(id=target_delegate_id)
    except Delegate.DoesNotExist:
        return JsonResponse({'raise404': True})

    is_self = target.id == delegate.id
    if not is_self and not discussion.user_can_moderate(delegate):
        return JsonResponse({'raise404': True})
    if not DiscussionParticipant.objects.filter(discussion=discussion, delegate=target).exists():
        return JsonResponse({'raise404': True, 'error': 'not_participant'})
    if not discussion.delegate_can_speak(target):
        error = 'formal_requires_rep' if discussion.discussion_type == Discussion.TYPE_FORMAL else 'cannot_speak'
        return JsonResponse({'raise404': True, 'error': error})
    if DiscussionSpeaker.objects.filter(discussion=discussion, delegate=target, status__in=[DiscussionSpeaker.STATUS_WAITING, DiscussionSpeaker.STATUS_CURRENT]).exists():
        return JsonResponse({'raise404': False})

    next_index = (DiscussionSpeaker.objects.filter(discussion=discussion).aggregate(Max('index'))['index__max'] or 0) + 1
    DiscussionSpeaker.objects.create(
        discussion=discussion,
        delegate=target,
        index=next_index,
        duration_seconds=discussion.default_speaker_seconds,
    )
    log_discussion_event(discussion, delegate, 'speaker_add', f'{target.name} joined the speaker queue.')
    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionRemoveSpeaker(request):
    speaker_id = request.POST.get('speakerId')
    try:
        speaker = DiscussionSpeaker.objects.select_related('discussion').get(id=speaker_id)
    except DiscussionSpeaker.DoesNotExist:
        return JsonResponse({'raise404': True})
    delegate = current_delegate(request)
    if require_discussion_moderator(request, speaker.discussion) is None and speaker.delegate_id != getattr(delegate, 'id', None):
        return JsonResponse({'raise404': True})
    discussion = speaker.discussion
    if discussion.current_speaker_id == speaker.id:
        discussion.current_speaker = None
        discussion.timer_running = False
        discussion.save()
    log_discussion_event(discussion, delegate, 'speaker_remove', f'{speaker.delegate.name} was removed from the speaker queue.')
    speaker.delete()
    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionReorderSpeakers(request):
    discussion = discussion_or_404(request.POST.get('discussionId'))
    if require_discussion_moderator(request, discussion) is None:
        return JsonResponse({'raise404': True})
    order = [int(x) for x in request.POST.get('order', '').split(',') if x]
    speakers = DiscussionSpeaker.objects.filter(discussion=discussion, id__in=order, status=DiscussionSpeaker.STATUS_WAITING)
    for speaker in speakers:
        speaker.index = order.index(speaker.id) + 1
        speaker.save()
    log_discussion_event(discussion, current_delegate(request), 'speaker_reorder', f'{current_delegate(request).name} reordered the speaker queue.')
    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionUpdateSpeakerTime(request):
    try:
        speaker = DiscussionSpeaker.objects.select_related('discussion').get(id=request.POST.get('speakerId'))
    except DiscussionSpeaker.DoesNotExist:
        return JsonResponse({'raise404': True})
    if require_discussion_moderator(request, speaker.discussion) is None:
        return JsonResponse({'raise404': True})
    speaker.duration_seconds = seconds_from_request(request, 'durationSeconds', speaker.duration_seconds)
    speaker.save()
    log_discussion_event(speaker.discussion, current_delegate(request), 'speaker_time', f'{current_delegate(request).name} changed {speaker.delegate.name} speaker time to {format_duration(speaker.duration_seconds)}.')
    if speaker.discussion.current_speaker_id == speaker.id:
        speaker.discussion.timer_remaining_seconds = speaker.duration_seconds
        speaker.discussion.timer_started_at = timezone.now() if speaker.discussion.timer_running else None
        speaker.discussion.save()
    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionTimerAction(request):
    discussion = discussion_or_404(request.POST.get('discussionId'))
    if require_discussion_moderator(request, discussion) is None:
        return JsonResponse({'raise404': True})
    action = request.POST.get('action')

    with transaction.atomic():
        discussion = Discussion.objects.select_for_update().get(id=discussion.id)
        current = discussion.current_speaker

        if action == 'activate':
            discussion.active = True
            discussion.save()
            log_discussion_event(discussion, current_delegate(request), 'discussion_start', f'{current_delegate(request).name} started the discussion.')
        elif action == 'pause' and current:
            discussion.timer_remaining_seconds = discussion.timer_remaining()
            discussion.timer_running = False
            discussion.timer_started_at = None
            discussion.save()
            log_discussion_event(discussion, current_delegate(request), 'timer_pause', f'{current_delegate(request).name} paused the timer for {current.delegate.name} at {format_duration(discussion.timer_remaining_seconds)}.')
        elif action == 'resume' and current:
            discussion.timer_running = True
            discussion.timer_started_at = timezone.now()
            discussion.save()
            log_discussion_event(discussion, current_delegate(request), 'timer_resume', f'{current_delegate(request).name} resumed the timer for {current.delegate.name} at {format_duration(discussion.timer_remaining_seconds)}.')
        elif action == 'restart' and current:
            discussion.timer_remaining_seconds = current.duration_seconds
            discussion.timer_running = True
            discussion.timer_started_at = timezone.now()
            discussion.save()
            log_discussion_event(discussion, current_delegate(request), 'timer_restart', f'{current_delegate(request).name} restarted the timer for {current.delegate.name} to {format_duration(discussion.timer_remaining_seconds)}.')
        elif action in ('skip', 'finish') and current:
            remaining_before_end = discussion.timer_remaining()
            current.status = DiscussionSpeaker.STATUS_SKIPPED if action == 'skip' else DiscussionSpeaker.STATUS_DONE
            current.save()
            discussion.current_speaker = None
            discussion.timer_running = False
            discussion.timer_started_at = None
            discussion.timer_remaining_seconds = discussion.default_speaker_seconds
            discussion.save()
            log_discussion_event(discussion, current_delegate(request), 'speaker_' + action, f'{current.delegate.name} was {"yielded/skipped" if action == "skip" else "marked finished"} with {format_duration(remaining_before_end)} remaining.')
        elif action == 'start':
            if not current:
                current = discussion.next_waiting_speaker()
                if not current:
                    return JsonResponse({'raise404': False, 'empty': True})
                current.status = DiscussionSpeaker.STATUS_CURRENT
                current.save()
                discussion.current_speaker = current
                discussion.timer_remaining_seconds = current.duration_seconds
                log_discussion_event(discussion, current_delegate(request), 'speaker_start', f'{current.delegate.name} started speaking.')
            discussion.active = True
            discussion.timer_running = True
            discussion.timer_started_at = timezone.now()
            discussion.save()
        else:
            return JsonResponse({'raise404': True})

    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionQuestionAdd(request):
    delegate = current_delegate(request)
    if delegate is None:
        return JsonResponse({'raise404': True})
    discussion = discussion_or_404(request.POST.get('discussionId'))
    if discussion.archived:
        return JsonResponse({'raise404': True, 'error': 'discussion_closed'})

    text = (request.POST.get('text') or '').strip()
    if not text:
        return JsonResponse({'raise404': True, 'error': 'empty_question'})
    if len(text) > 2000:
        return JsonResponse({'raise404': True, 'error': 'question_too_long'})

    parent = None
    parent_id = request.POST.get('parentId')
    if parent_id:
        try:
            parent = DiscussionQuestion.objects.get(id=parent_id, discussion=discussion)
        except DiscussionQuestion.DoesNotExist:
            return JsonResponse({'raise404': True, 'error': 'invalid_parent'})

    question = DiscussionQuestion.objects.create(
        discussion=discussion,
        author=delegate,
        parent=parent,
        text=text,
    )
    if parent:
        log_discussion_event(discussion, delegate, 'question_reply', f'{delegate.name} replied "{text}" to "{parent.text}".')
    else:
        log_discussion_event(discussion, delegate, 'question_add', f'{delegate.name} posted Q&A message "{question.text}".')
    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionQuestionEdit(request):
    delegate = current_delegate(request)
    if delegate is None:
        return JsonResponse({'raise404': True})
    try:
        question = DiscussionQuestion.objects.select_related('discussion', 'author').get(id=request.POST.get('questionId'))
    except DiscussionQuestion.DoesNotExist:
        return JsonResponse({'raise404': True})
    if question.discussion.archived or question.author_id != delegate.id:
        return JsonResponse({'raise404': True})
    text = (request.POST.get('text') or '').strip()
    if not text:
        return JsonResponse({'raise404': True, 'error': 'empty_question'})
    if len(text) > 2000:
        return JsonResponse({'raise404': True, 'error': 'question_too_long'})
    old_text = question.text
    question.text = text
    question.save()
    log_discussion_event(question.discussion, delegate, 'question_edit', f'{delegate.name} edited Q&A message from "{old_text}" to "{text}".')
    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionQuestionDelete(request):
    delegate = current_delegate(request)
    if delegate is None:
        return JsonResponse({'raise404': True})
    try:
        question = DiscussionQuestion.objects.select_related('discussion', 'author').get(id=request.POST.get('questionId'))
    except DiscussionQuestion.DoesNotExist:
        return JsonResponse({'raise404': True})
    if question.discussion.archived or question.author_id != delegate.id:
        return JsonResponse({'raise404': True})
    text = question.text
    discussion = question.discussion
    question.delete()
    log_discussion_event(discussion, delegate, 'question_delete', f'{delegate.name} deleted Q&A message "{text}".')
    broadcast_discussions()
    return JsonResponse({'raise404': False})


@login_required
@require_POST
def ajaxDiscussionQuestionReact(request):
    delegate = current_delegate(request)
    if delegate is None:
        return JsonResponse({'raise404': True})
    try:
        question = DiscussionQuestion.objects.select_related('discussion').get(id=request.POST.get('questionId'))
    except DiscussionQuestion.DoesNotExist:
        return JsonResponse({'raise404': True})
    if question.discussion.archived:
        return JsonResponse({'raise404': True, 'error': 'discussion_closed'})

    reaction = request.POST.get('reaction')
    valid_reactions = [choice[0] for choice in DiscussionQuestionReaction.REACTION_CHOICES]
    if reaction not in valid_reactions:
        return JsonResponse({'raise404': True, 'error': 'invalid_reaction'})

    existing = DiscussionQuestionReaction.objects.filter(question=question, delegate=delegate, reaction=reaction)
    if existing.exists():
        existing.delete()
        log_discussion_event(question.discussion, delegate, 'question_reaction_remove', f'{delegate.name} removed a {reaction} reaction from a Q&A message.')
    else:
        DiscussionQuestionReaction.objects.create(question=question, delegate=delegate, reaction=reaction)
        log_discussion_event(question.discussion, delegate, 'question_reaction', f'{delegate.name} reacted {reaction} to a Q&A message.')
    broadcast_discussions()
    return JsonResponse({'raise404': False})

@login_required
@require_POST
def ajaxSpeakerAdd(request):
    # FIXME: Acquire lock to prevent race conditions

    Speaker.objects.filter(delegate=request.user.delegate).delete()

    action = request.POST.get('action')
    location = request.POST.get('location', '')

    if action == 'remove':
        speakers = Speaker.speakers_for_ws()
        async_to_sync(channel_layer.group_send)('speakerlist', {'type': 'speakerlist_updated', 'mode': caches['default'].get('speaker_mode', 'standard'), 'speakerlist': speakers})
        return HttpResponse()

    speaker = Speaker()
    speaker.delegate = request.user.delegate
    speaker.index = (Speaker.objects.all().aggregate(Max('index'))['index__max'] or 0) + 1

    if action == 'add':
        speaker.intention = 0
    elif action == 'point_order':
        speaker.intention = 1
    elif action == 'add-for':
        speaker.intention = 2
    elif action == 'add-against':
        speaker.intention = 3
    else:
        return HttpResponseBadRequest('Unknown action')

    if location == '':
        speaker.node = None
    else:
        speaker.node = Institution.objects.get(id=location)

    speaker.save()

    speakers = Speaker.speakers_for_ws()
    async_to_sync(channel_layer.group_send)('speakerlist', {'type': 'speakerlist_updated', 'mode': caches['default'].get('speaker_mode', 'standard'), 'speakerlist': speakers})
    return HttpResponse()

@login_required
@require_POST
def ajaxSpeakerRemove(request):
    if not request.user.delegate.is_site_admin:
        return HttpResponseForbidden()
    
    Speaker.objects.filter(delegate__id=request.POST.get('delegateId')).delete()
    
    speakers = Speaker.speakers_for_ws()
    async_to_sync(channel_layer.group_send)('speakerlist', {'type': 'speakerlist_updated', 'mode': caches['default'].get('speaker_mode', 'standard'), 'speakerlist': speakers})
    return HttpResponse()

@login_required
@require_POST
def ajaxSpeakersReorder(request):
    if not request.user.delegate.is_site_admin:
        return HttpResponseForbidden()
    
    order = [int(x) for x in request.POST.get('order', '').split(',') if x]
    for speaker in Speaker.objects.filter(delegate__id__in=order).select_related('delegate'):
        speaker.index = order.index(speaker.delegate.id)
        speaker.save()
    
    speakers = Speaker.speakers_for_ws()
    async_to_sync(channel_layer.group_send)('speakerlist', {'type': 'speakerlist_updated', 'mode': caches['default'].get('speaker_mode', 'standard'), 'speakerlist': speakers})
    return HttpResponse()

@login_required
@require_POST
def ajaxChangeSpeakingMode(request):
    if not request.user.delegate.is_site_admin:
        return HttpResponseForbidden()
    
    mode = request.POST.get('mode', 'standard')
    caches['default'].set('speaker_mode', mode, timeout=None)
    
    speakers = Speaker.speakers_for_ws()
    async_to_sync(channel_layer.group_send)('speakerlist', {'type': 'speakerlist_updated', 'mode': mode, 'speakerlist': speakers})
    return HttpResponse()

@login_required
@require_POST
def ajaxSpeakersClear(request):
    if not request.user.delegate.is_site_admin:
        return HttpResponseForbidden()
    
    Speaker.objects.all().delete()
    async_to_sync(channel_layer.group_send)('speakerlist', {'type': 'speakerlist_updated', 'mode': caches['default'].get('speaker_mode', 'standard'), 'speakerlist': []})
    return HttpResponse()

def delegates(request):
    if request.user.is_authenticated:
        allDelegates = [request.user.delegate] + list(Delegate.objects.exclude(authClone=request.user).exclude(speakerNum=0).filter(rep=True).order_by('speakerNum')) + list(Delegate.objects.exclude(authClone=request.user).exclude(speakerNum=0).filter(rep=False).order_by('speakerNum'))
    else:
        allDelegates = list(Delegate.objects.exclude(speakerNum=0).filter(rep=True).order_by('speakerNum')) + list(Delegate.objects.exclude(speakerNum=0).filter(rep=False).order_by('speakerNum'))
    return render(request, 'councilApp/delegates.html', {'allDelegates':allDelegates, 'active_tab':'delegates'})

@login_required
@ensure_csrf_cookie
def proxy(request):
    delegate = request.user.delegate

    proxiesForMe = Proxy.objects.filter(voter=delegate, active=True)
    proxiesIHold = Proxy.objects.filter(holder=delegate, active=True)

    allDelegates = sorted(Delegate.objects.exclude(id=delegate.id).exclude(speakerNum=0), key=lambda x:x.speakerNum)

    return render(request, 'councilApp/proxy.html', {'delegate':delegate, 'proxiesForMe':proxiesForMe, 'proxiesIHold':proxiesIHold,
        'allDelegates':allDelegates, 'active_tab':'proxy'})

@login_required
@require_POST
def proxyNominate(request):
    try:
        delegate = request.user.delegate
        candidateId = request.POST.get('candidateId', None)
        holder = Delegate.objects.get(id=candidateId)
    except:
        return JsonResponse({'raise404':True, 'newProxy':None})
    
    proxiesForMe = Proxy.objects.filter(voter=delegate, active=True)
    if proxiesForMe:
        return JsonResponse({'raise404':True, 'newProxy':None})

    newProxy = Proxy()
    newProxy.voter = delegate
    newProxy.holder = holder
    newProxy.save()

    data = {'raise404':False, 'newProxy':[holder.name, holder.institution.shortName]}
    return JsonResponse(data)

@login_required
@require_POST
def proxyRetract(request):
    try:
        delegate = request.user.delegate
        proxiesForMe = Proxy.objects.filter(voter=delegate, active=True)
    except:
        return JsonResponse({'raise404':True, 'oldProxy':None})
    if len(proxiesForMe) != 1:
        return JsonResponse({'raise404':True, 'oldProxy':None})
    activeProxy = proxiesForMe[0]
    activeProxy.active = False
    activeProxy.expiryTime = timezone.now()
    activeProxy.save()

    data = {'raise404':False, 'oldProxy':[activeProxy.holder.name, activeProxy.holder.institution.shortName]}
    return JsonResponse(data)

@login_required
@require_POST
def proxyResign(request):
    try:
        delegate = request.user.delegate
        proxyId = request.POST.get('proxyId', None)
        activeProxy = Proxy.objects.get(id=proxyId, active=True)
    except:
        return JsonResponse({'raise404':True, 'oldProxy':None})
    if not activeProxy.active:
        return JsonResponse({'raise404':True, 'oldProxy':None})

    activeProxy.active = False
    activeProxy.expiryTime = timezone.now()
    activeProxy.save()

    data = {'raise404':False, 'oldProxy':[activeProxy.holder.name, activeProxy.holder.institution.shortName]}
    return JsonResponse(data)

@login_required
@ensure_csrf_cookie
def poll(request):
    allPolls = sorted(Poll.objects.all(), key=lambda x:-x.id)
    delegate = request.user.delegate if request.user.is_authenticated else None
    superadmin = delegate.is_site_admin if delegate is not None else False
    rep = delegate.rep if delegate is not None else False
    activePolls = [i for i in allPolls if i.active and eligibleToVote(delegate, i)]
    return render(request, 'councilApp/poll.html', {'allPolls':allPolls, 'superadmin':superadmin, 'rep':rep, 'activePolls':activePolls,
        'active_tab':'poll'})

@login_required
def createPoll(request):
    if not request.user.delegate.is_site_admin:
        raise Http404()

    if request.method == 'POST':
        pollForm = StartPollForm(request.POST)
        if pollForm.is_valid():
            newPoll = Poll()
            newPoll.title = pollForm.cleaned_data.get('title')
            newPoll.anonymous = pollForm.cleaned_data.get('anonymous')
            newPoll.roll_call = pollForm.cleaned_data.get('roll_call')
            newPoll.repsOnly = pollForm.cleaned_data.get('repsOnly')
            newPoll.weighted = pollForm.cleaned_data.get('weighted')
            newPoll.supermajority = pollForm.cleaned_data.get('majority') == 'super'
            newPoll.active = True
            newPoll.save()
            return redirect(f'/poll/{newPoll.id}')
    else:
        pollForm = StartPollForm()
        
    return render(request, 'councilApp/pollCreate.html', {'pollForm':pollForm, 'active':False, 'active_tab':'poll'})
    
@login_required
@require_POST
def closePoll(request, pollId):
    if not request.user.delegate.is_site_admin:
        raise Http404()
    try:
        activePoll = Poll.objects.filter(id = pollId, active=True)[0]
    except:
        raise Http404()
    
    activePoll.endTime = timezone.now()

    pollResults = calculateResults(activePoll)
    (activePoll.abstainVotes, activePoll.yesVotes, activePoll.noVotes) = pollResults

    if activePoll.roll_call:
        activePoll.outcome = 0
    elif not activePoll.supermajority:
        # Ordinary majority
        if activePoll.yesVotes > activePoll.noVotes:
            activePoll.outcome = 1
        elif activePoll.yesVotes < activePoll.noVotes:
            activePoll.outcome = 2
        else:
            activePoll.outcome = 3
    else:
        # 2/3 supermajority
        if activePoll.yesVotes >= 2*activePoll.noVotes:
            activePoll.outcome = 1
        else:
            activePoll.outcome = 2
        # NB: A casting vote is not exercisable on a supermajority - Renton 2005, para 8.16

    activePoll.active = False
    activePoll.save()
    
    return redirect(f'/poll/{activePoll.id}/')

def pollInfo(request, pollId):
    try:
        poll = Poll.objects.filter(id = pollId)[0]
    except:
        raise Http404()

    allVotes = Vote.objects.filter(poll=poll).select_related('voter__institution', 'proxy__holder__institution')
    pollResults = calculateResults(poll)
    superadmin = True if request.user.is_authenticated and request.user.delegate.is_site_admin else False

    yetToVote = []
    if poll.repsOnly:
        allInstitutions = Institution.objects.exclude(name="N/A")
        for institution in allInstitutions:
            if len([i for i in allVotes if i.voter.institution == institution]) == 0:
                yetToVote.append(institution)

    return render(request, 'councilApp/pollInfo.html', {'poll':poll, 'superadmin':superadmin, 'allVotes':allVotes, 'pollResults':pollResults, 
        'sumResults':sum(pollResults[1:3]), 'yetToVote':yetToVote, 'active_tab':'poll'})

@login_required
@ensure_csrf_cookie
def voteOnPoll(request, pollId):
    try:
        activePoll = Poll.objects.filter(id = pollId, active=True)[0]
    except:
        raise Http404()

    activeVoteHTMLIds = []

    delegate = request.user.delegate
    delegateHasProxy = Proxy.objects.filter(voter=delegate, active=True)
    delegateProxy = delegateHasProxy[0] if delegateHasProxy else None
    delegateHasVote = Vote.objects.filter(voter=delegate, poll=activePoll)
    delegateVote = delegateHasVote[0] if delegateHasVote else None
    delegateInfo = {'delegate':delegate, 'delegateProxy':delegateProxy, 'delegateVote':delegateVote}
    if delegateVote:
        activeVoteHTMLIds.append(f"ownRadio_{delegateVote.vote}")

    proxies = Proxy.objects.filter(holder=delegate, active=True)

    proxiesInfo = []
    for proxyObj in proxies:
        proxyHasVote = Vote.objects.filter(proxy=proxyObj,poll=activePoll)
        proxyVote = proxyHasVote[0] if proxyHasVote else None
        if proxyVote:
            activeVoteHTMLIds.append(f"proxyRadio_{proxyVote.vote}_{proxyObj.id}")
        proxiesInfo.append({'proxyObj':proxyObj, 'proxyVote':proxyVote})

    HTMLIdsJSON = json.dumps(activeVoteHTMLIds, cls=DjangoJSONEncoder)

    return render(request, 'councilApp/vote.html', {'activePoll':activePoll, 'delegateInfo':delegateInfo, 'proxiesInfo':proxiesInfo,
        'active_tab':'vote'})

@login_required
@require_GET
def ajaxGetCastVotes(request):
    try:
        pollId = request.GET.get('pollId', None)
        activePoll = Poll.objects.filter(id = pollId, active=True)[0]
        delegate = request.user.delegate
    except:
        return JsonResponse({'raise404':True})

    activeVoteHTMLIds = []

    delegateHasProxy = Proxy.objects.filter(voter=delegate, active=True)
    delegateProxy = delegateHasProxy[0] if delegateHasProxy else None
    delegateHasVote = Vote.objects.filter(voter=delegate, poll=activePoll)
    delegateVote = delegateHasVote[0] if delegateHasVote else None
    if delegateVote:
        activeVoteHTMLIds.append(f"ownRadio_{delegateVote.vote}")

    proxies = Proxy.objects.filter(holder=delegate, active=True)
    for proxyObj in proxies:
        proxyHasVote = Vote.objects.filter(voter=proxyObj.voter, poll=activePoll)
        proxyVote = proxyHasVote[0] if proxyHasVote else None
        if proxyVote:
            activeVoteHTMLIds.append(f"proxyRadio_{proxyVote.vote}_{proxyObj.id}")

    data = {'raise404':False, 'activeVoteHTMLIds':activeVoteHTMLIds}
    return JsonResponse(data)

@login_required
@require_POST
def ajaxSubmitVotes(request):
    try:
        pollId = request.POST.get('pollId', None)
        activePoll = Poll.objects.filter(id = pollId, active=True)[0]
        delegate = request.user.delegate
        checkedIds = request.POST.getlist('checkedIds[]', None)
    except:
        return JsonResponse({'raise404':True})

    for HTMLId in checkedIds:
        splitId = HTMLId.split('_')
        if 'own' in splitId[0]:
            existingVotes = Vote.objects.filter(voter=delegate, poll=activePoll)
            thisVote = existingVotes[0] if existingVotes else Vote()
            thisVote.voter = delegate
            thisVote.proxy = None
            thisVote.voteWeight = delegate.institution.votesWeight if activePoll.weighted else 1
        elif 'proxy' in splitId[0]:
            proxyId = splitId[2]
            proxyObj = Proxy.objects.get(id=proxyId, active=True)
            existingVotes = Vote.objects.filter(voter=proxyObj.voter, poll=activePoll)
            thisVote = existingVotes[0] if existingVotes else Vote()
            thisVote.voter = proxyObj.voter
            thisVote.proxy = proxyObj
            thisVote.voteWeight = proxyObj.voter.institution.votesWeight if activePoll.weighted else 1
        else: 
            return JsonResponse({'raise404':True})

        thisVote.poll = activePoll
        thisVote.vote = int(splitId[1])
        thisVote.voteTime = timezone.now()
        thisVote.save()

    return JsonResponse({'raise404':False})

def agenda(request):
    delegate = current_delegate(request)
    can_edit = delegate is not None and delegate.is_site_admin

    if request.method == 'POST':
        if not can_edit:
            raise Http404()
        action = request.POST.get('action')
        if action == 'save_agenda':
            day_keys = request.POST.getlist('day_key')
            day_ids = request.POST.getlist('day_id')
            day_titles = request.POST.getlist('day_title')
            day_dates = request.POST.getlist('day_date')
            day_orders = request.POST.getlist('day_order')
            item_keys = request.POST.getlist('item_key')
            item_day_keys = request.POST.getlist('item_day_key')
            item_ids = request.POST.getlist('item_id')
            item_times = request.POST.getlist('item_time')
            item_titles = request.POST.getlist('item_title')
            item_colors = request.POST.getlist('item_color')
            item_orders = request.POST.getlist('item_order')
            item_badges = request.POST.getlist('item_badge')
            item_categories = request.POST.getlist('item_category')
            item_links = request.POST.getlist('item_links')
            item_contents = request.POST.getlist('item_content')

            def list_value(values, index, default=''):
                return values[index] if index < len(values) else default

            def clean_int(value, default=0):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return default

            saved_day_ids = []
            saved_item_ids = []
            day_id_map = {}
            item_id_map = {}
            day_by_key = {}

            with transaction.atomic():
                for index, day_key in enumerate(day_keys):
                    day_id = list_value(day_ids, index).strip()
                    if day_id:
                        day = AgendaDay.objects.get(id=day_id)
                    else:
                        day = AgendaDay()
                    day.title = list_value(day_titles, index).strip() or 'New Day'
                    day.date = list_value(day_dates, index).strip()
                    day.order = clean_int(list_value(day_orders, index))
                    day.save()
                    saved_day_ids.append(day.id)
                    day_by_key[day_key] = day
                    day_id_map[day_key] = day.id

                AgendaDay.objects.exclude(id__in=saved_day_ids).delete()

                for index, item_key in enumerate(item_keys):
                    day = day_by_key.get(list_value(item_day_keys, index))
                    if day is None:
                        continue
                    title = list_value(item_titles, index).strip()
                    time = list_value(item_times, index).strip()
                    content = list_value(item_contents, index).strip()
                    links = list_value(item_links, index).strip()
                    badge = list_value(item_badges, index).strip()
                    category = list_value(item_categories, index).strip()
                    if not any([title, time, content, links, badge, category]):
                        continue
                    item_id = list_value(item_ids, index).strip()
                    if item_id:
                        item = AgendaItem.objects.get(id=item_id)
                    else:
                        item = AgendaItem(day=day)
                    item.day = day
                    item.time = time
                    item.title = title or 'New Item'
                    item.badge = badge
                    item.color = list_value(item_colors, index).strip() or '#0d6efd'
                    item.category = category
                    item.content = content
                    item.links = links
                    item.order = clean_int(list_value(item_orders, index))
                    item.save()
                    saved_item_ids.append(item.id)
                    item_id_map[item_key] = item.id

                AgendaItem.objects.filter(day_id__in=saved_day_ids).exclude(id__in=saved_item_ids).delete()

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'day_ids': day_id_map, 'item_ids': item_id_map})
        return redirect('/agenda/?edit=1')

    days = AgendaDay.objects.prefetch_related('items').all()
    return render(request, 'councilApp/councilInfo/agenda.html', {
        'active_tab': 'agenda',
        'days': days,
        'can_edit_agenda': can_edit,
        'show_day_tabs': days.count() > 1,
        'edit_agenda': request.GET.get('edit') == '1',
    })

def loginCustom(request):
    if request.user.is_authenticated:
        return redirect('/')

    if request.method == 'POST':
        loginForm = LoginForm(request.POST)
        if loginForm.is_valid():
            username = loginForm.cleaned_data.get('username').lower()
            password = loginForm.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            
            if user == None:
                loginForm = LoginForm()
                return render(request, 'councilApp/authTemplates/login.html', {'loginForm':loginForm, 'wrong':True, 'active_tab':'login'})
            else:
                login(request, user)
                try:
                    return redirect(request.GET['next'])
                except:
                    return redirect('/')
    else:
        loginForm = LoginForm()

    return render(request, 'councilApp/authTemplates/login.html', {'loginForm':loginForm, 'wrong':False, 'active_tab':'login'})

def logoutCustom(request):
    logout(request)
    return redirect('/')

def passwordResetLinkRequest(request):
    logout(request)
    if request.method == 'POST':
        emailForm = PasswordChangeEmail(request.POST)
        if emailForm.is_valid():
            email = emailForm.cleaned_data.get('email').lower()

            userList = User.objects.filter(email=email)

            if len(userList) == 0:
                return render(request, 'councilApp/authTemplates/requestChange.html', {'emailForm':emailForm, 'done':True})
            
            user = userList[0]

            for oldToken in ResetToken.objects.filter(user=user):
                oldToken.active = False
                oldToken.save()

            token = generateToken()
            while len(ResetToken.objects.filter(token=token)) > 0:
                token = generateToken()
            ResetToken.objects.create(token = token, user = user, active=True)

            try:
                resetLink = f'{settings.WEB_DOMAIN}/password_reset/{token}'
                subject = 'Council Webapp Password Change Request'
                html_message = render_to_string('councilApp/authTemplates/passwordEmail.html', {
                    'domain':settings.WEB_DOMAIN,
                    'resetLink':resetLink,
                    'site_name':settings.PYPLENARY_SITE_NAME,
                    'support_email':settings.PYPLENARY_SUPPORT_EMAIL,
                    'admin_name':settings.PYPLENARY_ADMIN_NAME,
                })
                plain_message = strip_tags(html_message)
                email_from = settings.DEFAULT_FROM_EMAIL

                send_mail(subject, plain_message, email_from, [email], html_message=html_message)

                return render(request, 'councilApp/authTemplates/requestChange.html', {'emailForm':emailForm, 'done':True})

            except Exception:
                logger.exception("Failed to send password reset email to %s", email)
                return render(request, 'councilApp/authTemplates/requestChange.html', {'emailForm':emailForm, 'done':True})
    else:
        emailForm = PasswordChangeEmail()
    
    return render(request, 'councilApp/authTemplates/requestChange.html', {'emailForm':emailForm, 'done':False})


def passwordReset(request, token):
    logout(request)
    try:
        tokenObj = ResetToken.objects.get(token=token)
        user = tokenObj.user
        if not tokenObj.active:
            return render(request, 'councilApp/authTemplates/passwordReset.html', {'linkExpired':True, 'done':False})
    except:
        return render(request, 'councilApp/authTemplates/passwordReset.html', {'linkExpired':True, 'done':False})

    if request.method == 'POST':
        changeForm = SetPasswordForm(user, request.POST)
        if changeForm.is_valid():
            changeForm.save()
            tokenObj.active = False
            tokenObj.save()
            return render(request, 'councilApp/authTemplates/passwordReset.html', {'linkExpired':False, 'done':True})
    else:
        changeForm = SetPasswordForm(user)

    return render(request, 'councilApp/authTemplates/passwordReset.html', {'changeForm':changeForm, 'linkExpired':False, 'done':False, 'user':user})

def regoRequest(request):
    regoOpen = settings.REGO_OPEN

    if not regoOpen:
        return render(request, 'councilApp/authTemplates/noRego.html', {'active_tab':'registration'})
    logout(request)
    
    if request.method == 'POST':
        regoForm = RegoForm(request.POST)

        if regoForm.is_valid():

            [email, name, institution, account_role, role, pronouns, firstTime] = [regoForm.cleaned_data.get('email').lower(),
                regoForm.cleaned_data.get('name'),
                regoForm.cleaned_data.get('institution'),
                regoForm.cleaned_data.get('account_role'),
                regoForm.cleaned_data.get('role'),
                regoForm.cleaned_data.get('pronouns'),
                regoForm.cleaned_data.get('firstTime'),]

            role = role if role else 'Delegate'

            if User.objects.filter(username=email).exists() or Delegate.objects.filter(email=email).exists():
                return render(request, 'councilApp/authTemplates/rego.html', {'regoForm':None, 'email':None, 'done':True, 'error':1, 'active_tab':'registration'})

            for oldToken in PendingRego.objects.filter(email=email):
                oldToken.active = False
                oldToken.save()

            token = generateToken()
            while len(PendingRego.objects.filter(token=token)) > 0:
                token = generateToken()
            PendingRego.objects.create(token=token, email=email, name=name, institution=institution, account_role=account_role, role=role, pronouns=pronouns, firstTime=firstTime)

            try:
                activateLink = f'{settings.WEB_DOMAIN}/activate/{token}'
                subject = 'Council Webapp Acccount Activation'
                html_message = render_to_string('councilApp/authTemplates/activationEmail.html', {
                    'activateLink':activateLink,
                    'name':name,
                    'site_name':settings.PYPLENARY_SITE_NAME,
                    'support_email':settings.PYPLENARY_SUPPORT_EMAIL,
                    'admin_name':settings.PYPLENARY_ADMIN_NAME,
                })
                plain_message = strip_tags(html_message)
                email_from = settings.DEFAULT_FROM_EMAIL

                send_mail(subject, plain_message, email_from, [email], html_message=html_message)

                return render(request, 'councilApp/authTemplates/rego.html', {'regoForm':None, 'email':email, 'done':True, 'error':0, 'active_tab':'registration'})

            except Exception:
                logger.exception("Failed to send registration activation email to %s", email)
                return render(request, 'councilApp/authTemplates/rego.html', {'regoForm':None, 'email':None, 'done':True, 'error':2, 'active_tab':'registration'})
    else:
        regoForm = RegoForm()
    
    return render(request, 'councilApp/authTemplates/rego.html', {'regoForm':regoForm, 'email':None, 'done':False, 'error':0, 'active_tab':'registration'})

def regoSetPassword(request, token):
    logout(request)
    try:
        tokenObj = PendingRego.objects.get(token=token)
        if not tokenObj.active:
            return render(request, 'councilApp/authTemplates/regoPassword.html', {'error':2, 'done':False})
    except:
        return render(request, 'councilApp/authTemplates/regoPassword.html', {'error':1, 'done':False})

    existing_delegate = Delegate.objects.filter(email=tokenObj.email).first()
    if existing_delegate:
        tokenObj.active = False
        tokenObj.save()
        return render(request, 'councilApp/authTemplates/regoPassword.html', {'error':3, 'done':False})

    user, _ = User.objects.get_or_create(
        username=tokenObj.email,
        defaults={'password': settings.USER_TEMP_PASSWORD, 'email': tokenObj.email},
    )
    if hasattr(user, 'delegate'):
        tokenObj.active = False
        tokenObj.save()
        return render(request, 'councilApp/authTemplates/regoPassword.html', {'error':3, 'done':False})

    if request.method == 'POST':
        pwdForm = SetPasswordForm(user, request.POST)
        if pwdForm.is_valid():
            try:
                with transaction.atomic():
                    pwdForm.save()
                    Delegate.objects.create(
                        authClone=user,
                        name=tokenObj.name,
                        email=tokenObj.email,
                        institution=tokenObj.institution,
                        account_role=tokenObj.account_role,
                        role=tokenObj.role,
                        speakerNum=max([0]+[i.speakerNum for i in Delegate.objects.all()])+1,
                        pronouns=tokenObj.pronouns,
                        first_time=tokenObj.firstTime)

                    tokenObj.active = False
                    tokenObj.save()
            except IntegrityError:
                logger.exception("Duplicate registration activation attempted for %s", tokenObj.email)
                tokenObj.active = False
                tokenObj.save()
                return render(request, 'councilApp/authTemplates/regoPassword.html', {'error':3, 'done':False})

            return render(request, 'councilApp/authTemplates/regoPassword.html', {'error':0,  'done':True})
    else:
        pwdForm = SetPasswordForm(user)

    return render(request, 'councilApp/authTemplates/regoPassword.html', {'pwdForm':pwdForm, 'email':tokenObj.email, 'error':0, 'done':False})

@login_required
def profile(request):
    user = request.user
    delegate = getattr(request.user, 'delegate', None)
    if delegate is None:
        return render(request, 'councilApp/authTemplates/noDelegate.html', {'active_tab':'profile'})

    done = False
    emailChanged = False
    admin_request_error = False
    admin_request_done = False

    changeDetailForm = ProfileForm({
        'name': delegate.name,
        'email': delegate.email,
        'institution': delegate.institution,
        'role': delegate.role,
        'pronouns': delegate.pronouns,
        'firstTime': delegate.first_time})

    if request.method == 'POST':
        if request.POST.get('action') == 'request_admin':
            if delegate.is_site_admin or hasattr(delegate, 'admin_access_request'):
                admin_request_done = True
            elif request.POST.get('admin_code') != 'adminaccesspls':
                admin_request_error = True
            else:
                body = (
                    f'{delegate.name} is requesting admin access.\n\n'
                    f'Email: {delegate.email}\n'
                    f'Access role: {delegate.get_account_role_display()}\n'
                    f'Position: {delegate.role}\n'
                    f'Institution: {delegate.institution}\n'
                    f'Pronouns: {delegate.pronouns or "-"}\n'
                    f'First time attendee: {delegate.first_time}\n'
                )
                try:
                    send_mail(
                        'PyPlenary admin access request',
                        body,
                        settings.DEFAULT_FROM_EMAIL,
                        ['amsaassistant@gmail.com'],
                        fail_silently=False,
                    )
                    AdminAccessRequest.objects.create(delegate=delegate)
                    admin_request_done = True
                except Exception:
                    logger.exception("Failed to send admin access request email for %s", delegate.email)
                    admin_request_error = True
        else:
            changeDetailForm = ProfileForm(request.POST)

            if changeDetailForm.is_valid():
                email = changeDetailForm.cleaned_data.get('email').lower()

                if email != user.username:
                    if User.objects.filter(username=email):
                        return render(request, 'councilApp/profile.html', {'changeDetailForm':changeDetailForm, 'error':1, 'active_tab':'profile'})
                    [delegate.email, user.username, user.email] = [email, email, email]
                    emailChanged = True

                [delegate.email, delegate.name, delegate.institution, delegate.role, delegate.pronouns, delegate.first_time] = [
                    email,
                    changeDetailForm.cleaned_data.get('name'),
                    changeDetailForm.cleaned_data.get('institution'),
                    changeDetailForm.cleaned_data.get('role'),
                    changeDetailForm.cleaned_data.get('pronouns'),
                    changeDetailForm.cleaned_data.get('firstTime'),]

                delegate.role = delegate.role if delegate.role else 'Delegate'

                delegate.save()
                user.save()

                done = True

    return render(request, 'councilApp/profile.html', {
        'changeDetailForm': changeDetailForm,
        'emailChanged': emailChanged,
        'done': done,
        'error': 0,
        'active_tab': 'profile',
        'admin_request_error': admin_request_error,
        'admin_request_done': admin_request_done,
        'admin_request_exists': hasattr(delegate, 'admin_access_request'),
    })

@login_required
def passwordResetLoggedIn(request):
    user = request.user
    if request.method == 'POST':
        changeForm = SetPasswordForm(user, request.POST)
        if changeForm.is_valid():
            changeForm.save()
            return render(request, 'councilApp/authTemplates/passwordResetLoggedIn.html', {'done':True})
    else:
        changeForm = SetPasswordForm(user)

    return render(request, 'councilApp/authTemplates/passwordResetLoggedIn.html', {'changeForm':changeForm, 'done':False, 'user':user})

def loaderio_token(request):
    return HttpResponse('loaderio-' + settings.LOADERIO_TOKEN, content_type='text/plain')

@login_required
@ensure_csrf_cookie
def appAdmin(request):
    if request.user.delegate.is_site_admin:
        return render(request, 'councilApp/adminToolTemplates/app_admin.html', {'active_tab':'app_admin'})
    else:
        raise Http404()

@login_required
def appAdminDownloadData(request):
    if not request.user.delegate.is_site_admin:
        raise Http404()
    return generateSpeakerListCSV(request)

@login_required
def appAdminAddUsersTemplate(request):
    if not request.user.delegate.is_site_admin:
        raise Http404()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="add_user_template.csv"'

    writer = csv.writer(response)
    writer.writerow(['Name', 'Email', 'Account role', 'Role', 'Institution', 'Pronouns', 'First time'])

    return response

@login_required
def appAdminAddUsersValidInstitutions(request):
    if not request.user.delegate.is_site_admin:
        raise Http404()
    institutions = sorted(Institution.objects.all(), key = lambda x:x.name)
    return render(request, 'councilApp/adminToolTemplates/valid_institutions.html', {'active_tab':'app_admin', 'institutions':institutions})

@login_required
def appAdminAddUsersValidInstitutionsDownload(request):
    if not request.user.delegate.is_site_admin:
        raise Http404()
    institutions = sorted(Institution.objects.all(), key = lambda x:x.name)
    response = HttpResponse('\n'.join([f'{i.name}\n{i.shortName}' for i in institutions]), content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename="valid_institutions.txt"'
    return response

@login_required
@ensure_csrf_cookie
def appAdminAddUsers(request):
    return render(request, 'councilApp/adminToolTemplates/add_users.html', {'active_tab':'app_admin'})

@login_required
@require_POST
def ajaxAddOneUser(request):
    if not request.user.delegate.is_site_admin:
        raise Http404()
    try:
        userInfo = request.POST.get('userInfo')
        userInfo = json.loads(userInfo)
        reissue = True if request.POST.get('reissue') == 'true' else False
        result = addUserFromJSON(userInfo, reissue)

        return JsonResponse({'result':result})
    except:
        result = {'success': False, 'errorCode': 'Unknown Error', 'errorMsg': '', 'account': {}}
        return JsonResponse({'result':result})

@login_required
def appAdminAssignReps(request):
    if not request.user.delegate.is_site_admin:
        raise Http404()
    institutions = sorted(Institution.objects.all(), key = lambda x:x.name)
    toPass = []
    for inst in institutions:
        if inst.name in ('N/A', 'Other'):
            continue
        rep = Delegate.objects.filter(institution = inst, rep = True)
        if rep:
            rep = rep[0]
        else:
            rep = '-'
        toPass.append({'inst':inst, 'rep':rep})
    return render(request, 'councilApp/adminToolTemplates/view_reps.html', {'active_tab':'app_admin', 'repsList': toPass})

@login_required
@ensure_csrf_cookie
def appAdminAssignRepById(request, instId):
    if not request.user.delegate.is_site_admin:
        raise Http404()
    try:
        inst = Institution.objects.get(id=instId)
    except:
        raise Http404()
    if inst.name in ('N/A', 'Other'):
        raise Http404()
    rep = Delegate.objects.filter(institution = inst, rep = True)
    if rep:
        rep = rep[0]
    else:
        rep = None

    validDelegates = Delegate.objects.filter(institution=inst).exclude(speakerNum=0).order_by('speakerNum')
    return render(request, 'councilApp/adminToolTemplates/assign_rep.html', {'active_tab':'app_admin', 'validDelegates': validDelegates, 'inst':inst, 'curRep':rep})

@login_required
@require_POST
def ajaxAssignRep(request):
    if not request.user.delegate.is_site_admin:
        raise Http404()
    try:
        delegateId = request.POST.get('delegateId', None)
        delegate = Delegate.objects.get(id=delegateId)
    except:
        return JsonResponse({'raise404':True, 'newRep':None})
    for otherDelegate in Delegate.objects.filter(institution=delegate.institution):
        otherDelegate.rep = False
        if otherDelegate.account_role == Delegate.ROLE_REPRESENTATIVE and otherDelegate.id != delegate.id:
            otherDelegate.account_role = Delegate.ROLE_DELEGATE
        otherDelegate.save()
    delegate.rep = True
    if delegate.account_role != Delegate.ROLE_ADMIN:
        delegate.account_role = Delegate.ROLE_REPRESENTATIVE
    delegate.save()

    data = {'raise404':False, 'newRep':[delegate.name, delegate.institution.name]}
    return JsonResponse(data)

@login_required
@require_POST
def ajaxResetAndWipe(request):
    if not request.user.delegate.is_site_admin:
        raise Http404()
    try:
        confirmation = request.POST.get('confirmation')
        if not confirmation:
            return JsonResponse({'raise404':True})

        # Deleting in the order
        superadminEmail = settings.PYPLENARY_ADMIN_EMAIL

        if request.user.username != superadminEmail:
            logout(request)
        Vote.objects.all().delete()
        Proxy.objects.all().delete()
        Poll.objects.all().delete()
        AgendaDay.objects.all().delete()
        AdminAccessRequest.objects.all().delete()
        Discussion.objects.all().delete()
        Speaker.objects.all().delete()
        ResetToken.objects.all().delete()
        PendingRego.objects.all().delete()
        Delegate.objects.all().exclude(authClone__username=superadminEmail).delete()
        User.objects.all().exclude(username=superadminEmail).delete()

        return JsonResponse({'raise404':False, 'successWipe':True})
        
    except:
        return JsonResponse({'raise404':True})
