from datetime import date, datetime, timedelta
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from .models import Tour, Reservation, BlogPost, Destination, ContactMessage, BlogComment, UserProfile, CountryContent
from .context_processors import get_country_from_site


def home(request):
    q = request.GET.get('q', '').strip()
    date_str = request.GET.get('date')

    country = get_country_from_site(request)
    tours = Tour.objects.filter(country=country)

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

    # Load country-specific content
    try:
        country_content = CountryContent.objects.get(country=country)
        hero_title = country_content.hero_title
        hero_subtitle = country_content.hero_subtitle
        hero_image = country_content.hero_image.url if country_content.hero_image else None
    except CountryContent.DoesNotExist:
        hero_title = "Discover Morocco" if country == 'morocco' else "Discover Ireland"
        hero_subtitle = ""
        hero_image = None

    return render(request, "home.html", {
        "tours": tours,
        "hero_title": hero_title,
        "hero_subtitle": hero_subtitle,
        "hero_image": hero_image,
        "country": country
    })
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


def start_robo_call(request, reservation_id):
    if request.method != 'POST':
        return HttpResponseBadRequest('Invalid method')

    reservation = get_object_or_404(Reservation, id=reservation_id)
    if reservation.user != request.user:
        return HttpResponseForbidden('Not allowed')
    if reservation.status != 'booked':
        return HttpResponseBadRequest('Booking must be validated')
    if reservation.tour.country.lower() != 'morocco':
        return HttpResponseBadRequest('Robocall available for Morocco only')

    sid = settings.TWILIO_ACCOUNT_SID
    token = settings.TWILIO_AUTH_TOKEN
    from_number = settings.TWILIO_FROM_NUMBER
    primary = settings.ROBOCALL_PRIMARY_NUMBER
    secondary = settings.ROBOCALL_SECONDARY_NUMBER

    if not sid or not token or not from_number:
        return JsonResponse({'error': 'Twilio not configured'}, status=500)

    try:
        from twilio.rest import Client
        client = Client(sid, token)

        call = client.calls.create(
            from_=from_number,
            to=primary,
            url=request.build_absolute_uri(reverse('twiml_call_first', args=[reservation_id])),
            timeout=60
        )

        return JsonResponse({'message': 'Call initiated', 'sid': call.sid})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def twiml_call_first(request, reservation_id):
    from twilio.twiml.voice_response import VoiceResponse, Dial

    response = VoiceResponse()
    dial = Dial(timeout=60, action=request.build_absolute_uri(reverse('twiml_call_fallback', args=[reservation_id])), method='POST')
    dial.number(settings.ROBOCALL_PRIMARY_NUMBER)
    response.append(dial)
    return HttpResponse(str(response), content_type='application/xml')


@csrf_exempt
def twiml_call_fallback(request, reservation_id):
    from twilio.twiml.voice_response import VoiceResponse, Dial

    status = request.POST.get('DialCallStatus', '')
    response = VoiceResponse()

    if status in ['completed', 'answered', 'in-progress']:
        response.say('Téléphone connecté, merci. Retour à votre application.')
        return HttpResponse(str(response), content_type='application/xml')

    dial = Dial(timeout=60, action=request.build_absolute_uri(reverse('twiml_call_complete', args=[reservation_id])), method='POST')
    dial.number(settings.ROBOCALL_SECONDARY_NUMBER)
    response.say('Aucun réponse sur la première ligne. Transfert vers le second numéro.')
    response.append(dial)
    return HttpResponse(str(response), content_type='application/xml')


@csrf_exempt
def twiml_call_complete(request, reservation_id):
    from twilio.twiml.voice_response import VoiceResponse

    status = request.POST.get('DialCallStatus', '')
    response = VoiceResponse()

    if status in ['completed', 'answered', 'in-progress']:
        response.say('Appel effectué. Merci, l’agent prend la suite.')
    else:
        response.say('Nous n’avons pas pu joindre le numéro. Merci, nous réessayons bientôt.')

    return HttpResponse(str(response), content_type='application/xml')


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
