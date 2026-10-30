from apps.core.catalogue import visible_tours, tour_rate, tour_discount
from apps.core.countries import uses_scheduled_departures
from decimal import Decimal
import json
import csv
from urllib.parse import urlencode
import stripe
from datetime import datetime, timedelta, date
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator
from .excel import reservations_excel
from django.core.exceptions import ValidationError
from django.views.decorators.cache import never_cache
from .availability import active_reservations, UNAVAILABLE_MESSAGE
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
from datetime import date

from apps.core.models import Reservation, Tour, TourExtraActivity
from apps.core.context_processors import get_country_from_site

stripe.api_key = settings.STRIPE_SECRET_KEY


def _bool_from_post(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "on", "yes"}


def _bool_from_any(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


def _recalculate_total_for_reservation(
    *,
    tour: Tour,
    start_date: date,
    end_date: date,
    persons: int,
    full_package: bool,
    include_transport: bool,
    include_hotel: bool,
    selected_extra_activities: list,
    charge_days: int | None = None,
    package_priced: bool | None = None,
    base_price_override: Decimal | None = None,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    nights = charge_days if charge_days is not None else max(0, (end_date - start_date).days)
    persons = max(1, int(persons or 1))

    from apps.core.catalogue import tour_rate
    package_priced = tour.package_price is not None if package_priced is None else package_priced
    base_price = Decimal(base_price_override) if base_price_override is not None else tour_rate(tour)

    if full_package:
        include_transport = True
        include_hotel = True

    transport_rate = Decimal(getattr(tour, 'transport_price_per_night', None) or 0)
    hotel_rate = Decimal(getattr(tour, 'hotel_price_per_night', None) or 0)
    transport_add = transport_rate if include_transport else Decimal('0')
    hotel_add = hotel_rate if include_hotel else Decimal('0')

    extras_total = Decimal('0')
    for item in (selected_extra_activities or []):
        try:
            price = Decimal(str(item.get('price') or '0'))
            is_per_night = bool(item.get('is_per_night'))
        except Exception:
            continue

        line = price * Decimal(persons) * (Decimal(nights) if is_per_night else Decimal('1'))
        extras_total += line

    extras_total = extras_total.quantize(Decimal('0.01'))
    nightly_total = (base_price * (1 if package_priced else Decimal(nights)) + (transport_add + hotel_add) * Decimal(nights)) * Decimal(persons)
    total = (nightly_total + extras_total).quantize(Decimal('0.01'))

    if persons > 5 and not package_priced:
        total = (total * Decimal('0.90')).quantize(Decimal('0.01'))

    return total, base_price, transport_add, hotel_add, extras_total


def _create_pending_reservation(**kwargs):
    if not getattr(kwargs.get('user'), 'is_authenticated', False):
        return None, 'Create an account or log in before booking.', None, 401
    try:
        if uses_scheduled_departures(kwargs['tour'].country):
            from .availability import lock_guide_calendar
            with lock_guide_calendar(kwargs['tour'].country):
                return _create_pending_reservation_checked(**kwargs)
        return _create_pending_reservation_checked(**kwargs)
    except ValidationError as exc:
        return None, ' '.join(exc.messages), None, 409


def _create_pending_reservation_checked(
    *,
    user,
    tour: Tour,
    start_date: date,
    end_date: date,
    persons: int,
    payment_method: str,
    full_package: bool,
    include_transport: bool,
    include_hotel: bool,
    extra_activity_ids: list[int] | None,
    departure_id=None,
):
    payment_method = (payment_method or "").strip().lower()
    if payment_method not in ({"cash", "transfer"} if uses_scheduled_departures(tour.country) else {"cash", "card"}):
        return None, "Please select a payment method.", None, 400

    if start_date < date.today():
        return None, "Start date cannot be in the past.", None, 400

    try:
        persons = int(persons)
    except (TypeError, ValueError):
        return None, 'Enter a valid number of travelers.', None, 400
    if persons < 1:
        return None, 'Choose at least one traveler.', None, 400
    departure = None
    if uses_scheduled_departures(tour.country):
        from .departures import resolve_departure
        departure = resolve_departure(tour, start_date, end_date, departure_id)
    from .eligibility import can_book_departure, DEAF_ONLY_MESSAGE
    if not can_book_departure(user, tour, departure):
        return None, DEAF_ONLY_MESSAGE, None, 403
    nights = (end_date - start_date).days
    if nights < 0 or (nights == 0 and not uses_scheduled_departures(tour.country)):
        return None, "Invalid date range.", None, 400

    max_nights = 5
    if not uses_scheduled_departures(tour.country) and nights > max_nights:
        return None, f"Maximum allowed duration is {max_nights} days.", None, 400

    from apps.core.catalogue import visible_tours
    if not visible_tours(user).filter(pk=tour.pk).exists():
        return None, 'This tour is not available to this account.', None, 404
    if departure and Reservation.objects.filter(user=user, departure=departure, status__in=['pending', 'booked']).exists():
        return None, 'You already have an active request for this departure.', None, 409
    minimum = departure.group_minimum if departure else tour.group_minimum
    maximum = departure.group_maximum if departure else tour.max_travelers
    if not minimum <= persons <= maximum:
        return None, f'Choose between {minimum} and {maximum} travelers for this package.', None, 400
    if uses_scheduled_departures(tour.country):
        from .availability import has_conflict, UNAVAILABLE_MESSAGE
        if has_conflict(start_date, end_date, country=tour.country, departure=departure):
            return None, UNAVAILABLE_MESSAGE, None, 409
    elif Reservation.objects.filter(tour__country=tour.country, status__in=['pending', 'booked'],
            start_date__lte=end_date, end_date__gte=start_date).exclude(user=user).exists():
        return None, 'These dates are already reserved.', None, 409

    extra_ids: list[int] = []
    for raw_id in (extra_activity_ids or []):
        try:
            extra_ids.append(int(raw_id))
        except Exception:
            continue

    extras_qs = TourExtraActivity.objects.filter(tour=tour, is_active=True)
    if extra_ids or uses_scheduled_departures(tour.country):
        extras_qs = extras_qs.filter(id__in=extra_ids)
    extras = list(extras_qs.order_by("id"))
    if departure:
        active_numbers = set(departure.program_days.filter(is_visible=True).values_list('day_number', flat=True))
        extras = [extra for extra in extras if not extra.insert_into_itinerary or extra.itinerary_day_number in active_numbers]

    selected_extras_payload = [
        {
            "id": int(extra.id),
            "title": extra.title,
            "price": str(Decimal(extra.price or 0)),
            "is_per_night": bool(extra.is_per_night),
        }
        for extra in extras
    ]

    total, base_price, transport_add, hotel_add, extras_total = _recalculate_total_for_reservation(
        tour=tour,
        start_date=start_date,
        end_date=end_date,
        persons=persons,
        full_package=full_package,
        include_transport=include_transport,
        include_hotel=include_hotel,
        selected_extra_activities=selected_extras_payload,
        charge_days=(departure.duration_days if tour.package_price is not None else departure.active_days) if departure else None,
    )

    from .deposits import deposit_terms
    deposit = deposit_terms(tour, persons, total)
    with transaction.atomic():
        existing_qs = Reservation.objects.select_for_update().filter(
            user=user,
            tour__country=tour.country,
        ).exclude(status__in=["cancelled", "rejected"]).order_by("-created_at")

        replaced_existing = not uses_scheduled_departures(tour.country) and existing_qs.exists()
        if replaced_existing:
            existing_qs.update(status="cancelled")

        reservation = Reservation.objects.create(
            user=user,
            tour=tour,
            departure=departure,
            **deposit,
            package_priced=tour.package_price is not None,
            priced_per_day=bool(departure),
            booked_days=(departure.duration_days if tour.package_price is not None else departure.active_days) if departure else None,
            start_date=start_date,
            end_date=end_date,
            num_persons=persons,
            total_price=total,
            full_package=bool(full_package),
            include_transport=bool(include_transport or full_package),
            include_hotel=bool(include_hotel or full_package),
            selected_extra_activities=selected_extras_payload,
            extras_total=extras_total,
            base_price_per_night=base_price,
            transport_price_per_night=transport_add,
            hotel_price_per_night=hotel_add,
            status="pending",
            payment_method=payment_method,
            payment_status="unpaid",
            stripe_payment_intent="",
        )

    info_message = "Your previous booking was updated with new dates." if replaced_existing else None
    if reservation.deposit_pending:
        info_message = f'A deposit of ${reservation.deposit_required_amount} is required before approval. Our team will contact you by email with payment instructions.'
    return reservation, None, info_message, 200


@login_required
@require_POST
def chat_book_tour(request):
    country = get_country_from_site(request)

    try:
        payload = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"success": False, "reply": "Invalid booking payload."}, status=400)

    try:
        tour_id = int(payload.get("tour_id"))
    except Exception:
        return JsonResponse({"success": False, "reply": "Tour not found for this booking request."}, status=400)

    tour = get_object_or_404(visible_tours(request.user), id=tour_id, country=country)

    start_raw = str(payload.get("start_date") or "").strip()
    end_raw = str(payload.get("end_date") or "").strip()
    try:
        start_date = datetime.strptime(start_raw, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_raw, "%Y-%m-%d").date()
    except Exception:
        return JsonResponse(
            {"success": False, "reply": "Please share valid dates in YYYY-MM-DD format."},
            status=400,
        )

    try:
        persons = int(payload.get("persons", 1))
    except Exception:
        persons = 1

    reservation, error_message, info_message, status_code = _create_pending_reservation(
        user=request.user,
        tour=tour,
        start_date=start_date,
        end_date=end_date,
        persons=persons,
        payment_method=str(payload.get("payment_method") or "").strip().lower(),
        full_package=_bool_from_any(payload.get("full_package")),
        include_transport=_bool_from_any(payload.get("include_transport")),
        include_hotel=_bool_from_any(payload.get("include_hotel")),
        extra_activity_ids=payload.get("extra_activity_ids") or [],
        departure_id=payload.get('departure_id'),
    )

    lang = str(payload.get("lang") or "en").strip().lower()
    if lang not in {"fr", "en"}:
        lang = "en"

    if error_message:
        reply = error_message
        if lang == "fr":
            if status_code == 409:
                reply = "Ces dates ne sont pas disponibles. Merci de choisir un autre intervalle."
            elif "payment method" in error_message.lower():
                reply = "Merci de choisir un mode de paiement : carte ou especes."
            elif "date" in error_message.lower():
                reply = "Les dates envoyees ne sont pas valides. Merci de choisir un autre intervalle."
        return JsonResponse({"success": False, "reply": reply}, status=status_code)

    parts = []
    if lang == "fr":
        if info_message:
            parts.append("Ta precedente reservation a ete remplacee par les nouvelles dates.")
        parts.append(
            f"Reservation envoyee pour {tour.title} du {start_date.isoformat()} au {end_date.isoformat()} pour {persons} personne(s). Elle est maintenant en attente de validation admin."
        )
    else:
        if info_message:
            parts.append("Your previous booking was replaced with the new dates.")
        parts.append(
            f"Your booking request for {tour.title} from {start_date.isoformat()} to {end_date.isoformat()} for {persons} traveler(s) has been submitted and is now pending admin validation."
        )

    return JsonResponse(
        {
            "success": True,
            "reply": " ".join(parts),
            "reservation_id": reservation.id if reservation else None,
        }
    )


# ============================================================
# TOUR DETAIL PAGE (IMPORTANT) -> envoie disabled_ranges + reservation
# ============================================================
@login_required
def tour_detail(request, tour_id):
    country = get_country_from_site(request)
    tour = get_object_or_404(visible_tours(request.user), id=tour_id, country=country)

    # Compute promo price for template display.
    if tour_discount(tour) > 0:
        try:
            discount = (Decimal(100) - Decimal(tour_discount(tour))) / Decimal(100)
            tour.promo_price = (Decimal(tour.price_per_night) * discount).quantize(Decimal('0.01'))
        except Exception:
            tour.promo_price = None
    else:
        tour.promo_price = None

    reservation = Reservation.objects.filter(
        user=request.user,
        tour=tour,
    ).exclude(status__in=["rejected", "cancelled", "completed"]).order_by("-created_at").first()

    # Single group booking rules:
    # - block any already reserved dates across ALL tours in the same country
    # - include pending + booked
    # - add a buffer after each tour so the group can reset/prep
    buffer_days = 0
    active_statuses = ['pending', 'booked']

    active_reservations = Reservation.objects.filter(
        tour__country=country,
        status__in=active_statuses,
    )
    if not uses_scheduled_departures(country):
        active_reservations = active_reservations.exclude(user=request.user)

    disabled_ranges = [
        {
            "from": r.start_date.isoformat(),
            "to": r.end_date.isoformat(),
        }
        for r in active_reservations.order_by('start_date')
    ]

    return render(request, "booking.html", {
        "tour": tour,
        "reservation": reservation,
        "disabled_ranges": disabled_ranges,
        "STRIPE_PUBLIC_KEY": settings.STRIPE_PUBLIC_KEY,
        "activities_list": [a.strip() for a in (tour.activities or '').replace('\n', ',').split(',') if a.strip()],
        "extra_activities": list(tour.extra_activities.filter(is_active=True).order_by('id')),
        "today": date.today(),
        "booking_max_nights": 5,
        "booking_buffer_days": buffer_days,
    })


# ============================================================
# CREATE BOOKING (ALWAYS PENDING)
# ============================================================
@login_required
def book_tour(request, tour_id):
    country = get_country_from_site(request)
    tour = get_object_or_404(visible_tours(request.user), id=tour_id, country=country)

    if request.method != "POST":
        return redirect("tour_detail", tour_slug=tour.slug)

    start = request.POST.get("start_date")
    end = request.POST.get("end_date")
    try:
        persons = int(request.POST.get("persons", 1))
    except Exception:
        persons = 1

    try:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
    except Exception:
        messages.error(request, "Invalid date format")
        return redirect("tour_detail", tour_slug=tour.slug)

    reservation, error_message, info_message, _status_code = _create_pending_reservation(
        user=request.user,
        tour=tour,
        start_date=start_date,
        end_date=end_date,
        persons=persons,
        payment_method=(request.POST.get("payment_method") or "").strip().lower(),
        full_package=_bool_from_post(request.POST.get("full_package")),
        include_transport=_bool_from_post(request.POST.get("include_transport")),
        include_hotel=_bool_from_post(request.POST.get("include_hotel")),
        extra_activity_ids=request.POST.getlist("extra_activity_ids"),
        departure_id=request.POST.get('departure_id'),
    )
    if error_message:
        messages.error(request, error_message)
        if uses_scheduled_departures(country):
            query = urlencode({'departure_id': request.POST.get('departure_id', ''), 'start_date': start, 'end_date': end, 'persons': persons})
            return redirect(reverse('tour_detail', args=[tour.slug]) + '?' + query)
        return redirect("tour_detail", tour_slug=tour.slug)

    if info_message:
        messages.info(request, info_message)
    if reservation:
        messages.success(request, "Booking request submitted. Waiting for admin validation.")
        return redirect('my_reservations')
    if uses_scheduled_departures(country):
        return redirect("tour_detail", tour_slug=tour.slug)
    return redirect("home")

# ============================================================
# ✅ Stripe Intent creation ONLY AFTER admin validation
# ============================================================
@login_required
@require_POST
def create_payment_intent_for_reservation(request, reservation_id):
    r = get_object_or_404(Reservation, id=reservation_id, user=request.user)

    # ✅ Only if booked + card + unpaid
    if uses_scheduled_departures(r.tour.country):
        return JsonResponse({"error": "Please arrange bank transfer with your guide after validation."}, status=400)

    if r.status != "booked":
        return JsonResponse({"error": "Booking not validated yet."}, status=400)

    if r.payment_method != "card":
        return JsonResponse({"error": "This reservation is not card payment."}, status=400)

    if r.payment_status == "paid":
        return JsonResponse({"error": "Already paid."}, status=400)

    amount = int(float(r.total_price) * 100)

    intent = stripe.PaymentIntent.create(
        amount=amount,
        currency="mad",
        automatic_payment_methods={"enabled": True},
        metadata={
            "reservation_id": str(r.id),
            "tour_id": str(r.tour.id),
            "user": r.user.username,
        }
    )

    # ✅ store intent id (optional)
    r.stripe_payment_intent = intent.id
    r.save(update_fields=["stripe_payment_intent"])

    return JsonResponse({
        "client_secret": intent.client_secret,
        "intent_id": intent.id
    })


# ============================================================
# CANCEL reservation (ONLY if pending/rejected and still future)
# ============================================================
@login_required
def cancel_reservation(request, id):
    if not request.user.is_staff:
        messages.info(request, "Please contact us to cancel your reservation.")
        return redirect("home")

    r = get_object_or_404(Reservation, id=id, tour__country=get_country_from_site(request))

    today = date.today()
    # ✅ cannot cancel if booked/completed OR date passed
    if r.status in {"booked", "completed"} or r.end_date < today:
        messages.info(request, "You cannot cancel this reservation.")
        return redirect("home")

    if r.status in ["pending", "rejected"]:
        r.status = "cancelled"
        r.save()
        messages.success(request, "✅ Reservation cancelled.")

    return redirect("home")


# ============================================================
# ADMIN
# ============================================================


def _get_profile_fields(user):
    try:
        profile = getattr(user, 'profile', None)
        if not profile:
            return None
        return {
            'profile_phone': getattr(profile, 'phone', ''),
            'profile_country': getattr(profile, 'country', ''),
            'profile_postal_code': getattr(profile, 'postal_code', ''),
        }
    except Exception:
        return None


def _reservation_report_headers():
    return [
        'reservation_id',
        'created_at',
        'status',
        'admin_note',
        'payment_method',
        'payment_status',
        'stripe_payment_intent',
        'tour_id',
        'tour_title',
        'tour_country',
        'destination',
        'start_date',
        'end_date',
        'nights',
        'num_persons',
        'total_price',
        'full_package',
        'include_transport',
        'transport_price_per_night',
        'include_hotel',
        'hotel_price_per_night',
        'extras_total',
        'selected_extra_activities',
        'base_price_per_night',
        'booking_for_other',
        'guest_full_name',
        'guest_phone',
        'user_id',
        'username',
        'email',
        'first_name',
        'last_name',
        'is_staff',
        'is_active',
        'date_joined',
        'last_login',
        'profile_phone',
        'profile_country',
        'profile_postal_code',
    ]


def _reservation_report_row(r):
    u = r.user
    t = r.tour
    destination_name = ''
    try:
        destination_name = getattr(getattr(t, 'destination', None), 'name', '') or ''
    except Exception:
        destination_name = ''

    profile_fields = _get_profile_fields(u) or {
        'profile_phone': '',
        'profile_country': '',
        'profile_postal_code': '',
    }

    return [
        r.id,
        r.created_at.isoformat() if getattr(r, 'created_at', None) else '',
        r.status,
        r.admin_note,
        r.payment_method,
        r.payment_status,
        r.stripe_payment_intent or '',
        getattr(t, 'id', ''),
        getattr(t, 'title', ''),
        getattr(t, 'country', ''),
        destination_name,
        r.start_date.isoformat() if r.start_date else '',
        r.end_date.isoformat() if r.end_date else '',
        getattr(r, 'nights', ''),
        r.num_persons,
        str(r.total_price),
        'yes' if getattr(r, 'full_package', False) else 'no',
        'yes' if getattr(r, 'include_transport', False) else 'no',
        str(getattr(r, 'transport_price_per_night', '') or ''),
        'yes' if getattr(r, 'include_hotel', False) else 'no',
        str(getattr(r, 'hotel_price_per_night', '') or ''),
        str(getattr(r, 'extras_total', '') or ''),
        str(getattr(r, 'selected_extra_activities', '') or ''),
        str(getattr(r, 'base_price_per_night', '') or ''),
        'yes' if r.booking_for_other else 'no',
        r.guest_full_name,
        r.guest_phone,
        u.id,
        u.username,
        u.email,
        u.first_name,
        u.last_name,
        'yes' if u.is_staff else 'no',
        'yes' if u.is_active else 'no',
        u.date_joined.isoformat() if u.date_joined else '',
        u.last_login.isoformat() if u.last_login else '',
        profile_fields['profile_phone'],
        profile_fields['profile_country'],
        profile_fields['profile_postal_code'],
    ]


def _reservations_to_csv_response(reservations_qs, filename: str) -> HttpResponse:
    """Excel-friendly CSV with clear columns for traceability.

    Uses ';' delimiter which is the most compatible with French Excel locales.
    """
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # Excel-friendly UTF-8 BOM
    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(_reservation_report_headers())

    for r in reservations_qs:
        writer.writerow(_reservation_report_row(r))

    return response

@login_required
def admin_reservations(request):
    if not request.user.is_staff:
        return redirect("home")

    reservations_qs = Reservation.objects.select_related(
        'user', 'user__profile',
        'tour',
        'tour__destination',
    ).order_by("-created_at")
    from apps.core.admin_workspace import reservation_country
    active_country = reservation_country(request)
    reservations_qs = reservations_qs.filter(tour__country=active_country.slug)

    query = (request.GET.get('q') or request.POST.get('q') or '').strip()
    if query:
        matching = (Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query)
                    | Q(user__username__icontains=query) | Q(user__email__icontains=query)
                    | Q(user__profile__phone__icontains=query) | Q(tour__title__icontains=query)
                    | Q(tour__destination__name__icontains=query) | Q(status__icontains=query)
                    | Q(guest_full_name__icontains=query) | Q(guest_phone__icontains=query))
        full_name = Q()
        for word in query.split():
            full_name &= Q(user__first_name__icontains=word) | Q(user__last_name__icontains=word)
        matching |= full_name
        if query.isdigit():
            matching |= Q(pk=int(query))
        reservations_qs = reservations_qs.filter(matching)

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        selected_ids = request.POST.getlist('reservation_ids')
        selected_qs = reservations_qs
        if selected_ids:
            selected_qs = reservations_qs.filter(id__in=selected_ids)

        if action == 'delete_selected':
            if not selected_ids:
                messages.error(request, 'Select at least one reservation to delete.')
                return redirect('admin_reservations')

            deleted_count, _ = selected_qs.delete()
            messages.success(request, f'✅ Deleted {deleted_count} reservation(s).')
            return redirect('admin_reservations')

        if action == 'download_report':
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'reservations_report_{ts}.xlsx'
            return reservations_excel(selected_qs, filename)

        messages.info(request, 'Choose an action to apply.')
        return redirect('admin_reservations')

    page = Paginator(reservations_qs, 7).get_page(request.GET.get('page'))
    from apps.core.models import WaitlistEntry
    waiting = WaitlistEntry.objects.select_related('user', 'departure__tour', 'reservation').order_by('-created_at')
    waiting = waiting.filter(departure__tour__country=active_country.slug)
    return render(request, "admin_reservations.html", {
        'admin_country': active_country,
        'waitlist_entries': waiting[:100],
        "reservations": page,
        "page_obj": page,
        "search_query": query,
        "reservations_count": reservations_qs.count(),
    })


@login_required
@require_POST
def admin_update_reservation(request, id):
    if not request.user.is_staff:
        return redirect("home")

    r = get_object_or_404(Reservation.objects.select_related('tour'), id=id, tour__country=get_country_from_site(request))

    try:
        start_date = datetime.strptime(request.POST.get('start_date') or '', '%Y-%m-%d').date()
        end_date = datetime.strptime(request.POST.get('end_date') or '', '%Y-%m-%d').date()
    except Exception:
        messages.error(request, 'Invalid date format.')
        return redirect('admin_reservations')

    nights = (end_date - start_date).days
    if nights < 0 or (nights == 0 and not r.priced_per_day):
        messages.error(request, 'Invalid date range.')
        return redirect('admin_reservations')

    try:
        persons = int(request.POST.get('num_persons', 1))
    except Exception:
        persons = 1
    persons = max(1, persons)

    status = (request.POST.get('status') or r.status).strip().lower()
    if status not in {c[0] for c in Reservation.STATUS_CHOICES}:
        status = r.status

    payment_method = (request.POST.get('payment_method') or '').strip().lower() or None
    if payment_method not in {c[0] for c in Reservation.PAYMENT_CHOICES}:
        payment_method = None

    payment_status = (request.POST.get('payment_status') or r.payment_status).strip().lower()
    if payment_status not in {c[0] for c in Reservation.PAYMENT_STATUS}:
        payment_status = r.payment_status

    full_package = r.full_package
    include_transport = r.include_transport
    include_hotel = r.include_hotel
    booking_for_other = r.booking_for_other

    guest_full_name = (request.POST.get('guest_full_name', r.guest_full_name) or '').strip()
    guest_phone = (request.POST.get('guest_phone', r.guest_phone) or '').strip()
    admin_note = (request.POST.get('admin_note') or '').strip()

    total, base_price, transport_add, hotel_add, extras_total = _recalculate_total_for_reservation(
        tour=r.tour,
        start_date=start_date,
        end_date=end_date,
        persons=persons,
        full_package=full_package,
        include_transport=include_transport,
        include_hotel=include_hotel,
        selected_extra_activities=r.selected_extra_activities,
        charge_days=r.booked_days if r.priced_per_day else None,
        package_priced=r.package_priced,
        base_price_override=r.base_price_per_night or r.tour.price_per_night,
    )

    r.start_date = start_date
    r.end_date = end_date
    r.num_persons = persons
    r.status = status

    r.payment_method = payment_method
    r.payment_status = payment_status

    r.full_package = full_package
    r.include_transport = include_transport or full_package
    r.include_hotel = include_hotel or full_package

    r.base_price_per_night = base_price
    r.transport_price_per_night = transport_add
    r.hotel_price_per_night = hotel_add
    r.extras_total = extras_total
    r.total_price = total

    r.booking_for_other = booking_for_other
    r.guest_full_name = guest_full_name
    r.guest_phone = guest_phone
    r.admin_note = admin_note

    try:
        r.save()
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
        return redirect('admin_reservations')
    messages.success(request, '✅ Reservation updated.')
    return redirect('admin_reservations')


@login_required
@require_POST
def delete_reservation(request, id):
    if not request.user.is_staff:
        return redirect("home")

    r = get_object_or_404(Reservation, id=id, tour__country=get_country_from_site(request))
    r.delete()
    messages.success(request, '✅ Reservation deleted.')
    return redirect('admin_reservations')


@login_required
@require_http_methods(['GET'])
def download_reservation_report(request, id):
    if not request.user.is_staff:
        return redirect("home")

    qs = Reservation.objects.select_related('user', 'tour', 'tour__destination').filter(id=id, tour__country=get_country_from_site(request))
    r = get_object_or_404(qs, id=id)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'reservation_{r.id}_report_{ts}.xlsx'
    filename = f'reservation_{r.id}_report_{ts}.xlsx'
    return reservations_excel(qs, filename)


@login_required
@require_POST
def validate_reservation(request, id):
    if not request.user.is_staff:
        return redirect("home")

    r = get_object_or_404(Reservation, id=id, tour__country=get_country_from_site(request))
    r.status = "booked"
    try:
        r.save()
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
        return redirect('admin_reservations')
    messages.success(request, "✅ Reservation validated.")
    return redirect("admin_reservations")


@login_required
@require_POST
def reject_reservation(request, id):
    if not request.user.is_staff:
        return redirect("home")

    r = get_object_or_404(Reservation, id=id, tour__country=get_country_from_site(request))
    r.status = "rejected"
    r.save()
    messages.error(request, "❌ Reservation rejected.")
    return redirect("admin_reservations")


@login_required
@require_POST
def mark_paid_reservation(request, id):
    if not request.user.is_staff:
        return redirect("home")

    r = get_object_or_404(Reservation, id=id, tour__country=get_country_from_site(request))

    # ✅ allow manual marking for cash and transfer methods
    if (r.payment_method in ["cash", "transfer"]) and r.payment_status != "paid":
        r.payment_status = "paid"
        try:
            r.save()
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
            return redirect('admin_reservations')
        messages.success(request, "✅ Payment marked as PAID.")
    else:
        messages.info(request, "Nothing to update.")

    return redirect("admin_reservations")


# ============================================================
# STRIPE WEBHOOK -> update ONLY payment_status
# ============================================================
@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    if not settings.STRIPE_WEBHOOK_SECRET:
        return JsonResponse({'status': 'webhook not configured'}, status=503)
    try:
        event = stripe.Webhook.construct_event(payload, request.META.get('HTTP_STRIPE_SIGNATURE', ''), settings.STRIPE_WEBHOOK_SECRET)
    except Exception:
        return JsonResponse({"status": "invalid"}, status=400)

    if event.type == "payment_intent.succeeded":
        intent = event.data.object

        # ✅ mark paid only
        for reservation in Reservation.objects.filter(stripe_payment_intent=intent.id).exclude(payment_status='paid'):
            reservation.payment_status = 'paid'
            reservation.save(update_fields=['payment_status'])

    return JsonResponse({"status": "ok"})
@login_required
@require_POST
def admin_cancel_reservation(request, id):
    if not request.user.is_staff:
        return redirect("home")

    r = get_object_or_404(Reservation, id=id, tour__country=get_country_from_site(request))

    # ✅ Admin can cancel ONLY booked + unpaid
    if r.status == "booked" and r.payment_status != "paid":
        r.status = "cancelled"
        r.save()
        messages.success(request, "✅ Reservation cancelled by admin.")
    else:
        messages.info(request, "Cannot cancel this reservation.")

    return redirect("admin_reservations")


@never_cache
@require_http_methods(['GET'])
def guide_availability(request):
    """Public dates only; never expose reservation or traveler information."""
    country = get_country_from_site(request)
    if not uses_scheduled_departures(country):
        return JsonResponse({'error': 'Not available on this site.'}, status=404)
    from .availability import full_calendar_ranges
    ranges = full_calendar_ranges(country)
    payload = {'blocked_ranges': [{'from': start.isoformat(), 'to': end.isoformat()}
        for start, end in ranges if end >= date.today()]}
    departure = None
    start_raw, end_raw = request.GET.get('start_date'), request.GET.get('end_date')
    if start_raw or end_raw:
        try:
            start, end = date.fromisoformat(start_raw or ''), date.fromisoformat(end_raw or '')
        except ValueError:
            return JsonResponse({'error': 'Choose a start and end date.'}, status=400)
        if start < date.today() or end < start:
            return JsonResponse({'error': 'Choose a start date today or later, with an end date on or after the start.'}, status=400)
        if request.GET.get('departure_id'):
            from .departures import resolve_departure
            try:
                departure = resolve_departure(
                    get_object_or_404(visible_tours(request.user), pk=request.GET.get('tour_id'), country=country),
                    start, end, request.GET['departure_id'])
                payload['days'] = departure.duration_days if departure.tour.package_price is not None else departure.active_days
            except (ValidationError, ValueError) as exc:
                return JsonResponse({'error': str(exc.messages[0]) if isinstance(exc, ValidationError) else 'Invalid departure.'}, status=400)
        from .availability import has_conflict, departure_capacity
        payload['available'] = not has_conflict(start, end, country=country, departure=departure)
        if departure:
            payload.update(departure_capacity(departure))
        payload['message'] = ('These dates are available to request. Your guide will confirm your booking.'
                              if payload['available'] else UNAVAILABLE_MESSAGE)
    return JsonResponse(payload)
