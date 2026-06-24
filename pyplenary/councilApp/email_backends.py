import logging
from base64 import urlsafe_b64encode

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class ResendEmailBackend(BaseEmailBackend):
    """Django email backend that sends mail through Resend's HTTPS API."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.api_key = settings.RESEND_API_KEY
        self.api_url = settings.RESEND_API_URL
        self.timeout = settings.RESEND_TIMEOUT

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            if self.fail_silently:
                return 0
            raise ValueError("RESEND_API_KEY must be set to use ResendEmailBackend.")

        sent_count = 0
        for message in email_messages:
            if self._send(message):
                sent_count += 1
        return sent_count

    def _send(self, message):
        html_body = None
        for content, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                html_body = content
                break

        payload = {
            "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
            "to": list(message.to),
            "subject": message.subject,
            "text": message.body,
        }
        if html_body:
            payload["html"] = html_body

        if message.cc:
            payload["cc"] = list(message.cc)
        if message.bcc:
            payload["bcc"] = list(message.bcc)
        if message.reply_to:
            payload["reply_to"] = list(message.reply_to)

        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                logger.error(
                    "Resend API rejected email with status %s: %s",
                    response.status_code,
                    response.text,
                )
            response.raise_for_status()
            return True
        except requests.RequestException:
            logger.exception("Failed to send email through Resend API")
            if self.fail_silently:
                return False
            raise


class GmailAPIEmailBackend(BaseEmailBackend):
    """Django email backend that sends mail through the Gmail HTTPS API."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.client_id = settings.GMAIL_CLIENT_ID
        self.client_secret = settings.GMAIL_CLIENT_SECRET
        self.refresh_token = settings.GMAIL_REFRESH_TOKEN
        self.token_url = settings.GMAIL_TOKEN_URL
        self.send_url = settings.GMAIL_SEND_URL
        self.timeout = settings.GMAIL_API_TIMEOUT
        self._access_token = None

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        self._validate_settings()

        sent_count = 0
        for message in email_messages:
            if self._send(message):
                sent_count += 1
        return sent_count

    def _validate_settings(self):
        missing = [
            name
            for name, value in (
                ("GMAIL_CLIENT_ID", self.client_id),
                ("GMAIL_CLIENT_SECRET", self.client_secret),
                ("GMAIL_REFRESH_TOKEN", self.refresh_token),
            )
            if not value
        ]
        if missing:
            if self.fail_silently:
                return
            raise ValueError(f"Missing Gmail API email settings: {', '.join(missing)}")

    def _get_access_token(self):
        if self._access_token:
            return self._access_token

        response = requests.post(
            self.token_url,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            logger.error(
                "Gmail token endpoint rejected refresh with status %s: %s",
                response.status_code,
                response.text,
            )
        response.raise_for_status()
        self._access_token = response.json()["access_token"]
        return self._access_token

    def _send(self, message):
        try:
            access_token = self._get_access_token()
            raw_message = urlsafe_b64encode(message.message().as_bytes()).decode("ascii")

            response = requests.post(
                self.send_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"raw": raw_message},
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                logger.error(
                    "Gmail API rejected email with status %s: %s",
                    response.status_code,
                    response.text,
                )
            response.raise_for_status()
            return True
        except requests.RequestException:
            logger.exception("Failed to send email through Gmail API")
            if self.fail_silently:
                return False
            raise
