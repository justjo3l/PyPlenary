from django.contrib import admin
from .models import *

# Register your models here.

admin.site.register(Institution)
admin.site.register(Delegate)
admin.site.register(Poll)
admin.site.register(Vote)
admin.site.register(Proxy)
admin.site.register(ResetToken)
admin.site.register(PendingRego)
admin.site.register(Speaker)
admin.site.register(Discussion)
admin.site.register(DiscussionParticipant)
admin.site.register(DiscussionSpeaker)
admin.site.register(DiscussionQuestion)
admin.site.register(DiscussionQuestionReaction)
admin.site.register(DiscussionEvent)
