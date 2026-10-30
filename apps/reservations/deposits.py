"""Deposit tracking only: staff record receipt after verifying payment externally."""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.core.models import Reservation
from .availability import lock_guide_calendar


def deposit_terms(tour, persons, total):
    if not tour.deposit_enabled or persons < tour.deposit_min_travelers:
        return {'deposit_status': 'not_required', 'deposit_required_amount': Decimal('0.00')}
    amount = (Decimal(str(tour.deposit_amount)) * (persons if tour.deposit_per_person else 1)).quantize(Decimal('0.01'))
    if amount <= 0 or amount > total:
        raise ValidationError('The deposit settings need team review before this package can be requested.')
    return {'deposit_status': 'awaiting', 'deposit_required_amount': amount}


def record_deposit_received(reservation_id, staff):
    if not staff.is_active or not staff.is_staff:
        raise ValidationError('Staff access is required.')
    country = Reservation.objects.select_related('tour').get(pk=reservation_id).tour.country
    with lock_guide_calendar(country):
        booking = Reservation.objects.select_for_update().select_related('tour').get(pk=reservation_id)
        if booking.deposit_status == 'received':
            return booking
        if not booking.deposit_pending or booking.status != 'pending':
            raise ValidationError('Only a pending booking with a required deposit can be updated.')
        booking.deposit_status = 'received'
        booking.deposit_received_at = timezone.now()
        booking.deposit_received_by = staff
        booking.save(update_fields=['deposit_status', 'deposit_received_at', 'deposit_received_by'])
        return booking
