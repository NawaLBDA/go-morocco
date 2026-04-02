import json
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

import openai
from django.db.utils import OperationalError, ProgrammingError

try:
    from huggingface_hub import InferenceClient
except ImportError:
    InferenceClient = None

from .models import Tour, Reservation, BlogPost, Destination, ContactMessage, BlogComment, UserProfile, CountryContent, Information, ChatMessage
from .context_processors import get_country_from_site


def home(request):
    q = request.GET.get('q', '').strip()
    # Backward compatible: old param `date` maps to `start_date`
    start_date_str = (request.GET.get('start_date') or request.GET.get('date') or '').strip()
    end_date_str = (request.GET.get('end_date') or '').strip()

    country = get_country_from_site(request)
    try:
        tours = Tour.objects.filter(country=country)
    except (OperationalError, ProgrammingError):
        tours = Tour.objects.none()

    if q and tours is not None:
        try:
            tours = tours.filter(
                Q(destination__name__icontains=q) |
                Q(title__icontains=q)
            )
        except (OperationalError, ProgrammingError):
            tours = Tour.objects.none()

    # Date filtering: treat selected date as trip start by default.
    # If end_date is provided, filter by range overlap.
    if start_date_str:
        try:
            start_date_val = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date_val = None
            if end_date_str:
                try:
                    end_date_val = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                except ValueError:
                    end_date_val = None

            if end_date_val and end_date_val < start_date_val:
                # Swap if user picked an inverted range
                start_date_val, end_date_val = end_date_val, start_date_val

            # If only start date is set, we still treat it as a 1-day range.
            range_end = end_date_val or start_date_val

            try:
                tours = tours.exclude(
                    reservations__status__in=['pending', 'booked'],
                    reservations__start_date__lte=range_end,
                    reservations__end_date__gte=start_date_val,
                )
            except (OperationalError, ProgrammingError):
                tours = Tour.objects.none()
        except ValueError:
            pass

    try:
        tours = tours.distinct()[:6]
    except (OperationalError, ProgrammingError):
        tours = []

    for tour in tours:
        # ✅ always compute promo
        tour.promo_price = None
        if tour.is_promotion and tour.discount_percent > 0:
            discount = (Decimal(100) - Decimal(tour.discount_percent)) / Decimal(100)
            tour.promo_price = (Decimal(tour.price_per_night) * discount).quantize(Decimal("0.01"))

        # ✅ reservation status (only if logged)
        tour.user_reservation = None
        if request.user.is_authenticated:
            try:
                tour.user_reservation = Reservation.objects.filter(
                    user=request.user,
                    tour=tour
                ).exclude(status__in=["rejected", "cancelled"]).order_by("-created_at").first()
            except (OperationalError, ProgrammingError):
                tour.user_reservation = None

    # Load country-specific content
    try:
        country_content = CountryContent.objects.get(country=country)
        hero_title = country_content.hero_title
        hero_subtitle = country_content.hero_subtitle
        hero_image = country_content.hero_image.url if country_content.hero_image else None
    except (CountryContent.DoesNotExist, OperationalError, ProgrammingError):
        hero_title = "Discover Morocco" if country == 'morocco' else "Discover Ireland"
        hero_subtitle = ""
        hero_image = None

    return render(request, "home.html", {
        "tours": tours,
        "hero_title": hero_title,
        "hero_subtitle": hero_subtitle,
        "hero_image": hero_image,
        "country": country
        ,
        "search_q": q,
        "search_start_date": start_date_str,
        "search_end_date": end_date_str,
    })


@csrf_exempt
def ai_chat_history(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    session_key = request.session.session_key or ''
    try:
        if request.user.is_authenticated:
            messages_qs = ChatMessage.objects.filter(user=request.user).order_by('created_at')
        else:
            messages_qs = ChatMessage.objects.filter(session_key=session_key).order_by('created_at')

        history = [{'role': m.role, 'message': m.message, 'created_at': m.created_at.isoformat()} for m in messages_qs]
        return JsonResponse({'history': history})
    except (OperationalError, ProgrammingError):
        return JsonResponse({'history': []})
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
        "activities_list": [activity.strip() for activity in tour.activities.split(',')] if tour.activities else [],
    })


@csrf_exempt
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
def ai_chat(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)

    message = payload.get('message', '').strip()
    if not message:
        return JsonResponse({'error': 'Message cannot be empty.'}, status=400)

    country = get_country_from_site(request) or 'morocco'
    session_key = request.session.session_key or ''

    if request.user.is_authenticated:
        ChatMessage.objects.create(user=request.user, role='user', message=message)
    else:
        ChatMessage.objects.create(session_key=session_key, role='user', message=message)

    bot_reply = ''
    action = {}

    try:
        if request.user.is_authenticated:
            history = ChatMessage.objects.filter(user=request.user).order_by('created_at')[:20]
        else:
            history = ChatMessage.objects.filter(session_key=session_key).order_by('created_at')[:20]

        context = f"You are a helpful travel assistant for {country.title()} tours. "
        context += f"Available tours: {', '.join([t.title for t in Tour.objects.filter(country=country)[:5]])}. "

        info_docs = Information.objects.filter(country=country)
        relevant_info = ''
        for doc in info_docs:
            if any(word in message.lower() for word in (doc.title + ' ' + doc.content).lower().split()):
                relevant_info += f"{doc.title}: {doc.content[:500]} "

        if relevant_info:
            context += f"Relevant information: {relevant_info}"

        if settings.OPENAI_API_KEY:
            try:
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                messages = [
                    {"role": "system", "content": context + " Respond helpfully and conversationally. If user wants to book a tour, navigate to booking page and prefill dates/persons. Use markers like [NAVIGATE: /tour/1] [PREFILL: start_date=2024-04-15,end_date=2024-04-20,persons=2] in your response when appropriate. Keep responses engaging and helpful."}
                ]
                for msg in history:
                    messages.append({"role": msg.role, "content": msg.message})

                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    max_tokens=300,
                    temperature=0.7
                )

                bot_reply = response.choices[0].message.content.strip()
                action, bot_reply = parse_actions_from_response(bot_reply, country)

            except Exception:
                logging.exception('[ai_chat] OpenAI exception')
                bot_reply = ''
                action = {}

        if not bot_reply and settings.HF_API_TOKEN and InferenceClient:
            try:
                hf_client = InferenceClient(token=settings.HF_API_TOKEN)
                hf_prompt = context + "\nUser: " + message + "\nAssistant:"
                hf_result = hf_client.text_generation(
                    model="mistralai/mistral-7b-instruct",
                    inputs=hf_prompt,
                    max_new_tokens=250,
                    temperature=0.7
                )

                if isinstance(hf_result, dict):
                    bot_reply = hf_result.get('generated_text', '').strip()
                elif isinstance(hf_result, list) and hf_result:
                    bot_reply = hf_result[0].get('generated_text', '').strip() if isinstance(hf_result[0], dict) else str(hf_result[0])
                else:
                    bot_reply = str(hf_result).strip()

                action, bot_reply = parse_actions_from_response(bot_reply, country)

            except Exception:
                logging.exception('[ai_chat] HF exception')
                bot_reply = ''
                action = {}

        if not bot_reply:
            bot_reply = generate_fallback_reply(message, country)
            action = parse_actions(message, country)

    except Exception:
        logging.exception('[ai_chat] Unhandled exception')
        bot_reply = 'Désolé, une erreur est survenue. Veuillez réessayer dans quelques instants.'
        action = parse_actions(message, country)

    if not action:
        action = parse_actions(message, country)

    if request.user.is_authenticated:
        ChatMessage.objects.create(user=request.user, role='assistant', message=bot_reply)
    else:
        ChatMessage.objects.create(session_key=session_key, role='assistant', message=bot_reply)

    result = {'reply': bot_reply}
    result.update(action)
    return JsonResponse(result)


def generate_fallback_reply(message, country):
    msg_lower = message.lower()
    if 'price' in msg_lower or 'cost' in msg_lower:
        return 'Our price starts at 2000$ per night.'
    elif 'book' in msg_lower or 'reserve' in msg_lower or 'booking' in msg_lower:
        return 'Say "book Morocco 15 April 20 April 2 people" and I prefill the form for you.'
    else:
        return f'Hello! I am your virtual assistant for {country.title()} tours. How can I help you plan your trip?'


def parse_actions_from_response(response, country):
    action = {}
    import re

    if response is None:
        return action, ''

    try:
        response_text = str(response)

        # Parse [NAVIGATE: url]
        navigate_match = re.search(r'\[NAVIGATE:\s*([^]]+)\]', response_text)
        if navigate_match:
            url = navigate_match.group(1).strip()
            action['navigate'] = url

        # Parse [PREFILL: key1=value1,key2=value2]
        prefill_match = re.search(r'\[PREFILL:\s*([^]]+)\]', response_text)
        if prefill_match:
            prefill_str = prefill_match.group(1).strip()
            prefill = {}
            for pair in prefill_str.split(','):
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    prefill[key.strip()] = value.strip()
            if prefill:
                action['prefill'] = prefill

        # Remove markers from response
        response_text = re.sub(r'\[NAVIGATE:[^]]+\]', '', response_text)
        response_text = re.sub(r'\[PREFILL:[^]]+\]', '', response_text)

        return action, response_text.strip()

    except Exception:
        logging.exception('[parse_actions_from_response] Unexpected response format')
        return action, str(response).strip() if response else ''


def parse_actions(message, country):
    action = {}
    msg_lower = message.lower()

    if 'home' in msg_lower or 'accueil' in msg_lower:
        action['navigate'] = reverse('home')
    elif 'about' in msg_lower or 'à propos' in msg_lower:
        action['navigate'] = reverse('about')
    elif 'blog' in msg_lower:
        action['navigate'] = reverse('blog_list')

    # Parse dates and persons for booking
    import re
    months = {
        'january': 1, 'janvier': 1, 'february': 2, 'feb': 2, 'march': 3, 'mars': 3,
        'april': 4, 'avril': 4, 'may': 5, 'mai': 5, 'june': 6, 'juin': 6,
        'july': 7, 'juillet': 7, 'august': 8, 'août': 8, 'september': 9, 'septembre': 9,
        'october': 10, 'octobre': 10, 'november': 11, 'novembre': 11, 'december': 12, 'décembre': 12
    }

    start_date = None
    end_date = None
    persons = None

    date_match2 = re.search(r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?(janvier|jan|february|feb|march|mars|april|avr|may|mai|june|juin|july|juil|august|aout|september|sept|october|oct|november|nov|december|dec)\s*to\s*(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?(janvier|jan|february|feb|march|mars|april|avr|may|mai|june|juin|july|juil|august|aout|september|sept|october|oct|november|nov|december|dec)', msg_lower)
    if date_match2:
        try:
            groups = date_match2.groups()
            if len(groups) >= 4:
                sday, smonth, eday, emonth = groups[:4]
                year = date.today().year
                start_date = date(year, months.get(smonth, 4), int(sday))
                end_date = date(year, months.get(emonth, 4), int(eday))
        except (ValueError, TypeError):
            pass

    persons_match = re.search(r'(\d+)\s*(persons|personnes|people|person)', msg_lower)
    if persons_match:
        persons = int(persons_match.group(1))

    if start_date and end_date and persons and ('reserve' in msg_lower or 'book' in msg_lower or 'booking' in msg_lower):
        try:
            # Support explicit city-based requests (e.g. "rabat")
            if 'rabat' in msg_lower:
                target_tour = Tour.objects.filter(
                    country=country,
                    destination__name__icontains='rabat'
                ).first()
            else:
                target_tour = Tour.objects.filter(country=country).first()

            if not target_tour and 'rabat' in msg_lower:
                # fallback to any tour if exact destination not found
                target_tour = Tour.objects.filter(country=country).first()

            if target_tour:
                action['navigate'] = reverse('tour_detail', args=[target_tour.id])
                action['prefill'] = {
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d'),
                    'persons': persons,
                }
        except Exception as e:
            logging.exception('[parse_actions] Failed to build output')
            return {}

    return action


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
    return redirect(reverse('home') + '#about-us')


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


def reservations(request):
    q = request.GET.get('q', '').strip()
    start_date_str = (request.GET.get('start_date') or request.GET.get('date') or '').strip()
    end_date_str = (request.GET.get('end_date') or '').strip()

    country = get_country_from_site(request)

    try:
        tours = Tour.objects.filter(country=country)
    except (OperationalError, ProgrammingError):
        tours = Tour.objects.none()

    if q:
        try:
            tours = tours.filter(
                Q(destination__name__icontains=q) |
                Q(title__icontains=q)
            )
        except (OperationalError, ProgrammingError):
            tours = Tour.objects.none()

    if start_date_str:
        try:
            start_date_val = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date_val = None
            if end_date_str:
                try:
                    end_date_val = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                except ValueError:
                    end_date_val = None

            if end_date_val and end_date_val < start_date_val:
                start_date_val, end_date_val = end_date_val, start_date_val

            range_end = end_date_val or start_date_val

            try:
                tours = tours.exclude(
                    reservations__status__in=['pending', 'booked'],
                    reservations__start_date__lte=range_end,
                    reservations__end_date__gte=start_date_val,
                )
            except (OperationalError, ProgrammingError):
                tours = Tour.objects.none()
        except ValueError:
            pass

    try:
        tours = tours.distinct().order_by('destination__name', 'title')
    except (OperationalError, ProgrammingError):
        tours = []

    # Compute promo prices for display
    for tour in tours:
        tour.promo_price = None
        if getattr(tour, 'is_promotion', False) and getattr(tour, 'discount_percent', 0) > 0:
            discount = (Decimal(100) - Decimal(tour.discount_percent)) / Decimal(100)
            tour.promo_price = (Decimal(tour.price_per_night) * discount).quantize(Decimal("0.01"))

    return render(request, 'reservations.html', {
        'tours': tours,
        'country': country,
        'search_q': q,
        'search_start_date': start_date_str,
        'search_end_date': end_date_str,
    })


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)

        if form.is_valid():
            full_name = request.POST.get('full_name', '').strip()
            if not full_name:
                form.add_error('username', 'Full name is required')
            else:
                name_parts = full_name.split(None, 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ''

                selected_country = request.POST.get('country', '').strip().lower()
                if selected_country not in ['morocco', 'ireland']:
                    selected_country = get_country_from_site(request)

                user = form.save(commit=False)
                user.email = request.POST.get('email')
                user.first_name = first_name
                user.last_name = last_name
                user.save()

                UserProfile.objects.create(
                    user=user,
                    phone=request.POST.get('phone'),
                    country=selected_country,
                    postal_code=request.POST.get('postal_code')
                )

                messages.success(request, "✅ Registration successful! Please log in.")
                return redirect('login')
    else:
        form = UserCreationForm()

    return render(request, 'register.html', {'form': form, 'country': get_country_from_site(request)})


def custom_logout(request):
    logout(request)
    return render(request, 'logged_out.html')
