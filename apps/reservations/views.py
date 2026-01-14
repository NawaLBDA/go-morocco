
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.core.models import Tour
from .models import Booking
from decimal import Decimal


@login_required
def book_tour(request, tour_id):
    tour = get_object_or_404(Tour, id=tour_id)
    if request.method == 'POST':
        nights = int(request.POST.get('nights', 1))
        persons = int(request.POST.get('persons', 1))
        # base price per person per night (default 1000 if not set)
        base = Decimal(tour.price_per_night if tour.price_per_night else 1000)
        # apply tour-level promotion or global promotion if set
        promo_percent = 0
        if getattr(tour, 'is_promotion', False) and getattr(tour, 'discount_percent', 0):
            promo_percent = int(tour.discount_percent)
        else:
            from apps.core.models import Promotion
            gp = Promotion.objects.filter(active=True, apply_to_all=True).first()
            if gp:
                promo_percent = int(gp.percent)

        if promo_percent:
            base = base - (base * Decimal(promo_percent) / Decimal(100))

        total = base * Decimal(nights) * Decimal(persons)
        # group discount: 10% if 5 or more persons
        if persons >= 5:
            total = total * Decimal('0.90')
        Booking.objects.create(
            user=request.user,
            tour=tour,
            nights=nights,
            persons=persons,
            total_price=total
        )
        return redirect('home')
    return render(request, 'booking.html', {'tour': tour})
