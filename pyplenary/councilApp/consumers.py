import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer

from .models import *

class SpeakerListConsumer(WebsocketConsumer):
    def connect(self):
        if not self.scope["user"].is_authenticated or not hasattr(self.scope["user"], "delegate"):
            self.close()
            return

        async_to_sync(self.channel_layer.group_add)('discussions', self.channel_name)
        self.accept()
        
        delegate = self.scope['user'].delegate
        discussions = Discussion.discussions_for_ws(delegate)
        self.send(text_data=json.dumps({'type': 'init', 'delegate_id': delegate.id, 'discussions': discussions}))

    def disconnect(self, code):
        pass

    def receive(self, text_data):
        pass

    def discussions_updated(self, data):
        delegate = self.scope['user'].delegate
        self.send(text_data=json.dumps({
            'type': 'discussions_updated',
            'delegate_id': delegate.id,
            'discussions': Discussion.discussions_for_ws(delegate),
        }))
