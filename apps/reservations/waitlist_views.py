from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from apps.core.catalogue import visible_tours
from apps.core.context_processors import get_country_from_site
from apps.core.models import TourDeparture, WaitlistEntry, Reservation
from .availability import departure_capacity, lock_guide_calendar
from .waitlist import decide_waitlist, send_decision_email


@login_required
@require_POST
def join_waitlist(request, departure_id):
    departure = get_object_or_404(TourDeparture.objects.select_related('tour', 'tour__region'),
        pk=departure_id, tour__in=visible_tours(request.user), is_published=True, start_date__gte=timezone.localdate())
    target = reverse('tour_detail', args=[departure.tour.slug]) + f'?departure_id={departure.pk}#departure-status'
    from .eligibility import can_book_departure, DEAF_ONLY_MESSAGE
    if not can_book_departure(request.user, departure.tour, departure):
        messages.error(request, DEAF_ONLY_MESSAGE)
        return redirect(target)
    try:
        persons = int(request.POST.get('persons', '1'))
        email = request.POST.get('email', request.user.email).strip()
        validate_email(email)
        if not 1 <= persons <= departure.max_participants:
            raise ValidationError(f'Choose between 1 and {departure.max_participants} travelers.')
        if not departure.active_days or departure.duration_days > departure.tour.max_days:
            raise ValidationError('This departure is not currently available.')
        with lock_guide_calendar(departure.tour.country):
            if departure_capacity(departure)['available']:
                raise ValidationError('This departure is available. Please use the regular booking form.')
            if Reservation.objects.filter(user=request.user, departure=departure, status__in=['pending', 'booked']).exists():
                raise ValidationError('You already have a booking for this departure.')
            entry, created = WaitlistEntry.objects.get_or_create(user=request.user, departure=departure,
                defaults={'num_persons': persons, 'email': email, 'message': request.POST.get('message', '').strip()[:3000]})
            messages.success(request, 'You have joined the waiting list. Our team will email you after reviewing your request.' if created else f'Your existing request: {entry.get_status_display()}.')
    except (ValueError, ValidationError) as exc:
        messages.error(request, ' '.join(exc.messages) if isinstance(exc, ValidationError) else 'Enter a valid group size.')
    return redirect(target)


@login_required
@require_POST
def waitlist_decision(request, entry_id, action):
    if not request.user.is_active or not request.user.is_staff:
        return HttpResponseForbidden('Staff access is required.')
    qs = WaitlistEntry.objects.all()
    if getattr(request, 'site_country', None) or request.GET.get('country'):
        qs = qs.filter(departure__tour__country=get_country_from_site(request))
    entry = get_object_or_404(qs, pk=entry_id)
    try:
        if action == 'retry-email':
            send_decision_email(entry.pk)
        elif action in ('accept', 'reject'):
            decide_waitlist(entry.pk, accept=action == 'accept', staff=request.user,
                note=request.POST.get('decision_note', ''))
        else:
            return HttpResponseForbidden('Unknown action.')
        entry.refresh_from_db()
        messages.success(request, f'Waiting-list request: {entry.get_status_display()}. Email status is shown in the list.')
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    return redirect('admin_reservations')
