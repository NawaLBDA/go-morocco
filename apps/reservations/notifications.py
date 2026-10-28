import json
import logging
from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.template.loader import render_to_string
from apps.core.email_identity import email_identity
from django.db import transaction
from apps.core.models import BookingNotificationSettings, BookingNotification

logger = logging.getLogger(__name__)


def queue_booking_notifications(booking, event='requested'):
    brand, sender, inbox = email_identity(booking.tour.country)
    context = {'brand': brand, 'name': booking.user.get_full_name() or booking.user.username,
        'reference': str(booking.pk), 'tour': booking.tour.title,
        'country': booking.tour.region.name, 'start': booking.start_date.strftime('%d %b %Y'),
        'end': booking.end_date.strftime('%d %b %Y'), 'persons': booking.num_persons,
        'amount': f'{booking.total_price} USD', 'payment_method': booking.get_payment_method_display(),
        'email': booking.user.email, 'inbox': inbox, 'event': event}
    recipients = [('email', booking.user.email, 'traveler')] if booking.user.email else []
    config = BookingNotificationSettings.objects.filter(country=booking.tour.country).first()
    staff_emails = [inbox] + (config.email_recipients.splitlines() if config else [])
    recipients += [('email', address.strip(), 'staff') for address in dict.fromkeys(staff_emails) if address.strip()]
    if config and event == 'requested':
        recipients += [('whatsapp', address.strip(), 'staff') for address in dict.fromkeys(config.whatsapp_recipients.splitlines()) if address.strip()]
    for channel, recipient, audience in recipients:
        notification, created = BookingNotification.objects.get_or_create(
            reservation=booking, channel=channel, recipient=recipient, event=event, audience=audience,
            defaults={'context': context})
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
            brand, sender, inbox = email_identity(booking.tour.country)
            context = notice.context or {'brand': brand, 'name': name, 'reference': str(booking.pk),
                'tour': booking.tour.title, 'start': str(booking.start_date), 'end': str(booking.end_date),
                'persons': booking.num_persons, 'amount': f'{booking.total_price} USD',
                'payment_method': booking.get_payment_method_display(), 'email': booking.user.email}
            context.update(brand=brand, inbox=inbox, event=notice.event, audience=notice.audience)
            title, introduction, next_step = {
                'requested': ('Booking request received', 'Thank you for choosing us. We have received your booking request and our team is reviewing it.', 'Your booking is pending approval. We will email you as soon as our team confirms it. Please wait for approval before arranging payment.'),
                'approved': ('Your journey is confirmed', 'Our team has approved your booking. We look forward to welcoming you on your journey.', 'If your balance is unpaid, please contact our team to arrange your selected payment method. Approval does not mean payment has been received.'),
                'paid': ('Payment received', 'Thank you. Our team has recorded your booking payment as received.', 'Keep this confirmation with your travel details. Contact us if you have any questions about your journey.'),
            }[notice.event]
            if notice.audience == 'staff':
                introduction = f'Booking #{booking.pk}: {title.lower()}. Review the reservation in your administration dashboard.'
                next_step = 'This is an operational notification for your team.'
            context.update(title=title, introduction=introduction, next_step=next_step)
            body = render_to_string('emails/booking_event.txt', context)
            message = EmailMultiAlternatives(f'{brand} | {title} | #{booking.pk}', body, sender,
                [notice.recipient], reply_to=[inbox] if notice.audience == 'traveler' else ([booking.user.email] if booking.user.email else [inbox]))
            message.attach_alternative(render_to_string('emails/booking_event.html', context), 'text/html')
            if not message.send(fail_silently=False):
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
