from django import forms
from .models import *
from .utils import *

class LoginForm(forms.Form):
    username = forms.CharField(label='Email', help_text='Please enter the email you signed up with.')
    password = forms.CharField(widget=forms.PasswordInput, label='Password', help_text='This is case-sensitive.')

class PasswordChangeEmail(forms.Form):
    email = forms.EmailField(max_length=254, label="", widget=forms.TextInput(attrs={'placeholder': 'Email'}))

class StartPollForm(forms.Form):
    title = forms.CharField(max_length=1000, label="Poll title", widget=forms.TextInput(attrs={'placeholder': 'Motion to be put to a vote'}))
    anonymous = forms.BooleanField(required = False, label="Anonymous voting", 
        widget=forms.CheckboxInput(attrs={'class': 'centred-checkbox'}))
    roll_call = forms.BooleanField(required = False, label="Roll call",
        widget=forms.CheckboxInput(attrs={'class': 'centred-checkbox', 'id':'check_roll_call'}))
    repsOnly = forms.BooleanField(required = False, label="Reps only", 
        widget=forms.CheckboxInput(attrs={'class': 'centred-checkbox', 'id':'check_reps'}), initial=True)
    weighted = forms.BooleanField(required = False, label="Institution-weighted vote", 
        widget=forms.CheckboxInput(attrs={'class': 'centred-checkbox', 'id':'check_weighted'}))
    majority = forms.ChoiceField(required = True, label="Majority", choices=[('simple','Simple majority (1/2 of votes)'),('super','Supermajority (2/3 of votes)')],
        widget=forms.RadioSelect(), initial='simple')

class RegoForm(forms.Form):
    name = forms.CharField(max_length=100, label='Full name', help_text='Please set your full name as you want it displayed.', 
        widget=forms.TextInput(attrs={'placeholder': 'Full name'}), required=True)
    email = forms.EmailField(max_length=254, label="Email", help_text='Please enter your email address.', 
        widget=forms.TextInput(attrs={'placeholder': 'Email'}), required=True)
    institution = forms.ModelChoiceField(label="Institution", help_text='Please select your institution.', 
        queryset=Institution.objects.all(), required=True)
    account_role = forms.ChoiceField(
        label='Access role',
        choices=Delegate.ACCOUNT_ROLE_CHOICES,
        initial=Delegate.ROLE_VIEWER,
        help_text='Viewers cannot speak. Delegates can speak in informal discussions. Representatives can speak in formal and informal discussions. Moderators can create and run discussions.',
        required=True,
    )
    role = forms.CharField(max_length=200, label='Role/Position(s) (Optional)', help_text='Please enter your position/title within AMSA or MedSoc, if applicable.', 
        widget=forms.TextInput(attrs={'placeholder': 'Role/Position(s)'}), required=False)
    pronouns = forms.CharField(max_length=100, label='Pronouns (Optional)', help_text='Please enter your pronouns if you wish. This will be publicly displayed.', 
        widget=forms.TextInput(attrs={'placeholder': 'Pronouns'}), required=False)
    firstTime = forms.BooleanField(required = False, label='First-time Council attendee', help_text='Is this your first time at Council?')


class ProfileForm(forms.Form):
    name = forms.CharField(max_length=100, label='Full name', help_text='Please set your full name as you want it displayed.',
        widget=forms.TextInput(attrs={'placeholder': 'Full name'}), required=True)
    email = forms.EmailField(max_length=254, label="Email", help_text='Please enter your email address.',
        widget=forms.TextInput(attrs={'placeholder': 'Email'}), required=True)
    institution = forms.ModelChoiceField(label="Institution", help_text='Please select your institution.',
        queryset=Institution.objects.all(), required=True)
    role = forms.CharField(max_length=200, label='Role/Position(s) (Optional)', help_text='Please enter your position/title within AMSA or MedSoc, if applicable.',
        widget=forms.TextInput(attrs={'placeholder': 'Role/Position(s)'}), required=False)
    pronouns = forms.CharField(max_length=100, label='Pronouns (Optional)', help_text='Please enter your pronouns if you wish. This will be publicly displayed.',
        widget=forms.TextInput(attrs={'placeholder': 'Pronouns'}), required=False)
    firstTime = forms.BooleanField(required = False, label='First-time Council attendee', help_text='Is this your first time at Council?')


class DiscussionCreateForm(forms.Form):
    title = forms.CharField(
        max_length=200,
        label='Discussion title',
        widget=forms.TextInput(attrs={'placeholder': 'Discussion topic'}),
        required=True,
    )
    discussion_type = forms.ChoiceField(
        label='Discussion type',
        choices=[('informal', 'Informal - anyone can speak'), ('formal', 'Formal - representatives only can speak')],
        initial='informal',
    )
    default_speaker_seconds = forms.IntegerField(
        label='Default speaker time (seconds)',
        min_value=15,
        max_value=900,
        initial=60,
    )
