import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class ResendEmailBackend(BaseEmailBackend):
    """Send through HTTPS for hosts where outbound SMTP is blocked."""
    def send_messages(self, email_messages):
        count = 0
        for message in email_messages:
            try:
                if not settings.RESEND_API_KEY:
                    raise RuntimeError('RESEND_API_KEY is not configured')
                payload = {'from': message.from_email, 'to': message.to,
                           'subject': message.subject, 'text': message.body}
                if message.reply_to:
                    payload['reply_to'] = message.reply_to
                if message.cc:
                    payload['cc'] = message.cc
                if message.bcc:
                    payload['bcc'] = message.bcc
                response = requests.post('https://api.resend.com/emails',
                    headers={'Authorization': f'Bearer {settings.RESEND_API_KEY}'},
                    json=payload, timeout=(5, 15))
                if response.status_code >= 400:
                    raise RuntimeError(f'Email provider rejected request (HTTP {response.status_code})')
                count += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return count
