from decimal import Decimal
import json
import stripe
from datetime import datetime, timedelta, date
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from datetime import date

from apps.core.models import Reservation, Tour

stripe.api_key = settings.STRIPE_SECRET_KEY


# ============================================================
# TOUR DETAIL PAGE (IMPORTANT) -> envoie disabled_ranges + reservation
# ============================================================
@login_required
def tour_detail(request, tour_id):
    tour = get_object_or_404(Tour, id=tour_id)

    # ✅ Reservation du user courant sur ce tour (active)
    reservation = Reservation.objects.filter(
        user=request.user,
        tour=tour
    ).exclude(status__in=["cancelled"]).order_by("-created_at").first()

    # ✅ Bloquer uniquement les ranges BOOKED par d'autres users
    booked_by_others = Reservation.objects.filter(
        tour=tour,
        status="booked",
    ).exclude(user=request.user)

    disabled_ranges = []
    for r in booked_by_others:
        disabled_ranges.append({
            "from": r.start_date.strftime("%Y-%m-%d"),
            "to": r.end_date.strftime("%Y-%m-%d"),
        })

    return render(request, "booking.html", {
        "tour": tour,
        "reservation": reservation,
        "disabled_ranges": disabled_ranges,
        "STRIPE_PUBLIC_KEY": settings.STRIPE_PUBLIC_KEY,
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

    # ✅ conflit seulement avec BOOKED (pas pending)
    conflict = Reservation.objects.filter(
        tour=tour,
        status="booked",
        start_date__lte=end_date + timedelta(days=2),
        end_date__gte=start_date
    ).exclude(user=request.user).exists()

    if conflict:
        messages.error(request, "❌ This date range is already booked. Please choose another date.")
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
    if persons >= 5:
        total *= 0.9

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

        payment_method=payment_method,      # cash | card
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
@login_required
def admin_reservations(request):
    if not request.user.is_staff:
        return redirect("home")

    reservations = Reservation.objects.all().order_by("-created_at")
    return render(request, "admin_reservations.html", {"reservations": reservations})


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

    # ✅ only cash manual
    if r.payment_method == "cash" and r.payment_status != "paid":
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
