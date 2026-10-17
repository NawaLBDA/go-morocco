import logging

from django.conf import settings
from django.core.mail import EmailMessage

from .models import ContactEmailSettings

logger = logging.getLogger(__name__)


def notify_contact(enquiry):
    """Keep the saved enquiry even if the notification cannot be delivered."""
    recipient = ContactEmailSettings.objects.filter(country=enquiry.country).values_list('recipient_email', flat=True).first()
    if not recipient:
        return False
    try:
        return bool(EmailMessage(
            subject=f'[{enquiry.country.title()}] New contact enquiry #{enquiry.pk}',
            body=f'Name: {enquiry.name}\nEmail: {enquiry.email}\nSubject: {enquiry.subject}\n\n{enquiry.message}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
            reply_to=[enquiry.email],
        ).send(fail_silently=False))
    except Exception:
        logger.error('Contact email delivery failed for enquiry %s; the message remains in admin.', enquiry.pk)
        return False
