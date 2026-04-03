from decimal import Decimal
import json
import csv
import stripe
from datetime import datetime, timedelta, date
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
from datetime import date

from apps.core.models import Reservation, Tour
from apps.core.context_processors import get_country_from_site

stripe.api_key = settings.STRIPE_SECRET_KEY


# ============================================================
# TOUR DETAIL PAGE (IMPORTANT) -> envoie disabled_ranges + reservation
# ============================================================
@login_required
def tour_detail(request, tour_id):
    country = get_country_from_site(request)
    tour = get_object_or_404(Tour, id=tour_id, country=country)

    # Compute promo price for template display.
    if tour.is_promotion and (tour.discount_percent or 0) > 0:
        try:
            discount = (Decimal(100) - Decimal(tour.discount_percent)) / Decimal(100)
            tour.promo_price = (Decimal(tour.price_per_night) * discount).quantize(Decimal('0.01'))
        except Exception:
            tour.promo_price = None
    else:
        tour.promo_price = None

    reservation = Reservation.objects.filter(
        user=request.user,
        tour=tour,
    ).exclude(status__in=["rejected", "cancelled"]).order_by("-created_at").first()

    # Single group booking rules:
    # - block any already reserved dates across ALL tours in the same country
    # - include pending + booked
    # - add a buffer after each tour so the group can reset/prep
    buffer_days = 3
    active_statuses = ['pending', 'booked']

    active_reservations = Reservation.objects.filter(
        tour__country=country,
        status__in=active_statuses,
    ).exclude(user=request.user)

    disabled_ranges = [
        {
            "from": r.start_date.isoformat(),
            "to": (r.end_date + timedelta(days=buffer_days)).isoformat(),
        }
        for r in active_reservations.order_by('start_date')
    ]

    return render(request, "booking.html", {
        "tour": tour,
        "reservation": reservation,
        "disabled_ranges": disabled_ranges,
        "STRIPE_PUBLIC_KEY": settings.STRIPE_PUBLIC_KEY,
        "activities_list": [a.strip() for a in (tour.activities or '').replace('\n', ',').split(',') if a.strip()],
        "today": date.today(),
        "booking_max_nights": 11,
        "booking_buffer_days": buffer_days,
    })


# ============================================================
# CREATE BOOKING (ALWAYS PENDING)
# ============================================================
@login_required
def book_tour(request, tour_id):
    tour = get_object_or_404(Tour, id=tour_id)

    if request.method != "POST":
        return redirect("tour_detail", tour_id=tour.id)

    start = request.POST.get("start_date")
    end = request.POST.get("end_date")
    persons = int(request.POST.get("persons", 1))
    payment_method = request.POST.get("payment_method", "cash")

    try:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
    except:
        messages.error(request, "Invalid date format")
        return redirect("tour_detail", tour_id=tour.id)

    nights = (end_date - start_date).days
    if nights <= 0:
        messages.error(request, "Invalid date range")
        return redirect("tour_detail", tour_id=tour.id)

    # ✅ business rule: reservations must not exceed 11 nights
    max_nights = 11
    if nights > max_nights:
        messages.error(request, f"Maximum allowed duration is {max_nights} nights.")
        return redirect("tour_detail", tour_id=tour.id)

    # ✅ single-group rule:
    # Block ANY overlap with other active reservations across the same country,
    # plus a buffer after the existing trip for reset/prep.
    buffer_days = 3
    active_statuses = ["pending", "booked"]
    window_start = start_date - timedelta(days=buffer_days)
    window_end = end_date + timedelta(days=buffer_days)

    candidates = Reservation.objects.filter(
        tour__country=tour.country,
        status__in=active_statuses,
        start_date__lte=window_end,
        end_date__gte=window_start,
    ).exclude(user=request.user)

    def _overlaps(a_start, a_end, b_start, b_end):
        return a_start <= b_end and a_end >= b_start

    for r in candidates.order_by('start_date'):
        blocked_start = r.start_date
        blocked_end = r.end_date + timedelta(days=buffer_days)
        if _overlaps(start_date, end_date, blocked_start, blocked_end):
            messages.error(
                request,
                "❌ These dates are unavailable (our group is already booked). "
                "Please choose another date range."
            )
            return redirect("tour_detail", tour_id=tour.id)

    # total
    base_price = Decimal(tour.price_per_night)

    if tour.is_promotion and tour.discount_percent > 0:
        discount = (Decimal(100) - Decimal(tour.discount_percent)) / Decimal(100)
        base_price = (base_price * discount).quantize(Decimal("0.01"))

    total = base_price * Decimal(nights) * Decimal(persons)

    # ✅ 10% discount for 5+ persons
    if persons >= 5:
        total = (total * Decimal("0.90")).quantize(Decimal("0.01"))

    # ✅ single-group: user can only have one active reservation per country.
    # If they submit new dates, cancel any previous active reservation in this country.
    existing_qs = Reservation.objects.filter(
        user=request.user,
        tour__country=tour.country,
    ).exclude(status__in=["cancelled", "rejected"]).order_by('-created_at')

    if existing_qs.exists():
        existing_qs.update(status="cancelled")
        messages.info(request, "ℹ️ Your previous booking was updated with new dates.")

    Reservation.objects.create(
        user=request.user,
        tour=tour,
        start_date=start_date,
        end_date=end_date,
        num_persons=persons,
        total_price=total,

        booking_for_other=request.POST.get("booking_for") == "other",
        guest_full_name=request.POST.get("guest_full_name", ""),
        guest_phone=request.POST.get("guest_phone", ""),

        # ✅ ALWAYS pending
        status="pending",

        payment_method=payment_method,      # cash | transfer
        payment_status="unpaid",            # unpaid until paid
        stripe_payment_intent=""            # empty for now
    )

    messages.success(request, "✅ Booking request submitted. Waiting for admin validation.")
    return redirect("home")


# ============================================================
# ✅ Stripe Intent creation ONLY AFTER admin validation
# ============================================================
@login_required
@require_POST
def create_payment_intent_for_reservation(request, reservation_id):
    r = get_object_or_404(Reservation, id=reservation_id, user=request.user)

    # ✅ Only if booked + card + unpaid
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
    r = get_object_or_404(Reservation, id=id, user=request.user)

    today = date.today()
    # ✅ cannot cancel if booked OR date passed
    if r.status == "booked" or r.end_date < today:
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
        'user',
        'tour',
        'tour__destination',
    ).all().order_by("-created_at")

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
            filename = f'reservations_report_{ts}.csv'
            return _reservations_to_csv_response(selected_qs, filename)

        messages.info(request, 'Choose an action to apply.')
        return redirect('admin_reservations')

    return render(request, "admin_reservations.html", {
        "reservations": reservations_qs,
        "reservations_count": reservations_qs.count(),
    })


@login_required
@require_POST
def delete_reservation(request, id):
    if not request.user.is_staff:
        return redirect("home")

    r = get_object_or_404(Reservation, id=id)
    r.delete()
    messages.success(request, '✅ Reservation deleted.')
    return redirect('admin_reservations')


@login_required
@require_http_methods(['GET'])
def download_reservation_report(request, id):
    if not request.user.is_staff:
        return redirect("home")

    qs = Reservation.objects.select_related('user', 'tour', 'tour__destination').filter(id=id)
    r = get_object_or_404(qs, id=id)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'reservation_{r.id}_report_{ts}.xlsx'
    filename = f'reservation_{r.id}_report_{ts}.csv'
    return _reservations_to_csv_response(qs, filename)


@login_required
def validate_reservation(request, id):
    if not request.user.is_staff:
        return redirect("home")

    r = get_object_or_404(Reservation, id=id)
    r.status = "booked"
    r.save()
    messages.success(request, "✅ Reservation validated.")
    return redirect("admin_reservations")


@login_required
def reject_reservation(request, id):
    if not request.user.is_staff:
        return redirect("home")

    r = get_object_or_404(Reservation, id=id)
    r.status = "rejected"
    r.save()
    messages.error(request, "❌ Reservation rejected.")
    return redirect("admin_reservations")


@login_required
def mark_paid_reservation(request, id):
    if not request.user.is_staff:
        return redirect("home")

    r = get_object_or_404(Reservation, id=id)

    # ✅ allow manual marking for cash and transfer methods
    if (r.payment_method in ["cash", "transfer"]) and r.payment_status != "paid":
        r.payment_status = "paid"
        r.save()
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
    try:
        event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)
    except Exception:
        return JsonResponse({"status": "invalid"}, status=400)

    if event.type == "payment_intent.succeeded":
        intent = event.data.object

        # ✅ mark paid only
        Reservation.objects.filter(stripe_payment_intent=intent.id).update(
            payment_status="paid"
        )

    return JsonResponse({"status": "ok"})
@login_required
def admin_cancel_reservation(request, id):
    if not request.user.is_staff:
        return redirect("home")

    r = get_object_or_404(Reservation, id=id)

    # ✅ Admin can cancel ONLY booked + unpaid
    if r.status == "booked" and r.payment_status != "paid":
        r.status = "cancelled"
        r.save()
        messages.success(request, "✅ Reservation cancelled by admin.")
    else:
        messages.info(request, "Cannot cancel this reservation.")

    return redirect("admin_reservations")
