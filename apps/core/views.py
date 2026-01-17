from datetime import date, datetime, timedelta
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q
from django.conf import settings

from .models import Tour, Reservation, BlogPost, Destination, ContactMessage, BlogComment, UserProfile


def home(request):
    q = request.GET.get('q', '').strip()
    date_str = request.GET.get('date')

    tours = Tour.objects.all()

    if q:
        tours = tours.filter(
            Q(destination__name__icontains=q) |
            Q(title__icontains=q)
        )

    if date_str:
        try:
            start_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            tours = tours.exclude(
                reservations__status='booked',
                reservations__start_date__lte=start_date,
                reservations__end_date__gte=start_date
            )
        except ValueError:
            pass

    tours = tours.distinct()[:6]

    for tour in tours:
        # ✅ always compute promo
        tour.promo_price = None
        if tour.is_promotion and tour.discount_percent > 0:
            discount = (Decimal(100) - Decimal(tour.discount_percent)) / Decimal(100)
            tour.promo_price = (Decimal(tour.price_per_night) * discount).quantize(Decimal("0.01"))

        # ✅ reservation status (only if logged)
        tour.user_reservation = None
        if request.user.is_authenticated:
            tour.user_reservation = Reservation.objects.filter(
                user=request.user,
                tour=tour
            ).exclude(status__in=["rejected", "cancelled"]).order_by("-created_at").first()

    return render(request, "home.html", {"tours": tours})
def tour_detail(request, tour_id):
    tour = get_object_or_404(Tour, id=tour_id)

    reservation = None
    if request.user.is_authenticated:
        reservation = Reservation.objects.filter(
            user=request.user,
            tour=tour
        ).exclude(status__in=["rejected", "cancelled"]).order_by("-created_at").first()

    # disable ranges for booked reservations
    reservations = Reservation.objects.filter(tour=tour, status='booked')

    disabled_ranges = [
        {"from": r.start_date.isoformat(), "to": (r.end_date + timedelta(days=2)).isoformat()}
        for r in reservations
    ]

    tour.promo_price = None
    if tour.is_promotion and tour.discount_percent > 0:
        discount = (Decimal(100) - Decimal(tour.discount_percent)) / Decimal(100)
        tour.promo_price = (Decimal(tour.price_per_night) * discount).quantize(Decimal("0.01"))
    return render(request, "booking.html", {
        "tour": tour,
        "reservation": reservation,
        "disabled_ranges": disabled_ranges,
        "today": date.today(),  # ✅ IMPORTANT
        "STRIPE_PUBLIC_KEY": settings.STRIPE_PUBLIC_KEY,
    })



def blog_list(request):
    posts = BlogPost.objects.all().order_by('-created_at')
    return render(request, 'blog_list.html', {'posts': posts})


def blog_detail(request, slug):
    post = get_object_or_404(BlogPost, slug=slug)
    comments = post.comments.all()

    if request.method == 'POST' and request.user.is_authenticated:
        content = request.POST.get('content')
        if content:
            BlogComment.objects.create(post=post, user=request.user, content=content)
            return redirect('blog_detail', slug=slug)

    return render(request, 'blog_detail.html', {'post': post, 'comments': comments})


def about(request):
    return render(request, 'about.html')


def contact(request):
    if request.method == 'POST':
        ContactMessage.objects.create(
            name=request.POST.get('name'),
            email=request.POST.get('email'),
            subject=request.POST.get('subject', ''),
            message=request.POST.get('message')
        )
        messages.success(request, '✅ Your message has been sent successfully!')
        return redirect('contact')
    return render(request, 'contact.html')


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)

        if form.is_valid():
            user = form.save(commit=False)
            user.email = request.POST.get('email')
            user.first_name = request.POST.get('first_name')
            user.last_name = request.POST.get('last_name')
            user.save()

            UserProfile.objects.create(
                user=user,
                phone=request.POST.get('phone'),
                country=request.POST.get('country'),
                postal_code=request.POST.get('postal_code')
            )

            messages.success(request, "✅ Registration successful! Please log in.")
            return redirect('login')
    else:
        form = UserCreationForm()

    return render(request, 'register.html', {'form': form})


def custom_logout(request):
    logout(request)
    return render(request, 'logged_out.html')
