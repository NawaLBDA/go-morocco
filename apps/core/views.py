import json
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging
import uuid

# A per-process identifier that changes on every server restart.
CHAT_BOOT_ID = uuid.uuid4().hex


def _ensure_session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key or ''


def _reset_chat_if_server_restarted(request, session_key: str) -> None:
    """Clears chat history for this browser session when the server restarts."""
    if not session_key:
        return
    if request.session.get('chat_boot_id') != CHAT_BOOT_ID:
        ChatMessage.objects.filter(session_key=session_key).delete()
        request.session['chat_boot_id'] = CHAT_BOOT_ID
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


def _normalize_country(country: str) -> str:
    country = (country or '').strip().lower()
    return country if country in {'morocco', 'ireland'} else 'morocco'


def _country_label(country: str) -> str:
    return 'Morocco' if country == 'morocco' else 'Ireland'


def _build_booking_rules_context() -> str:
    return (
        "Booking rules: maximum stay is 11 nights. "
        "Single-group rule: if there is any pending/booked reservation in a country, other tours in that country are unavailable for overlapping dates. "
        "Buffer rule: 3-day buffer after each reservation end date."
    )


def _detect_language(message: str) -> str:
    """Very small heuristic: returns 'fr' or 'en'."""
    msg = (message or '').lower()
    if any(ch in msg for ch in ['é', 'è', 'à', 'ù', 'ô', 'ç']):
        return 'fr'
    fr_markers = [
        'bonjour', 'salut', 'svp', "s'il", 'réserver', 'reserver', 'réservation',
        'du ', ' au ', 'pour ', 'personnes', 'nuit', 'nuits', 'disponible', 'disponibles'
    ]
    if any(m in msg for m in fr_markers):
        return 'fr'
    return 'en'


def _extract_booking_details(message: str):
    """Extract (start_date, end_date, persons, destination_hint) from FR/EN/ISO-ish messages."""
    msg_lower = (message or '').lower()
    import re

    months = {
        'january': 1, 'jan': 1, 'janvier': 1,
        'february': 2, 'feb': 2, 'février': 2, 'fevrier': 2,
        'march': 3, 'mar': 3, 'mars': 3,
        'april': 4, 'apr': 4, 'avril': 4,
        'may': 5, 'mai': 5,
        'june': 6, 'jun': 6, 'juin': 6,
        'july': 7, 'jul': 7, 'juillet': 7,
        'august': 8, 'aug': 8, 'août': 8, 'aout': 8,
        'september': 9, 'sep': 9, 'sept': 9, 'septembre': 9,
        'october': 10, 'oct': 10, 'octobre': 10,
        'november': 11, 'nov': 11, 'novembre': 11,
        'december': 12, 'dec': 12, 'décembre': 12, 'decembre': 12,
    }

    def parse_month(m: str) -> int | None:
        if not m:
            return None
        m = m.strip().lower()
        return months.get(m)

    start_date = None
    end_date = None

    # ISO range: 2026-04-20 to 2026-04-25
    iso = re.search(r'(\d{4}-\d{2}-\d{2})\s*(?:to|au|\-|–|—)\s*(\d{4}-\d{2}-\d{2})', msg_lower)
    if iso:
        try:
            start_date = datetime.strptime(iso.group(1), '%Y-%m-%d').date()
            end_date = datetime.strptime(iso.group(2), '%Y-%m-%d').date()
        except ValueError:
            start_date = end_date = None

    # English: from 20 April to 25 April
    if not (start_date and end_date):
        m = re.search(
            r'(?:from\s*)?(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?'
            r'(january|jan|janvier|february|feb|février|fevrier|march|mar|mars|april|apr|avril|may|mai|june|jun|juin|july|jul|juillet|august|aug|août|aout|september|sep|sept|septembre|october|oct|octobre|november|nov|novembre|december|dec|décembre|decembre)'
            r'\s*(?:to|until|\-|–|—)\s*(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?'
            r'(january|jan|janvier|february|feb|février|fevrier|march|mar|mars|april|apr|avril|may|mai|june|jun|juin|july|jul|juillet|august|aug|août|aout|september|sep|sept|septembre|october|oct|octobre|november|nov|novembre|december|dec|décembre|decembre)'
            r'(?:\s*(\d{4}))?',
            msg_lower,
        )
        if m:
            try:
                sday, smonth, eday, emonth, year = m.groups()
                y = int(year) if year else date.today().year
                start_date = date(y, parse_month(smonth) or 1, int(sday))
                end_date = date(y, parse_month(emonth) or 1, int(eday))
            except Exception:
                start_date = end_date = None

    # French: du 20 avril au 25 avril
    if not (start_date and end_date):
        m = re.search(
            r'(?:du|de)\s*(\d{1,2})\s*'
            r'(january|jan|janvier|february|feb|février|fevrier|march|mar|mars|april|apr|avril|may|mai|june|jun|juin|july|jul|juillet|august|aug|août|aout|september|sep|sept|septembre|october|oct|octobre|november|nov|novembre|december|dec|décembre|decembre)'
            r'\s*(?:au|à|a)\s*(\d{1,2})\s*'
            r'(january|jan|janvier|february|feb|février|fevrier|march|mar|mars|april|apr|avril|may|mai|june|jun|juin|july|jul|juillet|august|aug|août|aout|september|sep|sept|septembre|october|oct|octobre|november|nov|novembre|december|dec|décembre|decembre)?'
            r'(?:\s*(\d{4}))?',
            msg_lower,
        )
        if m:
            try:
                sday, smonth, eday, emonth, year = m.groups()
                y = int(year) if year else date.today().year
                start_date = date(y, parse_month(smonth) or 1, int(sday))
                # If end month omitted, assume same month
                em = parse_month(emonth) if emonth else (parse_month(smonth) or 1)
                end_date = date(y, em, int(eday))
            except Exception:
                start_date = end_date = None

    if start_date and end_date and end_date < start_date:
        start_date, end_date = end_date, start_date

    persons = None
    pm = re.search(r'(\d+)\s*(persons|personnes|people|person)', msg_lower)
    if pm:
        try:
            persons = int(pm.group(1))
        except ValueError:
            persons = None

    destination_hint = None
    # light hinting for common cities
    for city in ['rabat', 'marrakech', 'fes', 'fez', 'casablanca', 'tangier', 'dublin', 'galway', 'cork', 'belfast']:
        if city in msg_lower:
            destination_hint = city
            break

    return start_date, end_date, persons, destination_hint


def _get_country_blocked_ranges(country: str, buffer_days: int = 3):
    """Returns list of blocked date ranges (start, end_inclusive) for a country."""
    country = _normalize_country(country)
    active_statuses = ['pending', 'booked']
    try:
        reservations = Reservation.objects.filter(
            tour__country=country,
            status__in=active_statuses,
        ).order_by('start_date')
    except (OperationalError, ProgrammingError):
        return []

    ranges = []
    for r in reservations:
        try:
            ranges.append((r.start_date, r.end_date + timedelta(days=buffer_days)))
        except Exception:
            continue

    # merge overlaps
    merged = []
    for start, end in sorted(ranges, key=lambda x: x[0]):
        if not merged:
            merged.append([start, end])
            continue
        last = merged[-1]
        if start <= last[1] + timedelta(days=1):
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def _is_range_available(country: str, start_date: date, end_date: date, buffer_days: int = 3) -> bool:
    if not start_date or not end_date:
        return False
    country = _normalize_country(country)
    blocked = _get_country_blocked_ranges(country, buffer_days=buffer_days)
    # booking overlap check with buffer: block window_start .. end_date
    window_start = start_date - timedelta(days=buffer_days)
    for s, e in blocked:
        if s <= end_date and e >= window_start:
            return False
    return True


def _suggest_available_ranges(country: str, nights: int = 5, horizon_days: int = 120, limit: int = 4, buffer_days: int = 3):
    """Suggest next available continuous date ranges for a given stay length."""
    country = _normalize_country(country)
    nights = max(1, min(int(nights), 11))
    today = date.today()

    suggestions = []
    d = today
    end_horizon = today + timedelta(days=horizon_days)

    while d <= end_horizon and len(suggestions) < limit:
        start = d
        end = d + timedelta(days=nights)
        # end_date is checkout date; nights = (end - start).days
        if end > end_horizon:
            break
        if _is_range_available(country, start, end, buffer_days=buffer_days):
            suggestions.append((start, end))
            d = start + timedelta(days=7)
        else:
            d = d + timedelta(days=1)
    return suggestions


def _score_doc_relevance(message: str, doc_title: str, doc_content: str) -> int:
    msg = (message or '').lower()
    if not msg:
        return 0
    text = f"{doc_title or ''} {doc_content or ''}".lower()
    # Simple keyword overlap scoring (fast + predictable)
    score = 0
    for token in set([t for t in msg.replace('\n', ' ').split(' ') if len(t) >= 4]):
        if token in text:
            score += 1
    return score


def _build_country_catalog_context(country: str, user_message: str) -> str:
    """Build a compact, factual context from the DB for the current country."""
    country = _normalize_country(country)

    try:
        tours_qs = (
            Tour.objects.filter(country=country)
            .select_related('destination')
            .order_by('id')
        )
        tours = list(tours_qs[:12])
    except (OperationalError, ProgrammingError):
        tours = []

    destinations = []
    try:
        destinations = list(
            Destination.objects.filter(tours__country=country)
            .distinct()
            .order_by('name')[:12]
        )
    except (OperationalError, ProgrammingError):
        destinations = []

    catalog_lines = []
    if destinations:
        catalog_lines.append(
            "Destinations: " + ", ".join([d.name for d in destinations])
        )
    if tours:
        for t in tours:
            dest_name = getattr(t.destination, 'name', '') or ''
            promo = f" (promo -{t.discount_percent}%)" if getattr(t, 'is_promotion', False) and getattr(t, 'discount_percent', 0) else ""
            line = f"- Tour #{t.id}: {t.title} — {dest_name} — {t.price_per_night} per night{promo}."
            if t.transport:
                line += f" Transport: {t.transport}."
            if t.hotel:
                line += f" Hotel: {t.hotel}."
            if t.activities:
                activities = [a.strip() for a in t.activities.replace('\n', ',').split(',') if a.strip()]
                if activities:
                    line += " Activities: " + ", ".join(activities[:8]) + ("." if len(activities) <= 8 else ", …")
            catalog_lines.append(line)

    info_lines = []
    try:
        docs = list(Information.objects.filter(country=country))
        ranked = sorted(
            ((
                _score_doc_relevance(user_message, d.title, d.content),
                d.title,
                (d.content or '')
            ) for d in docs),
            key=lambda x: x[0],
            reverse=True,
        )
        for score, title, content in ranked[:3]:
            if score <= 0:
                continue
            snippet = content.strip().replace('\n', ' ')
            info_lines.append(f"- {title}: {snippet[:400]}")
    except (OperationalError, ProgrammingError):
        info_lines = []

    parts = []
    if catalog_lines:
        parts.append("Catalog:\n" + "\n".join(catalog_lines))
    if info_lines:
        parts.append("Extra info (from site admin):\n" + "\n".join(info_lines))
    parts.append(_build_booking_rules_context())

    return "\n\n".join(parts).strip()


def _pick_tour_for_booking(country: str, destination_hint: str | None = None):
    country = _normalize_country(country)
    try:
        qs = Tour.objects.filter(country=country)
        if destination_hint:
            tour = qs.filter(
                Q(destination__name__icontains=destination_hint) |
                Q(title__icontains=destination_hint)
            ).select_related('destination').first()
            if tour:
                return tour
        return qs.select_related('destination').first()
    except (OperationalError, ProgrammingError):
        return None


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
    # Single-group rule: if the group is booked for ANY tour in this country,
    # then NO other tour is available for those dates.
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

            buffer_days = 3
            active_statuses = ['pending', 'booked']
            window_start = start_date_val - timedelta(days=buffer_days)

            try:
                has_conflict = Reservation.objects.filter(
                    tour__country=country,
                    status__in=active_statuses,
                    start_date__lte=range_end,
                    end_date__gte=window_start,
                ).exists()
                if has_conflict:
                    tours = Tour.objects.none()
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

    session_key = _ensure_session_key(request)
    try:
        _reset_chat_if_server_restarted(request, session_key)
        messages_qs = ChatMessage.objects.filter(session_key=session_key).order_by('created_at')

        history = []
        for m in messages_qs:
            role = m.role
            # Backward compatibility: older rows used role='assistant'
            if role == 'assistant':
                role = 'bot'
            history.append({'role': role, 'message': m.message, 'created_at': m.created_at.isoformat()})
        return JsonResponse({'history': history})
    except (OperationalError, ProgrammingError):
        return JsonResponse({'history': []})
def tour_detail(request, tour_id):
    country = get_country_from_site(request)
    tour = get_object_or_404(Tour, id=tour_id, country=country)

    reservation = None
    if request.user.is_authenticated:
        reservation = Reservation.objects.filter(
            user=request.user,
            tour=tour
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
    )
    if request.user.is_authenticated:
        active_reservations = active_reservations.exclude(user=request.user)

    disabled_ranges = [
        {
            "from": r.start_date.isoformat(),
            "to": (r.end_date + timedelta(days=buffer_days)).isoformat(),
        }
        for r in active_reservations.order_by('start_date')
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
        "activities_list": [a.strip() for a in (tour.activities or '').replace('\n', ',').split(',') if a.strip()],
        "booking_max_nights": 11,
        "booking_buffer_days": buffer_days,
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

    country = _normalize_country(get_country_from_site(request) or 'morocco')
    session_key = _ensure_session_key(request)
    _reset_chat_if_server_restarted(request, session_key)

    ChatMessage.objects.create(session_key=session_key, role='user', message=message)

    bot_reply = ''
    action = {}
    lang = _detect_language(message)

    # Booking intelligence (works even without OpenAI credits)
    booking_intent = any(k in message.lower() for k in ['book', 'booking', 'reserve', 'reservation', 'réserver', 'reserver'])
    start_date_req, end_date_req, persons_req, destination_hint = _extract_booking_details(message)

    if booking_intent:
        # If dates provided, validate rules + availability first.
        if start_date_req and end_date_req:
            requested_nights = max(0, (end_date_req - start_date_req).days)
            if requested_nights > 11:
                bot_reply = (
                    "Désolé, la durée maximale est de 11 nuits. Peux-tu choisir une période plus courte ?"
                    if lang == 'fr' else
                    "Sorry — the maximum stay is 11 nights. Can you pick a shorter date range?"
                )
            elif not _is_range_available(country, start_date_req, end_date_req, buffer_days=3):
                suggestions = _suggest_available_ranges(country, nights=min(max(requested_nights, 3), 11), limit=4)
                if lang == 'fr':
                    if suggestions:
                        sug_txt = " ; ".join([f"{s.strftime('%d %b %Y')} → {e.strftime('%d %b %Y')}" for s, e in suggestions])
                        bot_reply = (
                            "Ces dates semblent déjà bloquées sur ce site. Voici des alternatives disponibles : "
                            + sug_txt
                            + ". Tu préfères laquelle ?"
                        )
                    else:
                        bot_reply = "Ces dates semblent déjà bloquées sur ce site. Donne-moi une autre période (et le nombre de personnes) et je te propose des options."
                else:
                    if suggestions:
                        sug_txt = "; ".join([f"{s.strftime('%d %b %Y')} → {e.strftime('%d %b %Y')}" for s, e in suggestions])
                        bot_reply = (
                            "Those dates look unavailable on this site. Here are available alternatives: "
                            + sug_txt
                            + ". Which one do you prefer?"
                        )
                    else:
                        bot_reply = "Those dates look unavailable on this site. Share another date range (+ number of people) and I’ll suggest options."
            else:
                # Dates are available. If persons is given, we can navigate/prefill.
                if not persons_req:
                    bot_reply = (
                        "Parfait — pour combien de personnes ?"
                        if lang == 'fr' else
                        "Great — for how many people?"
                    )
                else:
                    tour = _pick_tour_for_booking(country, destination_hint)
                    if tour:
                        action['navigate'] = reverse('tour_detail', args=[tour.id])
                        action['prefill'] = {
                            'start_date': start_date_req.strftime('%Y-%m-%d'),
                            'end_date': end_date_req.strftime('%Y-%m-%d'),
                            'persons': persons_req,
                        }
                        if lang == 'fr':
                            bot_reply = f"Super — je t’ouvre la réservation pour {tour.title}."
                        else:
                            bot_reply = f"Great — I’m opening the booking for {tour.title}."
        else:
            # No dates provided: propose real free windows.
            suggestions = _suggest_available_ranges(country, nights=5, limit=4)
            if lang == 'fr':
                if suggestions:
                    sug_txt = " ; ".join([f"{s.strftime('%d %b %Y')} → {e.strftime('%d %b %Y')}" for s, e in suggestions])
                    bot_reply = (
                        "Bien sûr. Donne-moi tes dates exactes et le nombre de personnes (et la ville si tu veux). "
                        "Exemples de périodes disponibles (5 nuits) : " + sug_txt + "."
                    )
                else:
                    bot_reply = "Bien sûr. Donne-moi tes dates exactes et le nombre de personnes, et je vérifie la disponibilité."
            else:
                if suggestions:
                    sug_txt = "; ".join([f"{s.strftime('%d %b %Y')} → {e.strftime('%d %b %Y')}" for s, e in suggestions])
                    bot_reply = (
                        "Sure — tell me your dates and number of people (and the destination if you want). "
                        "Examples of available windows (5 nights): " + sug_txt + "."
                    )
                else:
                    bot_reply = "Sure — tell me your dates and number of people and I’ll check availability."

    try:
        history = ChatMessage.objects.filter(session_key=session_key).order_by('created_at')[:20]

        country_label = _country_label(country)
        site_context = _build_country_catalog_context(country, message)

        system_prompt = (
            f"You are the official virtual assistant for the {country_label} travel website only. "
            f"You must ONLY answer using information relevant to {country_label}. "
            "If the user asks about another country/site, politely refuse and redirect them to questions about the current site. "
            "Respond in the same language as the user (French or English). "
            "Be conversational, concise, and helpful. Ask 1 short follow-up question when needed. "
            "Do NOT tell the user to type a specific magic command like 'book ...'. Instead, understand natural language and ask for missing info. "
            "If the user wants to book, select the most relevant tour from the catalog and include: "
            "[NAVIGATE: /tour/<id>/] and optionally [PREFILL: start_date=YYYY-MM-DD,end_date=YYYY-MM-DD,persons=N]. "
            "Never invent tours, destinations, or prices; use the provided catalog/context.\n\n"
            f"{site_context}"
        )

        if settings.OPENAI_API_KEY and not bot_reply:
            try:
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                messages = [{"role": "system", "content": system_prompt}]
                for msg in history:
                    role = msg.role
                    if role in {'bot', 'assistant'}:
                        role = 'assistant'
                    elif role != 'user':
                        role = 'user'
                    messages.append({"role": role, "content": msg.message})

                response = client.chat.completions.create(
                    model=getattr(settings, 'OPENAI_MODEL', None) or "gpt-4o",
                    messages=messages,
                    max_tokens=300,
                    temperature=0.7
                )

                bot_reply = response.choices[0].message.content.strip()
                action, bot_reply = parse_actions_from_response(bot_reply, country)

            except Exception:
                logging.exception('[ai_chat] OpenAI exception')
                # Keep any already computed deterministic reply (availability checks, etc).
                bot_reply = bot_reply or ''
                action = action or {}

        if not bot_reply and settings.HF_API_TOKEN and InferenceClient:
            try:
                hf_client = InferenceClient(token=settings.HF_API_TOKEN)
                hf_prompt = system_prompt + "\nUser: " + message + "\nAssistant:"
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

    ChatMessage.objects.create(session_key=session_key, role='bot', message=bot_reply)

    result = {'reply': bot_reply}
    result.update(action)
    return JsonResponse(result)


def generate_fallback_reply(message, country):
    country = _normalize_country(country)
    country_label = _country_label(country)
    msg_lower = message.lower()
    lang = _detect_language(message)

    if any(w in msg_lower for w in ['price', 'cost', 'prix', 'tarif']):
        if lang == 'fr':
            return f"Les prix dépendent du tour sur le site {country_label}. Dis-moi la destination, les dates et le nombre de personnes, et je te propose la meilleure option."
        return f"Prices vary by tour on the {country_label} site. Tell me the destination, dates, and number of people, and I’ll suggest the best option."

    if any(k in msg_lower for k in ['book', 'reserve', 'booking', 'réserver', 'reserver', 'réservation', 'reservation']):
        start_date_req, end_date_req, persons_req, destination_hint = _extract_booking_details(message)
        if start_date_req and end_date_req:
            if lang == 'fr':
                return "Parfait. Je vérifie la disponibilité pour ces dates. Si tu confirmes le nombre de personnes, je peux pré-remplir la réservation."
            return "Great — I’ll check availability for those dates. If you confirm the number of people, I can prefill the booking."

        suggestions = _suggest_available_ranges(country, nights=5, limit=4)
        if lang == 'fr':
            if suggestions:
                sug_txt = " ; ".join([f"{s.strftime('%d %b %Y')} → {e.strftime('%d %b %Y')}" for s, e in suggestions])
                return (
                    "Bien sûr. Donne-moi tes dates exactes et le nombre de personnes. "
                    "Exemples de périodes disponibles (5 nuits) : " + sug_txt + "."
                )
            return "Bien sûr. Donne-moi tes dates exactes et le nombre de personnes, et je vérifie la disponibilité."

        if suggestions:
            sug_txt = "; ".join([f"{s.strftime('%d %b %Y')} → {e.strftime('%d %b %Y')}" for s, e in suggestions])
            return (
                "Sure — tell me your exact dates and number of people. "
                "Examples of available windows (5 nights): " + sug_txt + "."
            )
        return "Sure — tell me your exact dates and number of people and I’ll check availability."

    if lang == 'fr':
        return f"Bonjour ! Je suis votre assistant virtuel pour {country_label}. Que souhaitez-vous organiser (destination, dates, budget) ?"
    return f"Hello! I’m your virtual assistant for {country_label}. What would you like to plan (destination, dates, budget)?"


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

    # Parse dates/persons from natural language and only prefill when the range is actually available.
    booking_intent = any(k in msg_lower for k in ['book', 'booking', 'reserve', 'reservation', 'réserver', 'reserver'])
    if booking_intent:
        start_date, end_date, persons, destination_hint = _extract_booking_details(message)
        if start_date and end_date and persons:
            requested_nights = max(0, (end_date - start_date).days)
            if requested_nights <= 11 and _is_range_available(country, start_date, end_date, buffer_days=3):
                target_tour = _pick_tour_for_booking(country, destination_hint)
                if target_tour:
                    action['navigate'] = reverse('tour_detail', args=[target_tour.id])
                    action['prefill'] = {
                        'start_date': start_date.strftime('%Y-%m-%d'),
                        'end_date': end_date.strftime('%Y-%m-%d'),
                        'persons': persons,
                    }

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
    country = get_country_from_site(request)
    posts = BlogPost.objects.filter(country=country).order_by('-created_at')
    return render(request, 'blog_list.html', {'posts': posts})


def blog_detail(request, slug):
    country = get_country_from_site(request)
    post = get_object_or_404(BlogPost, slug=slug, country=country)
    comments = post.comments.all()

    if request.method == 'POST' and request.user.is_authenticated:
        content = request.POST.get('content')
        if content:
            BlogComment.objects.create(post=post, user=request.user, content=content)
            return redirect('blog_detail', slug=slug)

    return render(request, 'blog_detail.html', {'post': post, 'comments': comments})


def about(request):
    country = get_country_from_site(request)
    return render(request, 'about.html', {'country': country})


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

            buffer_days = 3
            active_statuses = ['pending', 'booked']
            window_start = start_date_val - timedelta(days=buffer_days)

            try:
                has_conflict = Reservation.objects.filter(
                    tour__country=country,
                    status__in=active_statuses,
                    start_date__lte=range_end,
                    end_date__gte=window_start,
                ).exists()
                if has_conflict:
                    tours = Tour.objects.none()
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
