from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from .models import *

import csv
from io import StringIO
import json
import logging
import secrets
import requests
import yaml
import zipfile

REQUEST_TIMEOUT = 10
logger = logging.getLogger(__name__)


def fetch_yaml_from_uri(uri, label):
    if not uri:
        raise ValueError(f"{label} URI is not configured.")
    response = requests.get(uri, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return yaml.safe_load(response.text) or {}


def readConfigYAMLFromHTML(fileURL):
    return fetch_yaml_from_uri(fileURL, "configuration")

def eligibleToVote(delegate, poll):
    if poll.repsOnly:
        if delegate is not None and delegate.rep:
            return True
        else:
            proxies = Proxy.objects.filter(holder = delegate, active=True)
            for i in proxies:
                if i.voter.rep:
                    return True
            return False
    return True

def bad_request(status, message):
    response = HttpResponse(json.dumps({'message': message}), 
        content_type='application/json')
    response.status_code = status
    return response

def calculateResults(poll):
    votesInPoll = Vote.objects.filter(poll = poll)
    yesVotes = sum([i.voteWeight for i in votesInPoll if i.vote == 1])
    noVotes = sum([i.voteWeight for i in votesInPoll if i.vote == 2])
    abstainVotes = sum([i.voteWeight for i in votesInPoll if i.vote == 0])
    return (abstainVotes, yesVotes, noVotes)

def generateToken():
    return secrets.token_urlsafe(48)

def generateSpeakerListCSV(request):
    speakersIO = StringIO()
    writer = csv.writer(speakersIO)
    writer.writerow(['Speaker #', 'Name', 'Role', 'Institution', 'Pronouns'])
    for delegate in sorted(Delegate.objects.all(), key = lambda x:x.speakerNum):
        writer.writerow([delegate.speakerNum, delegate.name, delegate.role, delegate.institution.shortName, delegate.pronouns])

    discussionsIO = StringIO()
    writer = csv.writer(discussionsIO)
    writer.writerow(['Discussion', 'Type', 'Moderator', 'Active', 'Archived', 'Default speaker seconds', 'Current speaker', 'Created at'])
    for discussion in Discussion.objects.all().select_related('moderator', 'current_speaker__delegate').order_by('created_at'):
        writer.writerow([
            discussion.title,
            discussion.discussion_type,
            discussion.moderator.name,
            discussion.active,
            discussion.archived,
            discussion.default_speaker_seconds,
            discussion.current_speaker.delegate.name if discussion.current_speaker else '',
            discussion.created_at,
        ])

    discussionSpeakersIO = StringIO()
    writer = csv.writer(discussionSpeakersIO)
    writer.writerow(['Discussion', 'Speaker', 'Institution', 'Queue index', 'Duration seconds', 'Status', 'Added at'])
    for speaker in DiscussionSpeaker.objects.all().select_related('discussion', 'delegate', 'delegate__institution').order_by('discussion_id', 'index'):
        writer.writerow([
            speaker.discussion.title,
            speaker.delegate.name,
            speaker.delegate.institution.shortName if speaker.delegate.institution else '',
            speaker.index,
            speaker.duration_seconds,
            speaker.status,
            speaker.added_at,
        ])

    discussionQuestionsIO = StringIO()
    writer = csv.writer(discussionQuestionsIO)
    writer.writerow(['Discussion', 'Question ID', 'Parent ID', 'Author', 'Text', 'Created at'])
    for question in DiscussionQuestion.objects.all().select_related('discussion', 'author').order_by('discussion_id', 'created_at'):
        writer.writerow([
            question.discussion.title,
            question.id,
            question.parent_id or '',
            question.author.name,
            question.text,
            question.created_at,
        ])

    pollsIO = StringIO()
    writer = csv.writer(pollsIO)
    writer.writerow(['Motion', 'Time concluded', 'Result', 'Votes for', 'Votes against', 'Abstentions', 'All votes for', 'All votes against', 'All abstentions'])
    resultDict = {0:'N/A',1:'Carried',2:'Lost',3:'Tied'}
    for poll in sorted(Poll.objects.all(), key = lambda x:x.endTime):
        allVotes = Vote.objects.filter(poll=poll)
        toWrite = [poll.title, poll.endTime, resultDict[poll.outcome], poll.yesVotes, poll.noVotes, poll.abstainVotes]
        toWrite.append("; ".join([f'{vote.voter.name} ({vote.voter.institution.shortName})' for vote in allVotes if vote.vote == 1]))
        toWrite.append("; ".join([f'{vote.voter.name} ({vote.voter.institution.shortName})' for vote in allVotes if vote.vote == 2]))
        toWrite.append("; ".join([f'{vote.voter.name} ({vote.voter.institution.shortName})' for vote in allVotes if vote.vote == 0]))
        writer.writerow(toWrite)

    agendaIO = StringIO()
    writer = csv.writer(agendaIO)
    writer.writerow(['Day', 'Time', 'Item'])
    for day in AgendaDay.objects.prefetch_related('items').all():
        for item in day.items.all():
            writer.writerow([day.title, item.time, item.title])

    response = HttpResponse(content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename=councilAppData.zip'

    z = zipfile.ZipFile(response,'w') 
    z.writestr("delegateSpeakerNumbers.csv", speakersIO.getvalue())
    z.writestr("activeDiscussions.csv", discussionsIO.getvalue())
    z.writestr("discussionSpeakers.csv", discussionSpeakersIO.getvalue())
    z.writestr("discussionQuestions.csv", discussionQuestionsIO.getvalue())
    z.writestr("polls.csv", pollsIO.getvalue())
    z.writestr("agenda.csv", agendaIO.getvalue())
    z.close()

    return response

def addUserFromJSON(account, forceResend = False):
    try:
        account = dict(account)
        toReturn = {'success':False, 'errorCode':'',  'errorMsg':'',
            'name':account['Name'], 'email':account['Email'], 'inst':'', 'account':account}
        print(account)

        instNameLower = [(i.name.lower(), i.id) for i in Institution.objects.all()] + [(i.shortName.lower(), i.id) for i in Institution.objects.all()]

        institution = None
        for i in instNameLower:
            if account['Institution'].lower() == i[0]:
                institution = Institution.objects.get(id=i[1])
                toReturn['inst'] = institution.shortName
                break
        if not institution:
            toReturn['errorCode'] = 'Invalid Institution'
            toReturn['errorMsg'] = f"{account['Institution']} is an invalid institution"
            return toReturn
        
        account_role = (account.get('Account role') or account.get('Access role') or Delegate.ROLE_DELEGATE).strip().lower()
        public_role_choices = [choice for choice in Delegate.ACCOUNT_ROLE_CHOICES if choice[0] != Delegate.ROLE_ADMIN]
        valid_roles = dict(public_role_choices)
        valid_roles_by_label = {label.lower(): key for key, label in public_role_choices}
        if account_role in valid_roles_by_label:
            account_role = valid_roles_by_label[account_role]
        if account_role not in valid_roles:
            toReturn['errorCode'] = 'Invalid Account Role'
            toReturn['errorMsg'] = f"{account_role} is not a valid account role"
            return toReturn

        [email, name, institution, role, pronouns, firstTime] = [''.join(account['Email'].lower().split()),
            account['Name'],
            institution,
            account['Role'] if account['Role'] else 'Delegate',
            account['Pronouns'],
            account['First time'] in ("1", 1, True, "Yes", "yes", "YES", "True", "true", "TRUE"),]
        
        if not name or not email:
            toReturn['errorCode'] = 'Missing Name Or Email'
            return toReturn

        if User.objects.filter(username=email):
            toReturn['errorCode'] = 'Account Already Created'
            return toReturn

        if not forceResend:
            if PendingRego.objects.filter(email=email, active=True):
                toReturn['errorCode'] = 'Duplicate'
                return toReturn

        for oldToken in PendingRego.objects.filter(email=email):
            oldToken.active = False
            oldToken.save()

        token = generateToken()
        while PendingRego.objects.filter(token=token):
            token = generateToken()

    except:
        toReturn['errorCode'] = 'Unknown Error'
        return toReturn
    
    try:
        activateLink = f'{settings.WEB_DOMAIN}/activate/{token}'
        subject = f'[ACTION REQUIRED] Webapp Acccount Activation, {settings.CUSTOM_CONFIGS["PYPLENARY_SITE_NAME"]}'
        html_message = render_to_string('councilApp/adminToolTemplates/emailTemplate.html', {
            'activateLink':activateLink,
            'name':name,
            'site_name':settings.PYPLENARY_SITE_NAME,
            'site_url':settings.WEB_DOMAIN.rstrip('/'),
            'support_email':settings.PYPLENARY_SUPPORT_EMAIL,
            'admin_name':settings.PYPLENARY_ADMIN_NAME,
        })
        plain_message = strip_tags(html_message)
        email_from = settings.DEFAULT_FROM_EMAIL
        send_mail(subject, plain_message, email_from, [email], html_message=html_message)
        PendingRego.objects.create(token=token, email=email, name=name, institution=institution, account_role=account_role, role=role, pronouns=pronouns, firstTime=firstTime)
        
        toReturn['success'] = True

    except Exception:
        logger.exception("Failed to send admin invitation email to %s", email)
        toReturn['errorCode'] = 'Email Error'
        toReturn['errorMsg'] = 'An error occurred when attempting to email an invitation.'
        return toReturn

    return toReturn
