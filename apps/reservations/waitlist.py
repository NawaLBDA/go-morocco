"""Staff decisions never displace existing bookings or charge a traveler."""
import logging
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone
from apps.core.models import WaitlistEntry, SiteSettings
from .availability import lock_guide_calendar

logger = logging.getLogger(__name__)


def send_decision_email(entry_id):
    entry = WaitlistEntry.objects.select_related('departure__tour', 'reservation').get(pk=entry_id)
    if entry.status == 'waiting' or entry.email_sent_at:
        return
    from apps.core.email_identity import email_identity
    brand, sender, inbox = email_identity(entry.departure.tour.country, purpose='booking')
    dates = f'{entry.departure.start_date:%d %b %Y} – {entry.departure.end_date:%d %b %Y}'
    decision = 'accepted' if entry.status == 'accepted' else 'declined'
    body = f'Your waiting-list request for {entry.departure.tour.title} ({dates}), {entry.num_persons} traveler(s), has been {decision}.\n\n'
    if entry.reservation_id:
        body += f'Booking reference: {entry.reservation_id}. Confirmed total: ${entry.reservation.total_price}. Our team will contact you with payment details.\n\n'
    if entry.decision_note:
        body += entry.decision_note + '\n\n'
    body += brand
    try:
        if settings.EMAIL_BACKEND in ('django.core.mail.backends.console.EmailBackend',
                'django.core.mail.backends.dummy.EmailBackend', 'django.core.mail.backends.filebased.EmailBackend'):
            raise RuntimeError('Configure a real outgoing email provider.')
        sent = EmailMessage(f'{brand} | Waiting-list request {decision}', body,
            sender, [entry.email], bcc=[inbox] if entry.email.casefold() != inbox.casefold() else [],
            reply_to=[inbox]).send(fail_silently=False)
        if not sent:
            raise RuntimeError('Email provider did not accept the message.')
        WaitlistEntry.objects.filter(pk=entry.pk).update(email_sent_at=timezone.now(), email_error='')
    except Exception as exc:
        # Do not log credentials or provider response bodies.
        WaitlistEntry.objects.filter(pk=entry.pk).update(email_error=f'{type(exc).__name__}: email not sent. Check the email provider, then retry.')
        logger.warning('Waitlist decision email %s failed (%s).', entry.pk, type(exc).__name__)


def decide_waitlist(entry_id, *, accept, staff, note=''):
    if not staff.is_active or not staff.is_staff:
        raise ValidationError('Staff access is required.')
    country = WaitlistEntry.objects.select_related('departure__tour').get(pk=entry_id).departure.tour.country
    with lock_guide_calendar(country):
        entry = WaitlistEntry.objects.select_for_update().select_related('user', 'departure__tour').get(pk=entry_id)
        if entry.status != 'waiting':
            return entry
        if accept:
            from .views import _create_pending_reservation
            departure = entry.departure
            reservation, error, _, _ = _create_pending_reservation(user=entry.user, tour=departure.tour,
                start_date=departure.start_date, end_date=departure.end_date,
                persons=entry.num_persons, payment_method='cash', full_package=False,
                include_transport=False, include_hotel=False, extra_activity_ids=[], departure_id=departure.pk)
            if error:
                raise ValidationError(error)
            reservation.status = 'booked'
            reservation.save()
            entry.reservation = reservation
        entry.status = 'accepted' if accept else 'rejected'
        entry.decision_note = note.strip()[:3000]
        entry.decided_by = staff
        entry.decided_at = timezone.now()
        entry.save()
        transaction.on_commit(lambda pk=entry.pk: send_decision_email(pk))
        return entry
