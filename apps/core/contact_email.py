import logging

from django.conf import settings
from django.core.mail import EmailMessage

from .models import ContactEmailSettings

logger = logging.getLogger(__name__)


def notify_contact(enquiry):
    """Keep the saved enquiry even if the notification cannot be delivered."""
    from .email_identity import email_identity
    brand, sender, recipient = email_identity(enquiry.country)
    try:
        return bool(EmailMessage(
            subject=f'{brand} | Contact enquiry #{enquiry.pk}',
            body=f'Name: {enquiry.name}\nEmail: {enquiry.email}\nSubject: {enquiry.subject}\n\n{enquiry.message}',
            from_email=sender,
            to=[recipient],
            reply_to=[enquiry.email],
        ).send(fail_silently=False))
    except Exception:
        logger.error('Contact email delivery failed for enquiry %s; the message remains in admin.', enquiry.pk)
        return False
