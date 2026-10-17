import json
import logging
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from apps.core.models import BookingNotificationSettings, BookingNotification

logger = logging.getLogger(__name__)


def queue_booking_notifications(booking):
    config = BookingNotificationSettings.objects.filter(country=booking.tour.country).first()
    if not config:
        return
    for channel, recipients in [('email', config.email_recipients), ('whatsapp', config.whatsapp_recipients)]:
        for recipient in dict.fromkeys(x.strip() for x in recipients.splitlines() if x.strip()):
            notification, created = BookingNotification.objects.get_or_create(
                reservation=booking, channel=channel, recipient=recipient)
            if created:
                transaction.on_commit(lambda pk=notification.pk: deliver_notification(pk), robust=True)


def deliver_notification(pk):
    if not BookingNotification.objects.filter(pk=pk, status__in=['pending', 'failed']).update(status='sending', error=''):
        return
    notice = BookingNotification.objects.select_related('reservation__user__profile', 'reservation__tour').get(pk=pk)
    booking = notice.reservation
    profile = getattr(booking.user, 'profile', None)
    name = booking.user.get_full_name() or booking.user.username
    phone = profile.phone if profile else ''
    # Only operational booking details, not accessibility declarations.
    values = {'1': str(booking.pk), '2': name, '3': booking.tour.title,
              '4': f'{booking.start_date} to {booking.end_date}', '5': str(booking.num_persons),
              '6': f'{booking.total_price} USD', '7': phone or 'Not provided',
              '8': booking.user.email or 'Not provided'}
    body = (f'New booking request #{booking.pk}\nName: {name}\nPhone: {phone}\n'
            f'Email: {booking.user.email}\nTour: {booking.tour.title}\nDates: {values["4"]}\n'
            f'Persons: {booking.num_persons}\nTotal: {values["6"]}\n'
            f'Payment: {booking.get_payment_method_display()}\nStatus: {booking.get_status_display()}\n'
            'Review this request in Admin Reservations.')
    try:
        if notice.channel == 'email':
            if settings.EMAIL_BACKEND in ['django.core.mail.backends.console.EmailBackend', 'django.core.mail.backends.dummy.EmailBackend', 'django.core.mail.backends.filebased.EmailBackend']:
                raise RuntimeError('Email delivery disabled. Configure EMAIL_BACKEND and a verified sender.')
            if not EmailMessage(f'New booking request #{booking.pk}', body, settings.DEFAULT_FROM_EMAIL,
                                [notice.recipient]).send(fail_silently=False):
                raise RuntimeError('Email provider did not accept the message.')
            reference = ''
        else:
            config = BookingNotificationSettings.objects.get(country=booking.tour.country)
            if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_WHATSAPP_FROM, config.whatsapp_content_sid]):
                raise RuntimeError('Configure Twilio credentials, WhatsApp sender and approved template.')
            from twilio.rest import Client
            from twilio.http.http_client import TwilioHttpClient
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN,
                            http_client=TwilioHttpClient(timeout=15))
            message = client.messages.create(from_=settings.TWILIO_WHATSAPP_FROM,
                to=f'whatsapp:{notice.recipient}', content_sid=config.whatsapp_content_sid,
                content_variables=json.dumps(values))
            reference = message.sid
        BookingNotification.objects.filter(pk=pk).update(status='sent', provider_reference=reference, error='')
    except Exception as exc:
        # Never expose credentials or provider request bodies in admin errors.
        code = getattr(exc, 'code', None) or getattr(exc, 'status', None)
        reason = str(exc) if isinstance(exc, RuntimeError) else f'{type(exc).__name__}; provider code: {code or "unavailable"}. Check provider configuration.'
        BookingNotification.objects.filter(pk=pk).update(status='failed', error=reason[:255])
        logger.warning('Booking notification %s failed (%s).', pk, type(exc).__name__)
