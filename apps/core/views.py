import json
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging
import re
import uuid

import requests
from urllib.parse import quote

# A per-process identifier that changes on every server restart.
CHAT_BOOT_ID = uuid.uuid4().hex


_REDACTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    # OpenAI keys (old + project keys)
    (re.compile(r"\bsk-(?:proj-)?[-_A-Za-z0-9]{10,}\b"), "sk-[REDACTED]"),
    # Hugging Face tokens
    (re.compile(r"\bhf_[-_A-Za-z0-9]{10,}\b"), "hf_[REDACTED]"),
    # Generic bearer tokens
    (re.compile(r"(?i)\b(bearer)\s+[-_A-Za-z0-9\.=]{10,}\b"), r"\1 [REDACTED]"),
]


def _redact_secrets(text: str) -> str:
    if text is None:
        return ''
    s = str(text)
    for pattern, replacement in _REDACTION_PATTERNS:
        s = pattern.sub(replacement, s)
    return s


def _is_greeting(message: str) -> bool:
    words = re.findall(r"[A-Za-zÀ-ÿ']+", (message or '').lower())
    if not words:
        return False
    if len(words) > 3:
        return False
    greetings = {
        'hi', 'hello', 'hey', 'yo',
        'salut', 'bonjour', 'bonsoir', 'coucou',
        'salam', 'salamalekom', 'salamalikum', 'as-salam',
    }
    return words[0] in greetings


def _is_smalltalk(message: str) -> bool:
    msg = (message or '').strip().lower()
    if not msg:
        return False
    # Keep it conservative: only catch clear small-talk.
    patterns = [
        'how are you', "how're you", 'hru',
        'comment ca va', 'comment ça va', 'ca va', 'ça va',
        'cv',
    ]
    return any(p in msg for p in patterns)


def _is_affirmative(message: str) -> bool:
    msg = (message or '').strip().lower()
    if not msg:
        return False
    # Keep it strict: only clear affirmations.
    patterns = [
        r"^y(?:es)?\b",
        r"^yep\b",
        r"^yeah\b",
        r"^ok(?:ay)?\b",
        r"^okey\b",
        r"^oui\b",
        r"^d['’]?accord\b",
        r"^bien\b",
        r"^vas[-\s]?y\b",
        r"^go\b",
        r"^proceed\b",
    ]
    return any(re.search(p, msg) for p in patterns)


def _smalltalk_reply(country: str, lang: str) -> str:
    country_label = _country_label(country)
    if lang == 'fr':
        return (
            "Je vais bien, merci ! Je suis là pour t’aider à organiser ton voyage au "
            f"{country_label}. Tu cherches une ville (ex: Rabat) et des dates ?"
        )
    return (
        "I’m doing well, thanks! I’m here to help you plan your "
        f"{country_label} trip. Which city/destination and dates are you considering?"
    )


def _detect_list_tours_intent(message: str) -> bool:
    msg = (message or '').strip().lower()
    if not msg:
        return False

    # Do NOT trigger on generic words like "tour" alone.
    # Only trigger when the user is clearly asking for a LIST / what EXISTS / what is AVAILABLE.
    patterns = [
        # Common EN/FR phrasings, incl. "what's"/"whats" and common misspellings like "availble".
        r"\b(available|availability|avail\w*|disponible|disponibles|existe|existent|exist|exists|show|list|liste|quels?|quelles?|what|what's|whats|which)\b.*\b(tours?|excursions?|packages?)\b",
        r"\b(tours?|excursions?|packages?)\b.*\b(available|availability|avail\w*|disponible|disponibles|existe|exist|exists|list|liste|quels?|quelles?|what|what's|whats|which)\b",
        r"\bnos\s+(tours?|excursions?)\b",
        r"\bliste\s+des\s+(tours?|excursions?)\b",
        r"\btours?\s+disponibles?\b",
    ]
    return any(re.search(p, msg) for p in patterns)


def _detect_list_cities_intent(message: str) -> bool:
    msg = (message or '').strip().lower()
    if not msg:
        return False
    patterns = [
        r"\b(cities|city|destinations?|places)\b.*\b(available|availability|avail\w*|list|show|what|what's|whats|which)\b",
        r"\b(available|availability|avail\w*|list|show|what|what's|whats|which)\b.*\b(cities|city|destinations?|places)\b",
        r"\b(villes?|destinations?|lieux)\b.*\b(disponible|disponibles|dispo|liste|quels?|quelles?)\b",
        r"\b(disponible|disponibles|dispo|liste|quels?|quelles?)\b.*\b(villes?|destinations?|lieux)\b",
    ]
    return any(re.search(p, msg) for p in patterns)


def _list_cities_reply(country: str, lang: str, limit: int = 12) -> str:
    country = _normalize_country(country)
    country_label = _country_label(country)
    try:
        names = list(
            Tour.objects.filter(country=country)
            .select_related('destination')
            .order_by('destination__name')
            .values_list('destination__name', flat=True)
            .distinct()
        )
    except (OperationalError, ProgrammingError):
        names = []

    names = [(n or '').strip() for n in names if (n or '').strip()]
    names = names[: max(1, int(limit))]

    if not names:
        if lang == 'fr':
            return f"Je n’ai pas trouvé de villes/destinations configurées sur le site {country_label} pour le moment."
        return f"I couldn’t find any cities/destinations configured on the {country_label} site right now."

    if lang == 'fr':
        return (
            f"Villes / destinations disponibles sur le site {country_label} : "
            + ", ".join(names)
            + "."
        )
    return (
        f"Available cities/destinations on the {country_label} site: "
        + ", ".join(names)
        + "."
    )


def _detect_how_it_works_intent(message: str) -> bool:
    msg = (message or '').strip().lower()
    if not msg:
        return False
    patterns = [
        r"\bhow\s+it\s+work\b",
        r"\bhow\s+it\s+works\b",
        r"\bhow\s+does\s+it\s+work\b",
        r"\bcomment\s+ca\s+marche\b",
        r"\bcomment\s+ça\s+marche\b",
        r"\bcomment\s+cela\s+marche\b",
    ]
    return any(re.search(p, msg) for p in patterns)


def _detect_private_tour_intent(message: str) -> bool:
    msg = (message or '').strip().lower()
    if not msg:
        return False
    # Private / tailor-made tours.
    patterns = [
        r"\bprivate\s+tours?\b",
        r"\btours?\s+priv[ée]s?\b",
        r"\bprivatis(?:er|ation|e|é)\b",
        r"\bsur\s*-?\s*mesure\b",
        r"\btailor(?:ed)?\b",
        r"\bcustom(?:ized)?\b",
        r"\bpersonal(?:ized)?\b.*\btours?\b",
        r"\bchauffeur\s+priv[ée]\b",
        r"\bguide\s+priv[ée]\b",
    ]
    return any(re.search(p, msg) for p in patterns)


def _private_tour_reply(country: str, lang: str) -> str:
    country_label = _country_label(country)
    if lang == 'fr':
        return (
            f"Oui — on peut organiser des tours privés / sur‑mesure au {country_label}. "
            "On adapte l’itinéraire, le rythme, le chauffeur/guide, et le niveau d’hébergement selon ton style. "
            "Pour te proposer une idée + un prix, dis-moi juste : 1) ville(s) ou circuit souhaité, 2) dates, 3) nombre de personnes, 4) budget (éco / standard / premium). "
            "Tu peux aussi nous écrire via le bouton WhatsApp ou la page Contact." 
        )
    return (
        f"Yes — we can arrange private / tailor‑made tours in {country_label}. "
        "We can adapt the itinerary, pace, driver/guide, and hotel level to your preferences. "
        "To suggest options + a price, tell me: 1) city/route, 2) dates, 3) number of people, 4) budget level (economy / standard / premium). "
        "You can also reach us via the WhatsApp button or the Contact page."
    )


def _how_it_works_reply(country: str, lang: str) -> str:
    country_label = _country_label(country)
    if lang == 'fr':
        return (
            f"Comment ça marche sur le site {country_label} :\n"
            "1) Tu choisis tes dates et ta ville d’arrivée (ex: Marrakech, Casablanca, Rabat).\n"
            "2) On te propose un itinéraire + hébergements + expériences adaptés à ton rythme.\n"
            "3) Tu profites — avec support et chauffeurs locaux de confiance.\n"
            "Tu as déjà une ville + une période en tête ?"
        )
    return (
        f"How it works on the {country_label} site:\n"
        "1) You choose your dates and arrival city (e.g., Marrakech, Casablanca, Rabat).\n"
        "2) We curate your route, stays, and local experiences to match your pace.\n"
        "3) You enjoy — with trusted local drivers and end-to-end support.\n"
        "Do you already have a city and date range in mind?"
    )


def _list_tours_reply(country: str, lang: str, limit: int = 6) -> str:
    country = _normalize_country(country)
    country_label = _country_label(country)
    try:
        tours = list(
            Tour.objects.filter(country=country)
            .select_related('destination')
            .order_by('id')[: max(1, int(limit))]
        )
    except (OperationalError, ProgrammingError):
        tours = []

    if not tours:
        if lang == 'fr':
            return f"Je n’ai trouvé aucun tour sur le site {country_label} pour le moment."
        return f"I couldn’t find any tours on the {country_label} site right now."

    lines = []
    if lang == 'fr':
        lines.append(f"Voici les tours disponibles sur le site {country_label} :")
    else:
        lines.append(f"Here are the tours available on the {country_label} site:")

    for t in tours:
        dest_name = getattr(t.destination, 'name', '') or ''
        header = f"{t.title} ({dest_name})" if dest_name else t.title
        if lang == 'fr':
            lines.append(f"- {header} — {t.price_per_night} par nuit.")
        else:
            lines.append(f"- {header} — {t.price_per_night} per night.")

    if lang == 'fr':
        lines.append("Dis-moi la ville + tes dates + le nombre de personnes, et je vérifie la disponibilité.")
    else:
        lines.append("Tell me the city + your dates + number of people and I’ll check availability.")

    return "\n".join(lines)


def _answer_from_site_content(country: str, message: str, lang: str) -> str:
    """Try to answer using the site's editable content (sections + info)."""
    country = _normalize_country(country)
    msg = (message or '').strip()
    if not msg:
        return ''

    candidates: list[tuple[int, str, str]] = []  # (score, title, snippet)
    try:
        cc = CountryContent.objects.filter(country=country).first()
        if cc:
            title = (getattr(cc, 'hero_title', '') or '').strip() or 'Hero'
            content = (getattr(cc, 'hero_subtitle', '') or '').strip()
            if content:
                candidates.append((_score_doc_relevance(msg, title, content), title, content))
    except (OperationalError, ProgrammingError):
        pass

    try:
        for s in Section.objects.filter(country=country).order_by('order'):
            title = (getattr(s, 'title', '') or '').strip() or 'Section'
            content = (getattr(s, 'content', '') or '').strip()
            if not content:
                continue
            candidates.append((_score_doc_relevance(msg, title, content), title, content))
    except (OperationalError, ProgrammingError):
        pass

    try:
        for d in Information.objects.filter(country=country):
            title = (getattr(d, 'title', '') or '').strip() or 'Info'
            content = (getattr(d, 'content', '') or '').strip()
            if not content:
                continue
            candidates.append((_score_doc_relevance(msg, title, content), title, content))
    except (OperationalError, ProgrammingError):
        pass

    if not candidates:
        return ''

    best = sorted(candidates, key=lambda x: x[0], reverse=True)[:2]
    best = [b for b in best if b[0] > 0]
    if not best:
        return ''

    lines = []
    if lang == 'fr':
        lines.append("Voici ce que j’ai trouvé sur le site :")
    else:
        lines.append("Here’s what I found on the site:")

    for _, title, content in best:
        snippet = content.replace('\n', ' ').strip()
        lines.append(f"- {title}: {snippet[:420]}")

    if lang == 'fr':
        lines.append("Tu veux que je t’aide à réserver (dates + personnes) ou tu as une autre question ?")
    else:
        lines.append("Do you want help booking (dates + people), or do you have another question?")
    return "\n".join(lines)


def _greeting_reply(country: str, lang: str) -> str:
    country_label = _country_label(country)
    if lang == 'fr':
        return (
            f"Bonjour ! Je suis votre assistant virtuel pour {country_label}. "
            "Demandez-moi des infos sur les tours, les prix, ou des dates disponibles (ex: ‘5 nuits en juin, 2 personnes’)."
        )
    return (
        f"Hello! I’m your virtual assistant for {country_label}. "
        "Ask about tours, pricing, or available dates (e.g., ‘5 nights in June for 2 people’)."
    )


def _is_seq2seq_hf_model(model_id: str) -> bool:
    m = (model_id or '').lower()
    # Common seq2seq families on HF (not compatible with HF Hub streaming text-generation API).
    return any(k in m for k in ['t5', 'flan', 'mt0', 'bart', 'pegasus'])


def _truncate_prompt_for_model(model_id: str, prompt: str) -> str:
    """Keep prompts small for tiny seq2seq models (e.g., flan-t5-small)."""
    if not prompt:
        return ''
    model_id = (model_id or '').lower()
    # flan-t5-small has a small context; keep it tight.
    if 'flan-t5-small' in model_id or model_id.endswith('/flan-t5-small'):
        return prompt[-2500:]
    if _is_seq2seq_hf_model(model_id):
        return prompt[-4000:]
    return prompt


def _stream_chunks(text: str, chunk_size: int = 40):
    """Yield human-friendly chunks to the client (SSE)."""
    text = text or ''
    if not text:
        return
    # Prefer splitting by spaces to avoid breaking words.
    if ' ' in text:
        words = text.split(' ')
        buf = ''
        for w in words:
            if not w:
                continue
            nxt = (buf + (' ' if buf else '') + w)
            if len(nxt) >= chunk_size:
                yield (buf + (' ' if buf else '') + w) if not buf else nxt
                buf = ''
            else:
                buf = nxt
        if buf:
            yield buf
    else:
        for i in range(0, len(text), chunk_size):
            yield text[i:i + chunk_size]


def _hf_normalize_router_model_id(model_id: str) -> str:
    """Normalize HF model id for the router OpenAI-compatible endpoint.

    If no routing policy is specified, default to ":fastest".
    """
    model_id = (model_id or '').strip()
    if not model_id:
        return model_id
    if model_id.startswith('http://') or model_id.startswith('https://'):
        return model_id
    if ':' in model_id:
        return model_id
    return model_id + ':fastest'


def _hf_router_chat_completion_full_text(
    model_id: str,
    token: str,
    system_prompt: str,
    user_message: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
) -> str:
    """Call HuggingFace Inference Providers via the OpenAI-compatible router endpoint."""
    model_id = _hf_normalize_router_model_id(model_id)
    url = 'https://router.huggingface.co/v1/chat/completions'
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model_id,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message},
        ],
        'max_tokens': int(max_tokens),
        'temperature': float(temperature),
        'top_p': float(top_p),
        'stream': False,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code >= 400:
        try:
            err = r.json()
        except Exception:
            err = {'error': r.text}
        raise RuntimeError(f"HF router error {r.status_code}: {err}")
    data = r.json() or {}
    try:
        return str(data['choices'][0]['message']['content'] or '').strip()
    except Exception:
        return str(data).strip()


def _hf_router_chat_completion_stream(
    model_id: str,
    token: str,
    system_prompt: str,
    user_message: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
):
    """Yield delta tokens (strings) from HF router chat completion streaming."""
    model_id = _hf_normalize_router_model_id(model_id)
    url = 'https://router.huggingface.co/v1/chat/completions'
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'text/event-stream',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model_id,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message},
        ],
        'max_tokens': int(max_tokens),
        'temperature': float(temperature),
        'top_p': float(top_p),
        'stream': True,
    }

    with requests.post(url, headers=headers, json=payload, stream=True, timeout=(10, 120)) as r:
        if r.status_code >= 400:
            try:
                err = r.json()
            except Exception:
                err = {'error': r.text}
            raise RuntimeError(f"HF router error {r.status_code}: {err}")

        for raw_line in r.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if not data:
                continue
            if data == '[DONE]':
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            try:
                delta = obj['choices'][0].get('delta') or {}
                content = delta.get('content')
            except Exception:
                content = None
            if content:
                yield str(content)


HF_ROUTER_DEFAULT_MODEL = 'Qwen/Qwen2.5-7B-Instruct:fastest'


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
from django.http import HttpResponsePermanentRedirect
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, StreamingHttpResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

import openai
from django.db.utils import OperationalError, ProgrammingError

from .models import Tour, TourActivity, Reservation, BlogPost, Destination, ContactMessage, BlogComment, UserProfile, CountryContent, Section, Information, ChatMessage


def _safe_media_url(media_obj):
    if not media_obj:
        return ''
    try:
        return media_obj.url
    except Exception:
        return ''


def _time_to_minutes(value):
    if value in (None, ''):
        return None
    if hasattr(value, 'hour') and hasattr(value, 'minute'):
        return int(value.hour) * 60 + int(value.minute)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.strptime(raw[:5], '%H:%M')
        return parsed.hour * 60 + parsed.minute
    except Exception:
        return None


def _minutes_to_time_label(value):
    if value is None:
        return ''
    total = int(value) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _serialize_extra_itinerary_option(extra):
    start_minutes = _time_to_minutes(getattr(extra, 'itinerary_start_time', None))
    duration_minutes = int(getattr(extra, 'itinerary_duration_minutes', 0) or 0)
    end_minutes = start_minutes + duration_minutes if start_minutes is not None and duration_minutes > 0 else None
    return {
        'id': int(extra.id),
        'title': extra.title,
        'description': extra.description,
        'image_url': _safe_media_url(extra.image),
        'location': extra.location_display,
        'map_url': extra.map_url,
        'latitude': float(extra.latitude) if extra.latitude is not None else None,
        'longitude': float(extra.longitude) if extra.longitude is not None else None,
        'price_label': f"+{extra.price}$ {'/day' if extra.is_per_night else '/trip'}",
        'insert_into_itinerary': bool(extra.insert_into_itinerary),
        'itinerary_day_number': int(extra.itinerary_day_number or 0) if extra.itinerary_day_number else None,
        'itinerary_start_time': _minutes_to_time_label(start_minutes),
        'itinerary_end_time': _minutes_to_time_label(end_minutes),
        'itinerary_start_minutes': start_minutes,
        'itinerary_duration_minutes': duration_minutes,
    }


def _recompute_day_card_metadata(day_cards: list[dict]):
    day_cards.sort(key=lambda item: (
        _time_to_minutes(item.get('start_time')) if _time_to_minutes(item.get('start_time')) is not None else 10**9,
        _time_to_minutes(item.get('end_time')) if _time_to_minutes(item.get('end_time')) is not None else 10**9,
        int(item.get('sequence') or 0),
    ))
    for index, card in enumerate(day_cards, start=1):
        card['sequence'] = index
        if index == 1:
            card['segment_distance'] = ''
            card['segment_transport'] = ''
            card['segment_from_title'] = ''
            card['segment_summary'] = ''
            card['segment_badge'] = ''
            continue
        previous = day_cards[index - 2]
        from_activity_id = card.get('segment_from_activity_id')
        if not card.get('is_extra') and not previous.get('is_extra') and from_activity_id and previous.get('activity_id') == from_activity_id:
            continue
        card['segment_distance'] = ''
        card['segment_transport'] = ''
        card['segment_from_title'] = ''
        card['segment_summary'] = ''
        card['segment_badge'] = ''


def _apply_selected_extras_to_itinerary_days(base_days: list[dict], extra_options: list[dict], selected_extra_ids: list[int] | None = None) -> list[dict]:
    selected_ids = {int(x) for x in (selected_extra_ids or []) if str(x).strip().isdigit()}
    day_map: dict[int, dict] = {}
    for day in (base_days or []):
        cloned_cards = [dict(card) for card in day.get('cards', [])]
        _recompute_day_card_metadata(cloned_cards)
        day_map[int(day.get('day_number') or 1)] = {
            'day_number': int(day.get('day_number') or 1),
            'label': day.get('label') or f"Day {int(day.get('day_number') or 1)}",
            'cards': cloned_cards,
            'map_points': [],
        }

    for extra in sorted(
        [item for item in (extra_options or []) if int(item.get('id') or 0) in selected_ids and item.get('insert_into_itinerary')],
        key=lambda item: (
            int(item.get('itinerary_day_number') or 10**6),
            int(item.get('itinerary_start_minutes') if item.get('itinerary_start_minutes') is not None else 10**6),
            int(item.get('id') or 0),
        ),
    ):
        day_number = int(extra.get('itinerary_day_number') or 0)
        start_minutes = extra.get('itinerary_start_minutes')
        duration_minutes = int(extra.get('itinerary_duration_minutes') or 0)
        if not day_number or start_minutes is None or duration_minutes <= 0:
            continue

        day_entry = day_map.setdefault(day_number, {
            'day_number': day_number,
            'label': f"Day {day_number}",
            'cards': [],
            'map_points': [],
        })
        day_cards = day_entry['cards']
        for card in day_cards:
            card_start = _time_to_minutes(card.get('start_time'))
            card_end = _time_to_minutes(card.get('end_time'))
            if card_start is not None and card_start >= start_minutes:
                card['start_time'] = _minutes_to_time_label(card_start + duration_minutes)
                if card_end is not None:
                    card['end_time'] = _minutes_to_time_label(card_end + duration_minutes)
            elif card_start is not None and card_end is not None and card_start < start_minutes < card_end:
                shift = start_minutes + duration_minutes - card_start
                card['start_time'] = _minutes_to_time_label(card_start + shift)
                card['end_time'] = _minutes_to_time_label(card_end + shift)
            elif card_end is not None and card_end > start_minutes:
                card['end_time'] = _minutes_to_time_label(card_end + duration_minutes)

        extra_card = {
            'kind': 'extra',
            'activity_id': None,
            'extra_id': extra.get('id'),
            'is_extra': True,
            'sequence': len(day_cards) + 1,
            'day_number': day_number,
            'point_role': TourActivity.POINT_REGULAR,
            'title': extra.get('title', ''),
            'description': extra.get('description', ''),
            'image_url': extra.get('image_url', ''),
            'location': extra.get('location', ''),
            'map_url': extra.get('map_url', ''),
            'latitude': extra.get('latitude'),
            'longitude': extra.get('longitude'),
            'start_time': extra.get('itinerary_start_time', ''),
            'end_time': extra.get('itinerary_end_time', ''),
            'price_label': extra.get('price_label', ''),
            'segment_distance': '',
            'segment_transport': '',
            'segment_from_title': '',
            'segment_summary': '',
            'segment_badge': '',
            'segment_from_activity_id': None,
        }
        day_cards.append(extra_card)
        _recompute_day_card_metadata(day_cards)

    final_days = []
    for day_number in sorted(day_map):
        day_cards = day_map[day_number]['cards']
        map_points = []
        for local_index, card in enumerate(day_cards, start=1):
            point_role = card.get('point_role') or TourActivity.POINT_REGULAR
            role_label = ''
            if point_role == TourActivity.POINT_START:
                role_label = 'Starting point'
            elif point_role == TourActivity.POINT_END:
                role_label = 'Ending point'
            map_points.append({
                'sequence': local_index,
                'global_sequence': card.get('sequence'),
                'day_number': day_number,
                'title': card.get('title', ''),
                'location': card.get('location', ''),
                'image_url': card.get('image_url', ''),
                'latitude': card.get('latitude'),
                'longitude': card.get('longitude'),
                'segment_distance': card.get('segment_distance', ''),
                'segment_transport': card.get('segment_transport', ''),
                'segment_from_title': card.get('segment_from_title', ''),
                'segment_summary': card.get('segment_summary', ''),
                'segment_badge': card.get('segment_badge', ''),
                'point_role': point_role,
                'role_label': role_label,
                'start_time': card.get('start_time', ''),
                'end_time': card.get('end_time', ''),
            })
        final_days.append({
            'day_number': day_number,
            'label': day_map[day_number]['label'],
            'cards': day_cards,
            'map_points': map_points,
            'has_map_points': bool(map_points),
        })
    return final_days


def _build_activity_gallery_cards(tour: Tour) -> list[dict]:
    cards: list[dict] = []
    legs_by_target: dict[int, dict] = {}

    for leg in tour.itinerary_legs.filter(is_active=True).select_related('from_activity', 'to_activity').order_by('display_order', 'id'):
        legs_by_target[leg.to_activity_id] = {
            'from_activity_id': leg.from_activity_id,
            'from_title': leg.from_activity.title,
            'to_title': leg.to_activity.title,
            'distance_label': leg.distance_label,
            'transport_mode': leg.transport_mode,
            'transport_label': leg.transport_display_label,
            'summary': f"{leg.distance_label} by {leg.transport_display_label}",
            'card_badge': f"{leg.distance_label} by {leg.transport_display_label}",
        }

    for index, activity in enumerate(tour.activity_cards.filter(is_active=True).order_by('day_number', 'display_order', 'id'), start=1):
        leg_info = legs_by_target.get(activity.id)
        cards.append({
            'kind': 'activity',
            'activity_id': activity.id,
            'extra_id': None,
            'is_extra': False,
            'sequence': index,
            'day_number': activity.day_number or 1,
            'point_role': activity.point_role or TourActivity.POINT_REGULAR,
            'title': activity.title,
            'description': activity.description,
            'image_url': _safe_media_url(activity.image),
            'location': activity.location_display,
            'map_url': activity.map_url,
            'latitude': float(activity.latitude) if activity.latitude is not None else None,
            'longitude': float(activity.longitude) if activity.longitude is not None else None,
            'start_time': activity.start_time.strftime('%H:%M') if activity.start_time else '',
            'end_time': activity.end_time.strftime('%H:%M') if activity.end_time else '',
            'price_label': '',
            'segment_from_activity_id': leg_info['from_activity_id'] if leg_info else None,
            'segment_distance': leg_info['distance_label'] if leg_info else '',
            'segment_transport': leg_info['transport_label'] if leg_info else '',
            'segment_from_title': leg_info['from_title'] if leg_info else '',
            'segment_summary': leg_info['summary'] if leg_info else '',
            'segment_badge': leg_info['card_badge'] if leg_info else '',
        })

    itinerary_count = len(cards)
    for offset, extra in enumerate(tour.extra_activities.filter(is_active=True).order_by('id'), start=1):
        cards.append({
            'kind': 'extra',
            'activity_id': None,
            'extra_id': extra.id,
            'is_extra': True,
            'sequence': itinerary_count + offset,
            'title': extra.title,
            'description': extra.description,
            'image_url': _safe_media_url(extra.image),
            'location': extra.location_display,
            'map_url': extra.map_url,
            'latitude': float(extra.latitude) if extra.latitude is not None else None,
            'longitude': float(extra.longitude) if extra.longitude is not None else None,
            'start_time': '',
            'end_time': '',
            'price_label': f"+{extra.price}$ {'/day' if extra.is_per_night else '/trip'}",
            'segment_from_activity_id': None,
        })

    return cards


def _build_itinerary_days(tour: Tour, selected_extra_ids: list[int] | None = None) -> list[dict]:
    activity_cards = [card for card in _build_activity_gallery_cards(tour) if not card.get('is_extra')]
    if not activity_cards:
        return []

    day_map: dict[int, dict] = {}
    for card in activity_cards:
        day_number = int(card.get('day_number') or 1)
        day_entry = day_map.setdefault(day_number, {
            'day_number': day_number,
            'label': f"Day {day_number}",
            'cards': [],
            'map_points': [],
        })
        day_entry['cards'].append(card)

    base_days = [day_map[key] for key in sorted(day_map)]
    extra_options = [
        _serialize_extra_itinerary_option(extra)
        for extra in tour.extra_activities.filter(is_active=True).order_by('id')
    ]
    return _apply_selected_extras_to_itinerary_days(base_days, extra_options, selected_extra_ids)
from .context_processors import get_country_from_site


def _sse_pack(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _build_llm_prompt(system_prompt: str, history, user_message: str | None = None) -> str:
    """Build a chat-like prompt for text-generation models.

    Note: We avoid persisting chat history in DB; `history` can be an empty list.
    """
    lines = [system_prompt.strip(), "", "Conversation:"]
    for msg in (history or []):
        role = getattr(msg, 'role', 'user')
        content = getattr(msg, 'message', '')
        if role in {'bot', 'assistant'}:
            lines.append(f"Assistant: {content}")
        else:
            lines.append(f"User: {content}")
    if user_message:
        lines.append(f"User: {user_message}")
    lines.append("Assistant:")
    return "\n".join(lines).strip() + " "


@csrf_exempt
def ai_chat_stream(request):
    """Streaming AI chat endpoint (SSE over POST).

    Response is text/event-stream with messages:
    - {type:'delta', text:'...'} repeated
    - {type:'final', text:'...', action:{...}} once
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)

    message = _redact_secrets((payload.get('message') or '').strip())
    if not message:
        return JsonResponse({'error': 'Message cannot be empty.'}, status=400)

    # Require login for chat so we can safely check per-user booking overlaps.
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        login_url = reverse('login')

        def _gen_login_required():
            yield _sse_pack({
                'type': 'final',
                'text': 'Please log in to use the chat and to book. Redirecting to the login page…',
                'action': {'navigate': login_url},
            })

        return StreamingHttpResponse(_gen_login_required(), content_type='text/event-stream')

    country = _normalize_country(get_country_from_site(request) or 'morocco')
    country_label = _country_label(country)
    # Privacy: do NOT store chat messages in DB.

    request_id = uuid.uuid4().hex
    session_memory = bool(getattr(settings, 'CHAT_SESSION_MEMORY', False))
    session_history_max = int(getattr(settings, 'CHAT_SESSION_HISTORY_MAX', 8) or 8)
    session_history: list[dict] = []
    if session_memory:
        try:
            session_history = request.session.get('chat_history') or []
            if not isinstance(session_history, list):
                session_history = []
        except Exception:
            session_history = []
        session_history.append({'role': 'user', 'content': message})
        request.session['chat_history'] = session_history[-session_history_max:]

    lang = getattr(settings, 'CHAT_FORCE_LANGUAGE', '') or _detect_language(message)
    history = []
    welcome_should_show = _welcome_should_show(request)
    welcome_enabled = bool(welcome_should_show and _is_starting_chat(message))
    if welcome_enabled:
        # Mark as shown immediately; streaming responses can't reliably persist session writes inside the generator.
        _mark_welcome_shown(request)

    site_context = _build_country_catalog_context(country, message)
    booking_rules_context = _build_booking_rules_context()

    language_instruction = (
        "Respond in English only. " if lang == 'en' else (
            "Respond in French only. " if lang == 'fr' else "Respond in the same language as the user (French or English). "
        )
    )

    system_prompt = (
        f"You are the official virtual assistant for the {country_label} travel website. "
        "You can answer general travel questions about this country and its cities (explain what a city is like, what to choose, tips). "
        "If the user asks about another country/site, politely refuse and redirect them to questions about the current site. "
        + language_instruction +
        "Sound natural and human (not robotic). Be concise and helpful. "
        "Ask at most 1 short follow-up question, only when needed. "
        "Do not repeat the same question if the user already answered it. "
        "Avoid re-confirmation loops: if the user says yes/correct, do not ask to confirm again; move to the next missing detail. "
        "Never ask the user to confirm details (no 'Let's confirm...'); assume provided details are correct unless the user changes them. "
        "Never ask for card/payment details (numbers, CVV, etc). This site only needs a payment method: cash or card. "
        "Do not restate all booking details unless the user asks. "
        + ("This is the first user message in this session: start with a brief friendly greeting (one short sentence). " if welcome_enabled else "Do not add a repetitive greeting if the conversation is already ongoing. ")
        +
        "Do NOT repeat or dump the provided site context verbatim; never echo long blocks of text. "
        "Do NOT output special navigation markers like [NAVIGATE] or [PREFILL]. The backend/UI handles navigation. "
        "Currency rule: always present prices in USD only; do NOT mention MAD or Moroccan dirhams. "
        "Never invent site inventory (tours IDs, prices, availability) beyond the provided catalog/context. "
        "For booking, ask only for missing fields and follow the booking rules.\n\n"
        f"{booking_rules_context}\n\n"
        f"{site_context}"
    )

    if session_memory and session_history:
        # Give the model short conversation memory without persisting to DB.
        def _fmt_role(r: str) -> str:
            return 'Assistant' if r in {'assistant', 'bot'} else 'User'

        recent = session_history[-session_history_max:]
        recent_lines = []
        for item in recent:
            role = _fmt_role(str(item.get('role') or 'user'))
            content = str(item.get('content') or '').strip()
            if not content:
                continue
            recent_lines.append(f"{role}: {content}")
        if recent_lines:
            system_prompt = system_prompt + "\n\nRecent conversation (context):\n" + "\n".join(recent_lines[-session_history_max:])

    # Deterministic action computation (optional) so the UI can still navigate/prefill.
    action = {}
    deterministic_text: str | None = None
    msg_lower = message.lower()
    keyword_booking_intent = any(k in msg_lower for k in ['book', 'booking', 'reserve', 'reservation', 'réserver', 'reserver'])
    start_date_req, end_date_req, persons_req, parsed_dest = _extract_booking_details(message)
    payment_method_req = _extract_payment_method(message)
    addons_req = _extract_booking_addons(message)
    destination_hint = None
    if not _is_greeting(message) and not _is_smalltalk(message):
        destination_hint = _resolve_destination_hint(country, message, parsed_dest)

    # Pending booking continuation (ask only missing fields, especially payment method)
    pending = _get_pending_booking(request)
    pending_extra_ids: list[str] = []
    if pending:
        # Follow-up date updates like "from 8th to 11th" may omit the month/year.
        # Infer them from the pending booking month to keep the flow deterministic.
        if not (start_date_req and end_date_req):
            ref = _date_from_iso(pending.get('start_date')) or _date_from_iso(pending.get('end_date'))
            sd2, ed2 = _extract_day_range_without_month(message, ref)
            if sd2 and ed2:
                start_date_req, end_date_req = sd2, ed2

        # Merge missing details from pending (but allow current message to override)
        if not destination_hint:
            destination_hint = (pending.get('destination') or None)
        if not persons_req:
            try:
                persons_req = int(pending.get('persons') or 0) or None
            except Exception:
                persons_req = None
        if not start_date_req:
            start_date_req = _date_from_iso(pending.get('start_date'))
        if not end_date_req:
            end_date_req = _date_from_iso(pending.get('end_date'))
        if not payment_method_req:
            pm = (pending.get('payment_method') or '').strip().lower()
            payment_method_req = pm if pm in {'cash', 'card'} else None

        # Merge add-ons from pending unless explicitly provided in current message.
        for key in ['full_package', 'include_transport', 'include_hotel', 'extras']:
            if addons_req.get(key) is None and isinstance(pending.get(key), (bool, type(None))):
                addons_req[key] = pending.get(key)

        _pei = pending.get('extra_activity_ids')
        if isinstance(_pei, list):
            pending_extra_ids = [str(x).strip() for x in _pei if str(x).strip()]

    has_core_booking_fields = bool((parsed_dest or destination_hint) and start_date_req and end_date_req and persons_req)
    # If we already have pending booking context, stay in booking flow even if the user reply only contains (e.g.) new dates.
    booking_intent = bool(keyword_booking_intent or has_core_booking_fields or pending)


    if session_memory:
        if (not destination_hint) and (not parsed_dest):
            destination_hint = request.session.get('chat_last_destination')
        if not persons_req:
            try:
                persons_req = int(request.session.get('chat_last_persons') or 0) or None
            except Exception:
                persons_req = None
        if destination_hint:
            request.session['chat_last_destination'] = destination_hint
        if persons_req:
            request.session['chat_last_persons'] = int(persons_req)
        if start_date_req:
            request.session['chat_last_start_date'] = start_date_req.strftime('%Y-%m-%d')
        if end_date_req:
            request.session['chat_last_end_date'] = end_date_req.strftime('%Y-%m-%d')

    booking_hint = (parsed_dest or destination_hint)
    selected_tour_id: int | None = None

    # Handle explicit reservation management (cancel / change) without re-asking for already known details.
    # This avoids “booking reference” loops when the site enforces a single active reservation per country.
    manage_intent = _detect_reservation_manage_intent(message)
    tour_id_hint = None
    try:
        if pending and pending.get('tour_id'):
            tour_id_hint = int(pending.get('tour_id'))
        elif session_memory:
            tour_id_hint = int(request.session.get('chat_last_tour_id') or 0) or None
    except Exception:
        tour_id_hint = None

    if manage_intent == 'cancel':
        r, st = _cancel_matching_user_reservation(
            user=request.user,
            country=country,
            start_date=start_date_req,
            end_date=end_date_req,
            destination_hint=booking_hint,
            tour_id_hint=tour_id_hint,
        )
        _set_pending_booking(request, None)
        if st == 'cancelled' and r:
            tour_title = getattr(getattr(r, 'tour', None), 'title', '') or 'your tour'
            if lang == 'fr':
                deterministic_text = f"✅ C’est fait — j’ai annulé ta réservation pour “{tour_title}”."
            else:
                deterministic_text = f"✅ Done — I cancelled your reservation for “{tour_title}”."
        elif st == 'ambiguous':
            if lang == 'fr':
                deterministic_text = "J’ai trouvé plusieurs réservations actives. Tu veux annuler laquelle (ville ou dates) ?"
            else:
                deterministic_text = "I found multiple active reservations. Which one should I cancel (city or dates)?"
        else:
            if lang == 'fr':
                deterministic_text = "Je ne trouve aucune réservation active à annuler pour le moment."
            else:
                deterministic_text = "I can’t find an active reservation to cancel right now."

    # Private tours info (only when user is not already providing a full booking payload).
    if (not deterministic_text) and _detect_private_tour_intent(message) and (not has_core_booking_fields):
        deterministic_text = _private_tour_reply(country, lang)

    # Private tours info (only when user is not already providing a full booking payload).
    if (not deterministic_text) and _detect_private_tour_intent(message) and (not has_core_booking_fields):
        deterministic_text = _private_tour_reply(country, lang)

    # Structured booking state for the model (no canned replies).
    computed_hints_lines: list[str] = []
    if (not deterministic_text) and booking_intent:
        missing = []
        if not booking_hint:
            missing.append('destination/tour')
        if not (start_date_req and end_date_req):
            missing.append('dates')
        if not persons_req:
            missing.append('number_of_people')

        if missing:
            computed_hints_lines.append(
                "Booking intent detected. Missing fields: " + ", ".join(missing) + ". Ask ONLY for the most important missing field (one question)."
            )
            # Deterministic: ask only for the top missing field.
            if lang == 'fr':
                if 'destination/tour' in missing:
                    deterministic_text = "Pour quelle ville/destination veux-tu réserver ?"
                elif 'dates' in missing:
                    deterministic_text = "Quelles dates (du … au …) ?"
                else:
                    deterministic_text = "C’est pour combien de personnes ?"
            else:
                if 'destination/tour' in missing:
                    deterministic_text = "Which city/destination is the tour for?"
                elif 'dates' in missing:
                    deterministic_text = "What dates (from … to …)?"
                else:
                    deterministic_text = "How many people is it for?"
        else:
            requested_nights = max(0, (end_date_req - start_date_req).days)
            if requested_nights <= 0:
                computed_hints_lines.append("Invalid date range: end_date must be after start_date. Ask the user to correct dates.")
                deterministic_text = (
                    "La date de fin doit être après la date de début. Tu peux me redonner les dates (du … au …) ?"
                    if lang == 'fr' else
                    "End date must be after start date. Can you resend the dates (from … to …)?"
                )
            elif requested_nights > 5:
                computed_hints_lines.append("Booking rule: maximum stay is 5 days. Ask for a shorter date range.")
                deterministic_text = (
                    "La durée maximale est de 11 nuits. Peux-tu choisir des dates plus courtes ?"
                    if lang == 'fr' else
                    "Maximum stay is 5 days. Can you choose a shorter date range?"
                )
            else:
                will_replace_existing = _user_has_overlapping_reservation(request.user, country, start_date_req, end_date_req)
                tour, status, candidates = _select_tour_for_booking(country, message, booking_hint)

                if not tour:
                    if status == 'multiple' and candidates:
                        titles = [f"{t.id}: {t.title}" for t in candidates[:6]]
                        computed_hints_lines.append("Multiple tours match. Ask user to choose one (ID or title). Options: " + " | ".join(titles))
                        deterministic_text = (
                            "Plusieurs tours correspondent. Lequel choisis-tu (ID ou titre) ? Options: " + " | ".join(titles)
                            if lang == 'fr' else
                            "Multiple tours match. Which one do you want (ID or title)? Options: " + " | ".join(titles)
                        )
                    else:
                        computed_hints_lines.append("No matching tour exists for the requested destination on this site. Ask user to choose a destination/tour from the site catalog.")
                        deterministic_text = (
                            "Je ne trouve pas ce tour sur le site. Tu peux me donner la ville/destination exacte (ex: Rabat, Marrakech…) ?"
                            if lang == 'fr' else
                            "I can’t find that tour on this site. What exact city/destination is it (e.g., Rabat, Marrakech…)?"
                        )
                else:
                    selected_tour_id = int(tour.id)

                    # Optional extra activity selection (single).
                    chosen_extra_id = _select_single_extra_activity_id(tour, message)
                    if chosen_extra_id:
                        addons_req['extras'] = True
                        pending_extra_ids = [str(chosen_extra_id)]
                    if addons_req.get('extras') is False:
                        pending_extra_ids = []
                        computed_hints_lines.append("User explicitly does NOT want extra activities. Do not ask about extras.")

                    if addons_req.get('extras') is True and not pending_extra_ids:
                        # If the user replies with a bare "yes" and there is only ONE extra option,
                        # auto-select it to avoid looping on the same question.
                        if _is_affirmative(message):
                            try:
                                only_extra = list(tour.extra_activities.filter(is_active=True).only('id').order_by('id')[:2])
                            except Exception:
                                only_extra = []
                            if len(only_extra) == 1:
                                pending_extra_ids = [str(getattr(only_extra[0], 'id'))]

                        options_txt = _format_tour_extra_activities(tour)
                        if options_txt:
                            _set_pending_booking(request, {
                                'tour_id': int(tour.id),
                                'destination': booking_hint or '',
                                'start_date': start_date_req.strftime('%Y-%m-%d'),
                                'end_date': end_date_req.strftime('%Y-%m-%d'),
                                'persons': int(persons_req),
                                'payment_method': payment_method_req,
                                'full_package': bool(addons_req.get('full_package')),
                                'include_transport': bool(addons_req.get('include_transport') or bool(addons_req.get('full_package'))),
                                'include_hotel': bool(addons_req.get('include_hotel') or bool(addons_req.get('full_package'))),
                                'extras': True,
                                'extra_activity_ids': [],
                            })
                            computed_hints_lines.append(
                                "User wants extra activities. Ask them to choose exactly ONE extra activity from these options: " + options_txt + "."
                            )
                            deterministic_text = (
                                "Tu veux une activité extra. Choisis-en UNE: " + options_txt
                                if lang == 'fr' else
                                "You want an extra activity. Pick EXACTLY ONE: " + options_txt
                            )
                        else:
                            addons_req['extras'] = False
                            pending_extra_ids = []
                    else:
                        if not _user_break_buffer_ok(request.user, country, start_date_req, buffer_days=0):
                            computed_hints_lines.append("No booking buffer is allowed anymore. Skip this rule.")
                            # Preserve booking context so user can reply with only new dates.
                            _set_pending_booking(request, {
                                'tour_id': int(tour.id),
                                'destination': booking_hint or '',
                                'start_date': start_date_req.strftime('%Y-%m-%d'),
                                'end_date': end_date_req.strftime('%Y-%m-%d'),
                                'persons': int(persons_req),
                                'payment_method': payment_method_req,
                                'full_package': bool(addons_req.get('full_package')),
                                'include_transport': bool(addons_req.get('include_transport') or bool(addons_req.get('full_package'))),
                                'include_hotel': bool(addons_req.get('include_hotel') or bool(addons_req.get('full_package'))),
                                'extras': addons_req.get('extras'),
                                'extra_activity_ids': pending_extra_ids,
                            })
                            deterministic_text = (
                                "Tu dois laisser 3 jours de pause après ta dernière réservation. Peux-tu choisir une date de début plus tardive ?"
                                if lang == 'fr' else
                                "Please choose different dates."
                            )
                        elif not _is_range_available(country, start_date_req, end_date_req, buffer_days=0, exclude_user=request.user):
                            # Preserve booking context so the user can reply with only a new date range.
                            _set_pending_booking(request, {
                                'tour_id': int(tour.id),
                                'destination': booking_hint or '',
                                'start_date': start_date_req.strftime('%Y-%m-%d'),
                                'end_date': end_date_req.strftime('%Y-%m-%d'),
                                'persons': int(persons_req),
                                'payment_method': payment_method_req,
                                'full_package': bool(addons_req.get('full_package')),
                                'include_transport': bool(addons_req.get('include_transport') or bool(addons_req.get('full_package'))),
                                'include_hotel': bool(addons_req.get('include_hotel') or bool(addons_req.get('full_package'))),
                                'extras': addons_req.get('extras'),
                                'extra_activity_ids': pending_extra_ids,
                            })
                            suggestions = _suggest_available_ranges_near(
                                country,
                                start_date_req,
                                nights=min(max(requested_nights, 3), 11),
                                limit=4,
                                buffer_days=0,
                                exclude_user=request.user,
                            )
                            if suggestions:
                                sug_txt = " ; ".join([f"{s.strftime('%Y-%m-%d')} to {e.strftime('%Y-%m-%d')}" for s, e in suggestions])
                                computed_hints_lines.append("Requested dates are unavailable. Offer alternatives: " + sug_txt + ". Ask which one they prefer.")
                                deterministic_text = (
                                    "Ces dates ne sont pas disponibles. Tu préfères laquelle ? " + sug_txt
                                    if lang == 'fr' else
                                    "Those dates aren’t available. Which option do you prefer? " + sug_txt
                                )
                            else:
                                computed_hints_lines.append("Requested dates are unavailable. Ask the user for another date range.")
                                deterministic_text = (
                                    "Ces dates ne sont pas disponibles. Donne-moi un autre intervalle (du … au …)."
                                    if lang == 'fr' else
                                    "Those dates aren’t available. Please share another date range (from … to …)."
                                )
                        else:
                            # Effective add-ons
                            full_pkg = bool(addons_req.get('full_package'))
                            inc_transport = bool(addons_req.get('include_transport') or full_pkg)
                            inc_hotel = bool(addons_req.get('include_hotel') or full_pkg)

                            if full_pkg:
                                computed_hints_lines.append("User selected FULL PACKAGE. Do NOT ask about hotel/transport; they are included.")

                            if not payment_method_req:
                                _set_pending_booking(request, {
                                    'tour_id': int(tour.id),
                                    'destination': booking_hint or '',
                                    'start_date': start_date_req.strftime('%Y-%m-%d'),
                                    'end_date': end_date_req.strftime('%Y-%m-%d'),
                                    'persons': int(persons_req),
                                    'payment_method': None,
                                    'full_package': full_pkg,
                                    'include_transport': inc_transport,
                                    'include_hotel': inc_hotel,
                                    'extras': addons_req.get('extras'),
                                    'extra_activity_ids': pending_extra_ids,
                                })
                                computed_hints_lines.append("All booking fields are known except payment_method. Ask ONLY: cash (espèces) or card (carte).")
                                deterministic_text = (
                                    "OK. Paiement par carte ou en espèces ?"
                                    if lang == 'fr' else
                                    "OK — would you like to pay by card or cash?"
                                )
                            else:
                                _set_pending_booking(request, None)
                                action['book_direct'] = {
                                    'url': reverse('chat_book_tour'),
                                    'tour_id': int(tour.id),
                                    'tour_slug': tour.slug,
                                    'start_date': start_date_req.strftime('%Y-%m-%d'),
                                    'end_date': end_date_req.strftime('%Y-%m-%d'),
                                    'persons': int(persons_req),
                                    'payment_method': payment_method_req,
                                    'full_package': 1 if full_pkg else 0,
                                    'include_transport': 1 if inc_transport else 0,
                                    'include_hotel': 1 if inc_hotel else 0,
                                    'extra_activity_ids': [int(x) for x in (pending_extra_ids or [])],
                                }
                                computed_hints_lines.append("Booking is ready. Do not re-confirm; proceed as completed.")

                                if session_memory:
                                    try:
                                        request.session['chat_last_tour_id'] = int(tour.id)
                                        request.session['chat_last_payment_method'] = payment_method_req
                                        request.session['chat_last_full_package'] = bool(full_pkg)
                                        request.session['chat_last_include_transport'] = bool(inc_transport)
                                        request.session['chat_last_include_hotel'] = bool(inc_hotel)
                                        request.session['chat_last_extra_activity_ids'] = list(pending_extra_ids or [])
                                    except Exception:
                                        pass

                                if lang == 'fr':
                                    deterministic_text = "✅ Parfait — je pré-remplis la réservation et je l’envoie maintenant (en attente de validation admin)."
                                    if will_replace_existing:
                                        deterministic_text += " (Cela remplace ta réservation précédente.)"
                                else:
                                    deterministic_text = "✅ Great — I’m prefilling and submitting your booking request now (pending admin validation)."
                                    if will_replace_existing:
                                        deterministic_text += " (This replaces your previous reservation.)"

    if computed_hints_lines:
        system_prompt = system_prompt + "\n\nComputed booking state (ground truth; follow strictly):\n- " + "\n- ".join(computed_hints_lines)

    # If we have a deterministic booking/cancellation reply, return immediately (no LLM).
    if deterministic_text:
        final_action = action or {}

        if session_memory:
            try:
                session_history = request.session.get('chat_history') or []
                if not isinstance(session_history, list):
                    session_history = []
                session_history.append({'role': 'assistant', 'content': deterministic_text})
                request.session['chat_history'] = session_history[-session_history_max:]
            except Exception:
                pass

        def _gen_final():
            yield _sse_pack({'type': 'final', 'text': deterministic_text, 'action': final_action, 'model': None})

        resp = StreamingHttpResponse(_gen_final(), content_type='text/event-stream; charset=utf-8')
        resp['Cache-Control'] = 'no-cache'
        resp['X-Accel-Buffering'] = 'no'
        return resp

    def event_stream():
        full_text_parts: list[str] = []

        llm_available = bool(getattr(settings, 'HF_API_TOKEN', '') or getattr(settings, 'OPENAI_API_KEY', ''))
        if not llm_available:
            # Requirement: do not serve canned/deterministic replies when no model is configured.
            msg = (
                "Assistant IA non configuré pour le moment (clé modèle manquante). Réessaie plus tard."
                if lang == 'fr' else
                "AI assistant is not configured right now (missing model key). Please try again later."
            )
            yield _sse_pack({'type': 'final', 'text': msg, 'action': action or {}, 'model': None})
            return

        if getattr(settings, 'CHAT_DEBUG', False):
            yield _sse_pack({
                'type': 'debug',
                'request_id': request_id,
                'forced_llm': bool(getattr(settings, 'CHAT_FORCE_LLM', False)),
                'provider': 'huggingface' if getattr(settings, 'HF_API_TOKEN', '') else ('openai' if getattr(settings, 'OPENAI_API_KEY', '') else None),
                'model_config': getattr(settings, 'HF_MODEL', None) or None,
                'session_memory': session_memory,
            })

        # We always prefer the model for responses (no canned replies).

        # Prefer HuggingFace streaming when configured.
        used_model = None
        try:
            if settings.HF_API_TOKEN:
                hf_model = getattr(settings, 'HF_MODEL', None) or 'Qwen/Qwen2.5-7B-Instruct:fastest'
                hf_fallback = getattr(settings, 'HF_FALLBACK_MODEL', None) or ''
                max_tokens = int(getattr(settings, 'HF_MAX_NEW_TOKENS', 300) or 300)
                temperature = float(getattr(settings, 'HF_TEMPERATURE', 0.7) or 0.7)
                top_p = float(getattr(settings, 'HF_TOP_P', 0.95) or 0.95)

                def _run_stream(model_to_use: str):
                    for token_text in _hf_router_chat_completion_stream(
                        model_to_use,
                        settings.HF_API_TOKEN,
                        system_prompt,
                        message,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                    ):
                        token_text = _redact_secrets(token_text)
                        if not token_text:
                            continue
                        full_text_parts.append(token_text)
                        yield _sse_pack({'type': 'delta', 'text': token_text})

                used_model = hf_model
                try:
                    yield from _run_stream(hf_model)
                except Exception as e:
                    msg = str(e or '').lower()
                    if (not hf_fallback) and ('model_not_supported' in msg) and (HF_ROUTER_DEFAULT_MODEL != hf_model):
                        used_model = HF_ROUTER_DEFAULT_MODEL
                        yield from _run_stream(HF_ROUTER_DEFAULT_MODEL)
                    elif hf_fallback and hf_fallback != hf_model:
                        used_model = hf_fallback
                        yield from _run_stream(hf_fallback)
                    else:
                        raise

            elif (not settings.HF_API_TOKEN) and settings.OPENAI_API_KEY:
                used_model = getattr(settings, 'OPENAI_MODEL', None) or 'gpt-4o'
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ]

                response = client.chat.completions.create(
                    model=used_model,
                    messages=messages,
                    max_tokens=300,
                    temperature=0.7,
                    stream=True,
                )
                for event in response:
                    try:
                        delta = event.choices[0].delta
                        token_text = getattr(delta, 'content', None)
                    except Exception:
                        token_text = None
                    if not token_text:
                        continue
                    full_text_parts.append(token_text)
                    yield _sse_pack({'type': 'delta', 'text': token_text})
            else:
                # No model configured.
                if lang == 'fr':
                    fallback = "Le chatbot n’est pas configuré (clé HuggingFace/OpenAI manquante). Ajoute HF_API_TOKEN (et HF_MODEL) sur le serveur."
                else:
                    fallback = "Chat assistant isn’t configured (missing HuggingFace/OpenAI key). Set HF_API_TOKEN (and HF_MODEL) on the server."
                full_text_parts.append(fallback)
                yield _sse_pack({'type': 'delta', 'text': fallback})

        except Exception as e:
            logging.exception('[ai_chat_stream] streaming exception')

            err = None
            # Common case in this project: OpenAI key present but quota exhausted.
            try:
                is_rate_limit = isinstance(e, getattr(openai, 'RateLimitError', Exception))
            except Exception:
                is_rate_limit = False
            msg = str(e or '').lower()
            if is_rate_limit or 'insufficient_quota' in msg or 'exceeded your current quota' in msg:
                if lang == 'fr':
                    err = (
                        "Le quota OpenAI est dépassé sur le serveur. "
                        "Pour avoir un chat vraiment génératif + streaming, configure HuggingFace: HF_API_TOKEN et HF_MODEL."
                    )
                else:
                    err = (
                        "OpenAI quota is exceeded on the server. "
                        "For a real generative + streaming chat, configure HuggingFace: set HF_API_TOKEN and HF_MODEL."
                    )

            if not err:
                if lang == 'fr':
                    err = "Désolé — le modèle IA a eu un problème. Réessaie dans un instant."
                else:
                    err = "Sorry — the AI model had an issue. Please try again in a moment."

            err = _redact_secrets(err)

            full_text_parts = [err]
            yield _sse_pack({'type': 'delta', 'text': err})

        final_text = _redact_secrets(''.join(full_text_parts).strip())

        if not welcome_enabled:
            final_text = _strip_welcome_banner(final_text, country_label)
        # Remove any action markers if the model emits them.
        parsed_action, cleaned = parse_actions_from_response(final_text, country)
        parsed_action = _filter_navigation_action(
            parsed_action,
            country=country,
            booking_intent=booking_intent,
            start_date_req=start_date_req,
            end_date_req=end_date_req,
            persons_req=persons_req,
            allowed_tour_id=selected_tour_id,
            exclude_user=request.user,
        )
        final_action = action or parsed_action or {}
        final_text = cleaned.strip() if cleaned else final_text

        if session_memory:
            try:
                session_history = request.session.get('chat_history') or []
                if not isinstance(session_history, list):
                    session_history = []
                session_history.append({'role': 'assistant', 'content': final_text})
                request.session['chat_history'] = session_history[-session_history_max:]
            except Exception:
                pass

        yield _sse_pack({'type': 'final', 'text': final_text, 'action': final_action, 'model': used_model})

    resp = StreamingHttpResponse(event_stream(), content_type='text/event-stream; charset=utf-8')
    resp['Cache-Control'] = 'no-cache'
    resp['X-Accel-Buffering'] = 'no'
    return resp


def _normalize_country(country: str) -> str:
    country = (country or '').strip().lower()
    return country if country in {'morocco', 'ireland'} else 'morocco'


def _country_label(country: str) -> str:
    return 'Morocco' if country == 'morocco' else 'Ireland'


def _welcome_line(country_label: str) -> str:
    return (
        f"Hello! Your virtual assistant is ready for {country_label}. "
        "You can ask in English or French about tours, booking, and travel tips."
    )


def _is_starting_chat(message: str) -> bool:
    msg = (message or '').strip().lower()
    if not msg:
        return True
    if _is_greeting(msg):
        return True
    # Common “can I ask / puis-je demander” openers.
    starters = [
        'can i ask', 'can i ask?', 'may i ask', 'may i ask?',
        'je peux', 'je peux demander', 'puis-je', 'puis je', 'puis-je demander',
    ]
    return any(s in msg for s in starters)


def _welcome_should_show(request) -> bool:
    try:
        return not bool(request.session.get('chat_welcomed_v1'))
    except Exception:
        return True


def _mark_welcome_shown(request) -> None:
    try:
        request.session['chat_welcomed_v1'] = True
    except Exception:
        pass


def _strip_welcome_banner(text: str, country_label: str) -> str:
    """Remove the welcome line if the model repeats it."""
    s = (text or '').strip()
    if not s:
        return s

    # Exact match removal (most common case).
    wl = _welcome_line(country_label)
    if s.startswith(wl):
        s = s[len(wl):].lstrip()

    # Also handle variants that include extra spaces/newlines.
    pattern = re.compile(
        r"^Hello!\s+Your\s+virtual\s+assistant\s+is\s+ready\s+for\s+(Morocco|Ireland)\.\s+"
        r"You\s+can\s+ask\s+in\s+English\s+or\s+French\s+about\s+tours,\s+booking,\s+and\s+travel\s+tips\.\s*",
        flags=re.IGNORECASE,
    )
    s = pattern.sub('', s).lstrip()
    return s


def _build_booking_rules_context() -> str:
    return (
        "Booking rules: maximum stay is 5 days. "
        "Single-group rule: if there is any pending/booked reservation in a country, other tours in that country are unavailable for overlapping dates. "
        "There is no extra buffer after a reservation. "
        "Currency: all prices shown to users are in USD. "
        "Pricing rules: the base tour price is recalculated from the selected date range, traveler count, and chosen extras. "
        "Hotel and transport are optional add-ons unless explicitly selected (Full package = Transport + Hotel). "
        "Extra activities are optional add-ons; some are per day and some per trip (per person)."
    )


def _detect_reservation_manage_intent(message: str) -> str | None:
    """Return 'cancel' | 'change' | None based on FR/EN cues."""
    msg = (message or '').strip().lower()
    if not msg:
        return None
    if re.search(r"\b(cancel|cancellation|annul(?:er|e|es)?|supprim(?:er|e|es)?|delete)\b", msg):
        return 'cancel'
    if re.search(r"\b(change|changer|modif(?:ier|ie|ies)?|move|shift|resched(?:ule|uling)?|report(?:er|e|es)?)\b", msg):
        return 'change'
    return None


def _cancel_matching_user_reservation(
    *,
    user,
    country: str,
    start_date: date | None,
    end_date: date | None,
    destination_hint: str | None,
    tour_id_hint: int | None,
):
    """Cancel a best-match active reservation for a user.

    Returns (reservation, status) where status is one of:
      'cancelled', 'none', 'ambiguous'
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return None, 'none'
    country = _normalize_country(country)

    try:
        qs = Reservation.objects.filter(
            user=user,
            tour__country=country,
        ).exclude(status__in=['cancelled', 'rejected', 'completed']).select_related('tour', 'tour__destination').order_by('-created_at')
    except Exception:
        return None, 'none'

    if tour_id_hint:
        qs = qs.filter(tour_id=int(tour_id_hint))
    elif destination_hint:
        qs = qs.filter(
            Q(tour__destination__name__icontains=destination_hint) |
            Q(tour__title__icontains=destination_hint)
        )

    if start_date and end_date:
        qs = qs.filter(start_date__lt=end_date, end_date__gt=start_date)

    candidates = list(qs[:3])
    if not candidates:
        return None, 'none'
    if len(candidates) > 1 and not (tour_id_hint or destination_hint or (start_date and end_date)):
        return None, 'ambiguous'

    r = candidates[0]
    try:
        r.status = 'cancelled'
        r.save(update_fields=['status'])
        return r, 'cancelled'
    except Exception:
        return None, 'none'


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
    # Normalize common ordinal tokens that can appear as separate words (e.g. "5 may th").
    msg_lower = re.sub(r'\b(st|nd|rd|th)\b', '', msg_lower)
    msg_lower = re.sub(r'\s+', ' ', msg_lower).strip()

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

    # English: from 25 to 28 april (month at end)
    if not (start_date and end_date):
        m = re.search(
            r'(?:from\s*)?(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:to|until|\-|–|—)\s*'
            r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*'
            r'(january|jan|janvier|february|feb|février|fevrier|march|mar|mars|april|apr|avril|may|mai|june|jun|juin|july|jul|juillet|august|aug|août|aout|september|sep|sept|septembre|october|oct|octobre|november|nov|novembre|december|dec|décembre|decembre)'
            r'(?:\s*(\d{4}))?',
            msg_lower,
        )
        if m:
            try:
                sday, eday, mon, year = m.groups()
                y = int(year) if year else date.today().year
                mm = parse_month(mon) or 1
                start_date = date(y, mm, int(sday))
                end_date = date(y, mm, int(eday))
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

    # French: du 25 au 28 avril (month at end)
    if not (start_date and end_date):
        m = re.search(
            r'(?:du\s*)?(\d{1,2})\s*(?:au|à|a|\-|–|—)\s*(\d{1,2})\s*'
            r'(january|jan|janvier|february|feb|février|fevrier|march|mar|mars|april|apr|avril|may|mai|june|jun|juin|july|jul|juillet|august|aug|août|aout|september|sep|sept|septembre|october|oct|octobre|november|nov|novembre|december|dec|décembre|decembre)'
            r'(?:\s*(\d{4}))?',
            msg_lower,
        )
        if m:
            try:
                sday, eday, mon, year = m.groups()
                y = int(year) if year else date.today().year
                mm = parse_month(mon) or 1
                start_date = date(y, mm, int(sday))
                end_date = date(y, mm, int(eday))
            except Exception:
                start_date = end_date = None

    # Month-first: May 5 to May 8 (EN/FR month tokens supported)
    if not (start_date and end_date):
        m = re.search(
            r'(january|jan|janvier|february|feb|février|fevrier|march|mar|mars|april|apr|avril|may|mai|june|jun|juin|july|jul|juillet|august|aug|août|aout|september|sep|sept|septembre|october|oct|octobre|november|nov|novembre|december|dec|décembre|decembre)'
            r'\s*(\d{1,2})\s*(?:to|until|au|à|a|\-|–|—)\s*'
            r'(january|jan|janvier|february|feb|février|fevrier|march|mar|mars|april|apr|avril|may|mai|june|jun|juin|july|jul|juillet|august|aug|août|aout|september|sep|sept|septembre|october|oct|octobre|november|nov|novembre|december|dec|décembre|decembre)'
            r'\s*(\d{1,2})'
            r'(?:\s*(\d{4}))?',
            msg_lower,
        )
        if m:
            try:
                smonth, sday, emonth, eday, year = m.groups()
                y = int(year) if year else date.today().year
                start_date = date(y, parse_month(smonth) or 1, int(sday))
                end_date = date(y, parse_month(emonth) or 1, int(eday))
            except Exception:
                start_date = end_date = None

    # If year is omitted and the date is clearly in the past, roll to next year.
    if start_date and end_date and (start_date.year == date.today().year):
        try:
            if (start_date < date.today() - timedelta(days=7)) and (str(date.today().year) not in msg_lower):
                start_date = date(start_date.year + 1, start_date.month, start_date.day)
                end_date = date(end_date.year + 1, end_date.month, end_date.day)
        except Exception:
            pass

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


def _extract_day_range_without_month(message: str, ref: date | None) -> tuple[date | None, date | None]:
    """Extract a day-only range like 'from 8 to 11' and apply ref month/year.

    Intended for follow-up messages where the user changes only the day while
    keeping the same month as the ongoing (pending) booking.
    """
    if not ref:
        return None, None

    msg = (message or '').lower().strip()
    if not msg:
        return None, None

    # Normalize ordinals like "8th".
    msg = re.sub(r'\b(st|nd|rd|th)\b', '', msg)
    msg = re.sub(r'\s+', ' ', msg).strip()

    m = re.search(r'(?:from\s*)?(\d{1,2})\s*(?:to|until|au|à|a|\-|–|—)\s*(\d{1,2})\b', msg)
    if not m:
        # French short form sometimes: "du 8 au 11"
        m = re.search(r'(?:du\s*)?(\d{1,2})\s*(?:au|à|a|\-|–|—)\s*(\d{1,2})\b', msg)
    if not m:
        return None, None

    try:
        sday = int(m.group(1))
        eday = int(m.group(2))
        start_date = date(ref.year, ref.month, sday)
        end_date = date(ref.year, ref.month, eday)
    except Exception:
        return None, None

    if end_date < start_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date


def _extract_booking_addons(message: str) -> dict:
    """Extract add-on preferences from a free-form message.

    Returns dict with keys:
      full_package (bool|None), include_transport (bool|None), include_hotel (bool|None), extras (bool|None)
    """
    msg = (message or '').lower()
    msg = re.sub(r'\s+', ' ', msg).strip()

    full_package = None
    include_transport = None
    include_hotel = None
    extras = None

    if re.search(r'\b(full\s*package|package\s*complet|pack\s*complet|tout\s*inclus|all\s*inclusive|all\s*included)\b', msg):
        full_package = True
        include_transport = True
        include_hotel = True

    if re.search(r'\b(transport|car|driver|pickup|pick\s*up)\b', msg):
        include_transport = True
    if re.search(r'\b(hotel|h[oô]tel|accommodation|hébergement|hebergement)\b', msg):
        include_hotel = True

    # Explicit negatives
    if re.search(r'\b(without|no|sans)\b[^\n]{0,40}\b(extra|extras|extra\s*activities|activit[eé]s?\s*extra|activit[eé]s?\s*suppl[eé]mentaires)\b', msg):
        extras = False
    elif re.search(r'\b(with|avec)\b[^\n]{0,40}\b(extra|extras|extra\s*activities|activit[eé]s?\s*extra)\b', msg):
        extras = True

    return {
        'full_package': full_package,
        'include_transport': include_transport,
        'include_hotel': include_hotel,
        'extras': extras,
    }


def _select_single_extra_activity_id(tour: Tour | None, message: str) -> int | None:
    """Return a single matching TourExtraActivity id for this tour, or None.

    Matching is conservative to avoid accidental selections.
    """
    if not tour or not message:
        return None
    msg = (message or '').lower()
    msg = re.sub(r"[^a-z0-9\s\-']+", ' ', msg)
    msg = re.sub(r'\s+', ' ', msg).strip()
    if not msg:
        return None

    try:
        extras = list(tour.extra_activities.filter(is_active=True).only('id', 'title'))
    except Exception:
        extras = []
    if not extras:
        return None

    best_id = None
    best_score = 0
    for ea in extras:
        title = (getattr(ea, 'title', '') or '').lower().strip()
        if not title:
            continue

        score = 0
        if title in msg:
            score = 100 + len(title)
        else:
            tokens = [t for t in re.findall(r"[a-z0-9']+", title) if len(t) >= 4]
            if tokens:
                score = sum(1 for t in tokens if t in msg) * 10

        if score > best_score:
            best_score = score
            best_id = int(ea.id)

    return best_id if best_score >= 10 else None


def _format_tour_extra_activities(tour: Tour | None, limit: int = 6) -> str:
    if not tour:
        return ''
    try:
        extras = list(tour.extra_activities.filter(is_active=True).only('title').order_by('id'))
    except Exception:
        extras = []
    titles = [str(getattr(ea, 'title', '') or '').strip() for ea in extras if str(getattr(ea, 'title', '') or '').strip()]
    if not titles:
        return ''
    titles = titles[: max(1, int(limit))]
    return '; '.join(titles)


def _extract_payment_method(message: str) -> str | None:
    """Return 'cash', 'card', or None from a short FR/EN message."""
    msg = (message or '').strip().lower()
    if not msg:
        return None

    # Prefer explicit mentions.
    if re.search(r"\b(card|carte|cb|credit|visa|mastercard)\b", msg):
        return 'card'
    if re.search(r"\b(cash|esp[eè]ces?|espece|liquide|sur\s*place)\b", msg):
        return 'cash'
    return None


_CHAT_PENDING_BOOKING_KEY = 'chat_pending_booking_v1'


def _get_pending_booking(request) -> dict | None:
    try:
        pending = request.session.get(_CHAT_PENDING_BOOKING_KEY)
    except Exception:
        return None
    return pending if isinstance(pending, dict) else None


def _set_pending_booking(request, pending: dict | None) -> None:
    try:
        if pending:
            request.session[_CHAT_PENDING_BOOKING_KEY] = pending
        else:
            request.session.pop(_CHAT_PENDING_BOOKING_KEY, None)
    except Exception:
        return


def _date_from_iso(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(str(s), '%Y-%m-%d').date()
    except Exception:
        return None


def _get_country_blocked_ranges(country: str, buffer_days: int = 0, exclude_user=None):
    """Returns list of blocked date ranges (start, end_inclusive) for a country.

    If exclude_user is provided, their reservations are ignored (useful when a user
    is updating their own booking and we only want to block other users).
    """
    country = _normalize_country(country)
    active_statuses = ['pending', 'booked']
    try:
        reservations = Reservation.objects.filter(
            tour__country=country,
            status__in=active_statuses,
        )
        if exclude_user and getattr(exclude_user, 'is_authenticated', False):
            reservations = reservations.exclude(user=exclude_user)
        reservations = reservations.order_by('start_date')
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


def _is_range_available(country: str, start_date: date, end_date: date, buffer_days: int = 0, exclude_user=None) -> bool:
    """Return True iff there is no DB reservation blocking the requested window.

    IMPORTANT: availability must be based only on persisted `Reservation` rows in DB
    (pending/booked), never on chat/session text.
    """
    if not start_date or not end_date:
        return False
    country = _normalize_country(country)

    try:
        buffer_days = int(buffer_days)
    except Exception:
        buffer_days = 0
    buffer_days = max(0, buffer_days)

    window_start = start_date - timedelta(days=buffer_days)
    active_statuses = ['pending', 'booked']

    try:
        qs = Reservation.objects.filter(
            tour__country=country,
            status__in=active_statuses,
            start_date__lte=end_date,
            end_date__gte=window_start,
        )
        if exclude_user and getattr(exclude_user, 'is_authenticated', False):
            qs = qs.exclude(user=exclude_user)
        return not qs.exists()
    except Exception:
        # Fail-open for the assistant (don't wrongly claim "unavailable" on errors).
        return True


def _user_break_buffer_ok(user, country: str, start_date: date, buffer_days: int = 0) -> bool:
    """Enforce a per-user buffer after their last reservation end date.

    This is separate from the global single-group rule (which blocks other users).
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return True
    if not start_date:
        return True
    try:
        if int(buffer_days) <= 0:
            return True
    except Exception:
        return True
    country = _normalize_country(country)
    try:
        last = (
            Reservation.objects.filter(user=user, tour__country=country)
            .exclude(status__in=['cancelled', 'rejected'])
            .order_by('-end_date')
            .only('end_date')
            .first()
        )
    except Exception:
        return True
    if not last or not getattr(last, 'end_date', None):
        return True
    try:
        return start_date >= (last.end_date + timedelta(days=int(buffer_days)))
    except Exception:
        return True


def _user_has_overlapping_reservation(user, country: str, start_date: date, end_date: date) -> bool:
    """True if user already has an active reservation overlapping [start_date, end_date)."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if not start_date or not end_date:
        return False
    country = _normalize_country(country)
    try:
        return Reservation.objects.filter(
            user=user,
            tour__country=country,
            status__in=['pending', 'booked', 'completed'],
        ).filter(
            start_date__lt=end_date,
            end_date__gt=start_date,
        ).exists()
    except Exception:
        return False


def _suggest_available_ranges(country: str, nights: int = 5, horizon_days: int = 120, limit: int = 4, buffer_days: int = 0):
    """Suggest next available continuous date ranges for a given stay length."""
    country = _normalize_country(country)
    # Let users book far in the future; suggestions should cover more than ~4 months.
    horizon_days = max(int(horizon_days), 365)
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


def _suggest_available_ranges_near(
    country: str,
    anchor: date,
    *,
    nights: int,
    window_days: int = 180,
    limit: int = 4,
    buffer_days: int = 3,
    exclude_user=None,
):
    """Suggest available ranges near an anchor date (useful for far-future requests)."""
    country = _normalize_country(country)
    if not anchor:
        return []
    nights = max(1, min(int(nights), 11))
    today = date.today()
    start_scan = max(today, anchor - timedelta(days=14))
    end_scan = anchor + timedelta(days=int(window_days))

    suggestions = []
    d = start_scan
    while d <= end_scan and len(suggestions) < limit:
        start = d
        end = d + timedelta(days=nights)
        if _is_range_available(country, start, end, buffer_days=buffer_days, exclude_user=exclude_user):
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

    # Country-level content (hero, etc.)
    country_content_lines = []
    try:
        cc = CountryContent.objects.filter(country=country).first()
        if cc:
            if getattr(cc, 'hero_title', None):
                country_content_lines.append(f"Hero title: {cc.hero_title}")
            if getattr(cc, 'hero_subtitle', None):
                subtitle = (cc.hero_subtitle or '').strip().replace('\n', ' ')
                if subtitle:
                    country_content_lines.append(f"Hero subtitle: {subtitle[:280]}")
    except (OperationalError, ProgrammingError):
        country_content_lines = []

    # Main page sections
    section_lines = []
    try:
        sections = list(Section.objects.filter(country=country).order_by('order')[:8])
        for s in sections:
            title = (getattr(s, 'title', '') or '').strip()
            content = (getattr(s, 'content', '') or '').strip().replace('\n', ' ')
            if not title and not content:
                continue
            if content:
                section_lines.append(f"- {title}: {content[:320]}")
            else:
                section_lines.append(f"- {title}")
    except (OperationalError, ProgrammingError):
        section_lines = []

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
            included_compact = _compact_items_list(getattr(t, 'included', ''), max_items=6)
            if included_compact:
                line += f" Included: {included_compact}."
            not_included_compact = _compact_items_list(getattr(t, 'not_included', ''), max_items=6)
            if not_included_compact:
                line += f" Not included: {not_included_compact}."
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
    if country_content_lines:
        parts.append("Site content:\n" + "\n".join(country_content_lines))
    if section_lines:
        parts.append("Site sections:\n" + "\n".join(section_lines))
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
        # Never pick a random tour; require an explicit match.
        return None
    except (OperationalError, ProgrammingError):
        return None


def _extract_explicit_tour_id(message: str) -> int | None:
    msg = (message or '').strip()
    if not msg:
        return None

    patterns = [
        r"/tour/(\d+)/?",            # /tour/12/
        r"\btour\s*#?\s*(\d+)\b",  # tour 12 / tour #12
        r"\bid\s*#?\s*(\d+)\b",    # id 12
    ]
    for p in patterns:
        m = re.search(p, msg, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None


def _tours_for_hint(country: str, hint: str):
    country = _normalize_country(country)
    hint = (hint or '').strip()
    if not hint:
        return []
    try:
        return list(
            Tour.objects.filter(country=country)
            .select_related('destination')
            .filter(Q(destination__name__icontains=hint) | Q(title__icontains=hint))
            .order_by('id')
        )
    except (OperationalError, ProgrammingError):
        return []


def _select_tour_for_booking(country: str, message: str, destination_hint: str | None):
    """Return (tour, status, candidates).

    status: 'ok' | 'unknown_tour' | 'no_match' | 'multiple'
    """
    country = _normalize_country(country)
    explicit_id = _extract_explicit_tour_id(message)
    if explicit_id:
        try:
            t = Tour.objects.filter(country=country).select_related('destination').filter(id=explicit_id).first()
        except (OperationalError, ProgrammingError):
            t = None
        if not t:
            return None, 'unknown_tour', []
        return t, 'ok', [t]

    hint = (destination_hint or '').strip()
    if not hint:
        return None, 'no_match', []

    candidates = _tours_for_hint(country, hint)
    if not candidates:
        return None, 'no_match', []
    if len(candidates) == 1:
        return candidates[0], 'ok', candidates
    return None, 'multiple', candidates


def _filter_navigation_action(
    action: dict,
    *,
    country: str,
    booking_intent: bool,
    start_date_req,
    end_date_req,
    persons_req,
    allowed_tour_id: int | None,
    exclude_user=None,
) -> dict:
    if not action or not isinstance(action, dict):
        return {}
    nav = action.get('navigate')
    if not nav:
        return action

    m = re.match(r'^/tour/(\d+)/?$', str(nav).strip())
    if not m:
        action.pop('navigate', None)
        action.pop('prefill', None)
        return action

    try:
        nav_id = int(m.group(1))
    except Exception:
        action.pop('navigate', None)
        action.pop('prefill', None)
        return action

    if not booking_intent or not (start_date_req and end_date_req and persons_req):
        action.pop('navigate', None)
        action.pop('prefill', None)
        return action

    requested_nights = max(0, (end_date_req - start_date_req).days)
    if requested_nights > 5 or (not _is_range_available(country, start_date_req, end_date_req, buffer_days=0, exclude_user=exclude_user)):
        action.pop('navigate', None)
        action.pop('prefill', None)
        return action

    if not allowed_tour_id or nav_id != int(allowed_tour_id):
        action.pop('navigate', None)
        action.pop('prefill', None)
        return action

    # Ensure prefill exists and is consistent.
    action['navigate'] = f"/tour/{nav_id}/"
    action['prefill'] = {
        'start_date': start_date_req.strftime('%Y-%m-%d'),
        'end_date': end_date_req.strftime('%Y-%m-%d'),
        'persons': int(persons_req),
    }
    return action


def _find_relevant_tours(country: str, destination_hint: str | None, limit: int = 3):
    country = _normalize_country(country)
    hint = (destination_hint or '').strip()
    if not hint:
        return []
    try:
        qs = (
            Tour.objects.filter(country=country)
            .select_related('destination')
            .filter(
                Q(destination__name__icontains=hint) |
                Q(title__icontains=hint)
            )
            .order_by('id')
        )
        return list(qs[: max(1, int(limit))])
    except (OperationalError, ProgrammingError):
        return []


def _resolve_destination_hint(country: str, message: str, parsed_hint: str | None):
    """Try to resolve a destination/city from the message or DB."""
    country = _normalize_country(country)
    msg = (message or '').strip()
    if parsed_hint:
        hint = (parsed_hint or '').strip()
        # Only accept parsed hints if they actually map to a tour/destination on this site.
        if hint and _tours_for_hint(country, hint):
            return hint
        return None
    if not msg:
        return None

    # If user replies with a single word/city like "Rabat"
    if len(msg) <= 40 and ' ' not in msg:
        # Avoid poisoning the session with greetings / smalltalk.
        if _is_greeting(msg) or _is_smalltalk(msg):
            return None
        try:
            # Prefer destinations that actually have tours in this country.
            dest = (
                Destination.objects.filter(tours__country=country)
                .distinct()
                .filter(name__iexact=msg)
                .first()
            )
            if dest:
                return dest.name

            # Fallback: a tour title might match even if destination table isn't perfect.
            has_tour = Tour.objects.filter(country=country).filter(
                Q(destination__name__icontains=msg) | Q(title__icontains=msg)
            ).exists()
            return msg if has_tour else None
        except (OperationalError, ProgrammingError):
            return None

    # Otherwise try to match any destination name contained in the message.
    try:
        msg_lower = msg.lower()
        destinations = list(
            Destination.objects.filter(tours__country=country)
            .distinct()
            .order_by('name')
        )
        for d in destinations:
            name = (d.name or '').strip()
            if name and name.lower() in msg_lower:
                return d.name
    except (OperationalError, ProgrammingError):
        pass
    return None


def _detect_info_intent(message: str):
    """Return set like {'price','activities','included','excluded'} based on the message."""
    msg = (message or '').lower()
    intents = set()
    if any(w in msg for w in ['price', 'cost', 'prix', 'tarif', 'per night', 'par nuit', 'night', 'nuit']):
        intents.add('price')
    if any(w in msg for w in [
        'not included', 'not include', "isn't included", "is not included",
        'excluded', 'excludes', 'exclude', 'what is not included', "what's not included", 'whats not included',
        'non inclus', 'non incluse', 'non incluses', 'pas inclus', "n'est pas inclus",
    ]):
        intents.add('excluded')
    if any(w in msg for w in ['activity', 'activities', 'activités', 'activites', 'included', 'includes', 'inclus', 'comprend', 'what is included', 'inclusions', 'include']):
        intents.add('activities')
        intents.add('included')
    if any(w in msg for w in ['transport', 'hotel', 'hébergement', 'hebergement']):
        intents.add('included')
    return intents


def _compact_items_list(text: str, max_items: int = 6) -> str:
    raw = (text or '').strip()
    if not raw:
        return ''

    # Prefer line-separated items; fall back to comma-separated.
    parts = [p.strip() for p in re.split(r"[\r\n]+", raw) if p.strip()]
    if len(parts) == 1 and ',' in parts[0]:
        parts = [p.strip() for p in parts[0].split(',') if p.strip()]

    cleaned = []
    for p in parts:
        p = p.strip().lstrip('-•*\t ').strip()
        if p:
            cleaned.append(re.sub(r"\s+", " ", p))
    if not cleaned:
        return ''

    shown = cleaned[:max_items]
    s = ", ".join(shown)
    if len(cleaned) > max_items:
        s += ", …"
    return s


def _format_tour_info_reply(
    country: str,
    tours,
    intents: set[str],
    lang: str,
    include_booking_tip: bool = False,
    include_admin_hint: bool = False,
) -> str:
    country_label = _country_label(country)
    if not tours:
        if lang == 'fr':
            return f"Je n’ai trouvé aucun tour correspondant sur le site {country_label}. Tu peux me donner une autre ville/destination ?"
        return f"I couldn’t find a matching tour on the {country_label} site. Can you share another destination/city?"

    def _is_placeholder(text: str) -> bool:
        t = (text or '').strip().lower()
        return (not t) or t in {'test', 'todo', 'tbd', 'lorem', 'lorem ipsum'}

    lines = []
    for t in tours:
        dest_name = getattr(t.destination, 'name', '') or ''
        header = f"{t.title} ({dest_name})" if dest_name else t.title

        if 'price' in intents:
            if lang == 'fr':
                line = f"- {header}: {t.price_per_night} USD par nuit."
            else:
                line = f"- {header}: {t.price_per_night} USD per night."
            if getattr(t, 'is_promotion', False) and getattr(t, 'discount_percent', 0):
                if lang == 'fr':
                    line += f" Promo: -{t.discount_percent}%."
                else:
                    line += f" Promo: -{t.discount_percent}%."
            lines.append(line)

        if 'activities' in intents or 'included' in intents or 'excluded' in intents:
            details = []
            transport_val = (getattr(t, 'transport', '') or '').strip()
            hotel_val = (getattr(t, 'hotel', '') or '').strip()
            activities_val = (getattr(t, 'activities', '') or '').strip()
            included_val = (getattr(t, 'included', '') or '').strip()
            not_included_val = (getattr(t, 'not_included', '') or '').strip()

            if transport_val:
                details.append(("Transport" if lang == 'en' else "Transport") + f": {transport_val}")
            if hotel_val:
                details.append(("Hotel" if lang == 'en' else "Hôtel") + f": {hotel_val}")
            if activities_val:
                activities = [a.strip() for a in activities_val.replace('\n', ',').split(',') if a.strip()]
                if activities:
                    if lang == 'fr':
                        details.append("Activités: " + ", ".join(activities[:10]) + ("" if len(activities) <= 10 else ", …"))
                    else:
                        details.append("Activities: " + ", ".join(activities[:10]) + ("" if len(activities) <= 10 else ", …"))

            # Include structured inclusions/exclusions if available.
            if included_val and ('included' in intents or 'activities' in intents):
                label = "Included" if lang == 'en' else "Inclus"
                compact = _compact_items_list(included_val, max_items=8)
                if compact:
                    details.append(f"{label}: {compact}")
            if not_included_val:
                label = "Not included" if lang == 'en' else "Non inclus"
                compact = _compact_items_list(not_included_val, max_items=8)
                if compact:
                    details.append(f"{label}: {compact}")

            if details:
                lines.append(f"- {header}: " + " | ".join(details))
            else:
                # Fallback: sometimes the tour/destination description contains inclusions.
                tour_desc = (getattr(t, 'description', '') or '').strip()
                dest_desc = (getattr(getattr(t, 'destination', None), 'description', '') or '').strip()
                fallback_text = None
                if not _is_placeholder(tour_desc) and len(tour_desc) >= 25:
                    fallback_text = tour_desc
                elif not _is_placeholder(dest_desc) and len(dest_desc) >= 25:
                    fallback_text = dest_desc

                if fallback_text:
                    if lang == 'fr':
                        lines.append(f"- {header}: Je n’ai pas une liste d’activités/inclusions structurée, mais voici la description disponible: {fallback_text[:260]}")
                    else:
                        lines.append(f"- {header}: I don’t have a structured inclusions/activities list, but here’s the available description: {fallback_text[:260]}")
                else:
                    if lang == 'fr':
                        line = f"- {header}: Les activités/inclusions ne sont pas encore renseignées pour ce tour sur le site."
                    else:
                        line = f"- {header}: Activities/inclusions aren’t filled in for this tour on the site yet."

                    # If the user asked about activities (not price), still provide the price as a helpful factual detail.
                    if 'price' not in intents and getattr(t, 'price_per_night', None) is not None:
                        if lang == 'fr':
                            line += f" Prix actuel: {t.price_per_night} par nuit."
                        else:
                            line += f" Current price: {t.price_per_night} per night."
                    if include_admin_hint:
                        try:
                            admin_url = reverse('admin:core_tour_change', args=[t.id])
                            if lang == 'fr':
                                line += f" (Admin: {admin_url})"
                            else:
                                line += f" (Admin: {admin_url})"
                        except Exception:
                            pass
                    lines.append(line)

    if include_booking_tip:
        if lang == 'fr':
            lines.append("Si tu me donnes tes dates + nombre de personnes, je peux aussi vérifier la disponibilité et pré-remplir la réservation.")
        else:
            lines.append("If you share your dates + number of people, I can also check availability and prefill the booking.")

    return "\n".join(lines)


def home(request):
    q = request.GET.get('q', '').strip()
    # Backward compatible: old param `date` maps to `start_date`
    start_date_str = (request.GET.get('start_date') or request.GET.get('date') or '').strip()
    end_date_str = (request.GET.get('end_date') or '').strip()

    country = get_country_from_site(request)
    try:
        tours = Tour.objects.filter(country=country).select_related('destination').prefetch_related('activity_cards')
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

            active_statuses = ['pending', 'booked']

            try:
                has_conflict = Reservation.objects.filter(
                    tour__country=country,
                    status__in=active_statuses,
                    start_date__lte=range_end,
                    end_date__gte=start_date_val,
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
                ).exclude(status__in=["rejected", "cancelled", "completed"]).order_by("-created_at").first()
            except (OperationalError, ProgrammingError):
                tour.user_reservation = None
        tour.featured_activity_cards = list(tour.activity_cards.filter(is_active=True).order_by('display_order', 'id')[:2])
        if not tour.featured_activity_cards and tour.activities:
            tour.fallback_activity_labels = [
                a.strip() for a in (tour.activities or '').replace('\n', ',').split(',') if a.strip()
            ][:3]
        else:
            tour.fallback_activity_labels = []

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

    try:
        # Privacy: do not persist or return chat history.
        return JsonResponse({'history': []})
    except (OperationalError, ProgrammingError):
        return JsonResponse({'history': []})
def tour_detail_legacy(request, tour_id: int):
    """Legacy /tour/<id>/ endpoint that redirects to the slug URL."""
    country = get_country_from_site(request)
    tour = get_object_or_404(Tour, id=tour_id, country=country)
    return HttpResponsePermanentRedirect(reverse('tour_detail', args=[tour.slug]))


def tour_detail(request, tour_slug: str):
    country = get_country_from_site(request)
    tour = get_object_or_404(
        Tour.objects.select_related('destination').prefetch_related('activity_cards', 'extra_activities'),
        slug=tour_slug,
        country=country,
    )

    reservation = None
    if request.user.is_authenticated:
        reservation = Reservation.objects.filter(
            user=request.user,
            tour=tour
        ).exclude(status__in=["rejected", "cancelled", "completed"]).order_by("-created_at").first()

    selected_extra_ids: list[int] = []
    if reservation:
        for item in getattr(reservation, 'selected_extra_activities', []) or []:
            try:
                selected_extra_ids.append(int((item or {}).get('id')))
            except Exception:
                continue

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
    if request.user.is_authenticated:
        active_reservations = active_reservations.exclude(user=request.user)

    disabled_ranges = [
        {
            "from": r.start_date.isoformat(),
            "to": r.end_date.isoformat(),
        }
        for r in active_reservations.order_by('start_date')
    ]

    tour.promo_price = None
    if tour.is_promotion and tour.discount_percent > 0:
        discount = (Decimal(100) - Decimal(tour.discount_percent)) / Decimal(100)
        tour.promo_price = (Decimal(tour.price_per_night) * discount).quantize(Decimal("0.01"))
    structured_activities = list(tour.activity_cards.filter(is_active=True).order_by('day_number', 'display_order', 'id'))
    extra_activities = list(tour.extra_activities.filter(is_active=True).order_by('id'))
    extra_itinerary_options = [_serialize_extra_itinerary_option(extra) for extra in extra_activities]
    activity_gallery_cards = _build_activity_gallery_cards(tour)
    itinerary_days = _build_itinerary_days(tour, selected_extra_ids=selected_extra_ids)
    return render(request, "booking.html", {
        "tour": tour,
        "reservation": reservation,
        "disabled_ranges": disabled_ranges,
        "today": date.today(),  # ✅ IMPORTANT
        "STRIPE_PUBLIC_KEY": settings.STRIPE_PUBLIC_KEY,
        "activities_list": [a.strip() for a in (tour.activities or '').replace('\n', ',').split(',') if a.strip()],
        "structured_activities": structured_activities,
        "extra_activities": extra_activities,
        "extra_itinerary_options": extra_itinerary_options,
        "activity_gallery_cards": activity_gallery_cards,
        "itinerary_days": itinerary_days,
        "selected_extra_ids": selected_extra_ids,
        "booking_max_nights": 5,
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

    message = _redact_secrets((payload.get('message') or '').strip())
    if not message:
        return JsonResponse({'error': 'Message cannot be empty.'}, status=400)

    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return JsonResponse({
            'reply': 'Please log in to use the chat and to book.',
            'action': {'navigate': reverse('login')},
        }, status=200)

    llm_available = bool(getattr(settings, 'HF_API_TOKEN', '') or getattr(settings, 'OPENAI_API_KEY', ''))
    if not llm_available:
        return JsonResponse({'error': 'AI assistant not configured.'}, status=503)

    country = _normalize_country(get_country_from_site(request) or 'morocco')
    country_label = _country_label(country)
    lang = getattr(settings, 'CHAT_FORCE_LANGUAGE', '') or _detect_language(message)

    welcome_should_show = _welcome_should_show(request)
    welcome_enabled = bool(welcome_should_show and _is_starting_chat(message))
    if welcome_enabled:
        _mark_welcome_shown(request)

    request_id = uuid.uuid4().hex
    session_memory = bool(getattr(settings, 'CHAT_SESSION_MEMORY', False))
    session_history_max = int(getattr(settings, 'CHAT_SESSION_HISTORY_MAX', 8) or 8)
    session_history: list[dict] = []
    if session_memory:
        try:
            session_history = request.session.get('chat_history') or []
            if not isinstance(session_history, list):
                session_history = []
        except Exception:
            session_history = []
        session_history.append({'role': 'user', 'content': message})
        request.session['chat_history'] = session_history[-session_history_max:]

    action: dict = {}
    used_model = None
    deterministic_text: str | None = None

    msg_lower = message.lower()
    keyword_booking_intent = any(k in msg_lower for k in ['book', 'booking', 'reserve', 'reservation', 'réserver', 'reserver'])
    start_date_req, end_date_req, persons_req, parsed_dest = _extract_booking_details(message)
    payment_method_req = _extract_payment_method(message)
    addons_req = _extract_booking_addons(message)

    destination_hint = None
    if not _is_greeting(message) and not _is_smalltalk(message):
        destination_hint = _resolve_destination_hint(country, message, parsed_dest)

    pending = _get_pending_booking(request)
    pending_extra_ids: list[str] = []
    if pending:
        # Follow-up date updates like "from 8th to 11th" may omit the month/year.
        # Infer them from the pending booking month to keep the flow deterministic.
        if not (start_date_req and end_date_req):
            ref = _date_from_iso(pending.get('start_date')) or _date_from_iso(pending.get('end_date'))
            sd2, ed2 = _extract_day_range_without_month(message, ref)
            if sd2 and ed2:
                start_date_req, end_date_req = sd2, ed2

        if not destination_hint:
            destination_hint = (pending.get('destination') or None)
        if not persons_req:
            try:
                persons_req = int(pending.get('persons') or 0) or None
            except Exception:
                persons_req = None
        if not start_date_req:
            start_date_req = _date_from_iso(pending.get('start_date'))
        if not end_date_req:
            end_date_req = _date_from_iso(pending.get('end_date'))
        if not payment_method_req:
            pm = (pending.get('payment_method') or '').strip().lower()
            payment_method_req = pm if pm in {'cash', 'card'} else None

        # Merge add-ons from pending unless explicitly provided in current message.
        for key in ['full_package', 'include_transport', 'include_hotel', 'extras']:
            if addons_req.get(key) is None and isinstance(pending.get(key), (bool, type(None))):
                addons_req[key] = pending.get(key)

        _pei = pending.get('extra_activity_ids')
        if isinstance(_pei, list):
            pending_extra_ids = [str(x).strip() for x in _pei if str(x).strip()]

    booking_hint = (parsed_dest or destination_hint)
    has_core_booking_fields = bool(booking_hint and start_date_req and end_date_req and persons_req)
    booking_intent = bool(keyword_booking_intent or has_core_booking_fields or pending)

    # Reservation management (cancel / change) should be handled without looping.
    manage_intent = _detect_reservation_manage_intent(message)
    tour_id_hint = None
    try:
        if pending and pending.get('tour_id'):
            tour_id_hint = int(pending.get('tour_id'))
        elif session_memory:
            tour_id_hint = int(request.session.get('chat_last_tour_id') or 0) or None
    except Exception:
        tour_id_hint = None

    if manage_intent == 'cancel':
        r, st = _cancel_matching_user_reservation(
            user=request.user,
            country=country,
            start_date=start_date_req,
            end_date=end_date_req,
            destination_hint=booking_hint,
            tour_id_hint=tour_id_hint,
        )
        _set_pending_booking(request, None)
        if st == 'cancelled' and r:
            tour_title = getattr(getattr(r, 'tour', None), 'title', '') or 'your tour'
            deterministic_text = (
                f"✅ C’est fait — j’ai annulé ta réservation pour “{tour_title}”." if lang == 'fr'
                else f"✅ Done — I cancelled your reservation for “{tour_title}”."
            )
        elif st == 'ambiguous':
            deterministic_text = (
                "J’ai trouvé plusieurs réservations actives. Tu veux annuler laquelle (ville ou dates) ?" if lang == 'fr'
                else "I found multiple active reservations. Which one should I cancel (city or dates)?"
            )
        else:
            deterministic_text = (
                "Je ne trouve aucune réservation active à annuler pour le moment." if lang == 'fr'
                else "I can’t find an active reservation to cancel right now."
            )

    computed_hints_lines: list[str] = []
    if (not deterministic_text) and booking_intent:
        missing = []
        if not booking_hint:
            missing.append('destination/tour')
        if not (start_date_req and end_date_req):
            missing.append('dates')
        if not persons_req:
            missing.append('number_of_people')

        if missing:
            computed_hints_lines.append(
                "Booking intent detected. Missing fields: " + ", ".join(missing) + ". Ask ONLY for the most important missing field (one question)."
            )
            if lang == 'fr':
                if 'destination/tour' in missing:
                    deterministic_text = "Pour quelle ville/destination veux-tu réserver ?"
                elif 'dates' in missing:
                    deterministic_text = "Quelles dates (du … au …) ?"
                else:
                    deterministic_text = "C’est pour combien de personnes ?"
            else:
                if 'destination/tour' in missing:
                    deterministic_text = "Which city/destination is the tour for?"
                elif 'dates' in missing:
                    deterministic_text = "What dates (from … to …)?"
                else:
                    deterministic_text = "How many people is it for?"
        else:
            requested_nights = max(0, (end_date_req - start_date_req).days)
            if requested_nights <= 0:
                computed_hints_lines.append("Invalid date range: end_date must be after start_date. Ask the user to correct dates.")
                deterministic_text = (
                    "La date de fin doit être après la date de début. Tu peux me redonner les dates (du … au …) ?" if lang == 'fr'
                    else "End date must be after start date. Can you resend the dates (from … to …)?"
                )
            elif requested_nights > 5:
                computed_hints_lines.append("Booking rule: maximum stay is 5 days. Ask for a shorter date range.")
                deterministic_text = (
                    "La durée maximale est de 11 nuits. Peux-tu choisir des dates plus courtes ?" if lang == 'fr'
                    else "Maximum stay is 5 days. Can you choose a shorter date range?"
                )
            else:
                will_replace_existing = _user_has_overlapping_reservation(request.user, country, start_date_req, end_date_req)
                tour, status, candidates = _select_tour_for_booking(country, message, booking_hint)

                if not tour:
                    computed_hints_lines.append("Could not resolve an exact tour from the user's destination. Ask them to specify the destination or tour ID.")
                    deterministic_text = (
                        "Je ne trouve pas le tour exact. Tu peux préciser la ville/destination ou me donner l’ID du tour ?" if lang == 'fr'
                        else "I can’t resolve the exact tour. Can you specify the destination/city or the tour ID?"
                    )
                else:
                    chosen_extra_id = _select_single_extra_activity_id(tour, message)
                    if chosen_extra_id:
                        addons_req['extras'] = True
                        pending_extra_ids = [str(chosen_extra_id)]

                    if addons_req.get('extras') is False:
                        pending_extra_ids = []
                        computed_hints_lines.append("User explicitly does NOT want extra activities. Do not ask about extras.")

                    if addons_req.get('extras') is True and not pending_extra_ids:
                        # If the user replies with a bare "yes" and there is only ONE extra option,
                        # auto-select it to avoid looping on the same question.
                        if _is_affirmative(message):
                            try:
                                only_extra = list(tour.extra_activities.filter(is_active=True).only('id').order_by('id')[:2])
                            except Exception:
                                only_extra = []
                            if len(only_extra) == 1:
                                pending_extra_ids = [str(getattr(only_extra[0], 'id'))]

                        options_txt = _format_tour_extra_activities(tour)
                        if options_txt:
                            _set_pending_booking(request, {
                                'tour_id': int(tour.id),
                                'destination': booking_hint or '',
                                'start_date': start_date_req.strftime('%Y-%m-%d'),
                                'end_date': end_date_req.strftime('%Y-%m-%d'),
                                'persons': int(persons_req),
                                'payment_method': payment_method_req,
                                'full_package': bool(addons_req.get('full_package')),
                                'include_transport': bool(addons_req.get('include_transport') or bool(addons_req.get('full_package'))),
                                'include_hotel': bool(addons_req.get('include_hotel') or bool(addons_req.get('full_package'))),
                                'extras': True,
                                'extra_activity_ids': [],
                            })
                            computed_hints_lines.append(
                                "User wants extra activities. Ask them to choose exactly ONE extra activity from these options: " + options_txt + "."
                            )
                            deterministic_text = (
                                "Tu veux une activité extra. Choisis-en UNE: " + options_txt if lang == 'fr'
                                else "You want an extra activity. Pick EXACTLY ONE: " + options_txt
                            )
                        else:
                            addons_req['extras'] = False
                            pending_extra_ids = []
                    else:
                        if not _user_break_buffer_ok(request.user, country, start_date_req, buffer_days=0):
                            computed_hints_lines.append("No booking buffer is allowed anymore. Skip this rule.")
                            # Preserve booking context so user can reply with only new dates.
                            _set_pending_booking(request, {
                                'tour_id': int(tour.id),
                                'destination': booking_hint or '',
                                'start_date': start_date_req.strftime('%Y-%m-%d'),
                                'end_date': end_date_req.strftime('%Y-%m-%d'),
                                'persons': int(persons_req),
                                'payment_method': payment_method_req,
                                'full_package': bool(addons_req.get('full_package')),
                                'include_transport': bool(addons_req.get('include_transport') or bool(addons_req.get('full_package'))),
                                'include_hotel': bool(addons_req.get('include_hotel') or bool(addons_req.get('full_package'))),
                                'extras': addons_req.get('extras'),
                                'extra_activity_ids': pending_extra_ids,
                            })
                            deterministic_text = (
                                "Tu dois laisser 3 jours de pause après ta dernière réservation. Peux-tu choisir une date de début plus tardive ?" if lang == 'fr'
                                else "Please choose different dates."
                            )
                        elif not _is_range_available(country, start_date_req, end_date_req, buffer_days=0, exclude_user=request.user):
                            _set_pending_booking(request, {
                                'tour_id': int(tour.id),
                                'destination': booking_hint or '',
                                'start_date': start_date_req.strftime('%Y-%m-%d'),
                                'end_date': end_date_req.strftime('%Y-%m-%d'),
                                'persons': int(persons_req),
                                'payment_method': payment_method_req,
                                'full_package': bool(addons_req.get('full_package')),
                                'include_transport': bool(addons_req.get('include_transport') or bool(addons_req.get('full_package'))),
                                'include_hotel': bool(addons_req.get('include_hotel') or bool(addons_req.get('full_package'))),
                                'extras': addons_req.get('extras'),
                                'extra_activity_ids': pending_extra_ids,
                            })
                            suggestions = _suggest_available_ranges_near(
                                country,
                                start_date_req,
                                nights=min(max(requested_nights, 3), 11),
                                limit=4,
                                buffer_days=0,
                                exclude_user=request.user,
                            )
                            if suggestions:
                                sug_txt = " ; ".join([f"{s.strftime('%Y-%m-%d')} to {e.strftime('%Y-%m-%d')}" for s, e in suggestions])
                                computed_hints_lines.append(
                                    "Requested dates are unavailable. Propose these available alternatives: " + sug_txt + ". Ask which one they prefer."
                                )
                                deterministic_text = (
                                    "Ces dates ne sont pas disponibles. Tu préfères laquelle ? " + sug_txt if lang == 'fr'
                                    else "Those dates aren’t available. Which option do you prefer? " + sug_txt
                                )
                            else:
                                computed_hints_lines.append("Requested dates are unavailable. Ask the user for another date range.")
                                deterministic_text = (
                                    "Ces dates ne sont pas disponibles. Donne-moi un autre intervalle (du … au …)." if lang == 'fr'
                                    else "Those dates aren’t available. Please share another date range (from … to …)."
                                )
                        else:
                            full_pkg = bool(addons_req.get('full_package'))
                            inc_transport = bool(addons_req.get('include_transport') or full_pkg)
                            inc_hotel = bool(addons_req.get('include_hotel') or full_pkg)

                            if full_pkg:
                                computed_hints_lines.append("User selected FULL PACKAGE. Do NOT ask about hotel/transport; they are included.")

                            if not payment_method_req:
                                _set_pending_booking(request, {
                                    'tour_id': int(tour.id),
                                    'destination': booking_hint or '',
                                    'start_date': start_date_req.strftime('%Y-%m-%d'),
                                    'end_date': end_date_req.strftime('%Y-%m-%d'),
                                    'persons': int(persons_req),
                                    'payment_method': None,
                                    'full_package': full_pkg,
                                    'include_transport': inc_transport,
                                    'include_hotel': inc_hotel,
                                    'extras': addons_req.get('extras'),
                                    'extra_activity_ids': pending_extra_ids,
                                })
                                computed_hints_lines.append(
                                    "All booking details are provided except payment_method. Ask ONLY: cash (espèces) or card (carte). Do not ask for dates/people/destination again."
                                )
                                deterministic_text = (
                                    "OK. Paiement par carte ou en espèces ?" if lang == 'fr'
                                    else "OK — would you like to pay by card or cash?"
                                )
                            else:
                                _set_pending_booking(request, None)
                                action = {
                                    'book_direct': {
                                        'url': reverse('chat_book_tour'),
                                        'tour_id': int(tour.id),
                                        'tour_slug': tour.slug,
                                        'start_date': start_date_req.strftime('%Y-%m-%d'),
                                        'end_date': end_date_req.strftime('%Y-%m-%d'),
                                        'persons': int(persons_req),
                                        'payment_method': payment_method_req,
                                        'full_package': 1 if full_pkg else 0,
                                        'include_transport': 1 if inc_transport else 0,
                                        'include_hotel': 1 if inc_hotel else 0,
                                        'extra_activity_ids': [int(x) for x in (pending_extra_ids or [])],
                                    },
                                }
                                computed_hints_lines.append(
                                    "Booking is ready. Tell the user you are submitting their booking request (pending admin validation). Do not claim it's confirmed/paid."
                                )

                                if session_memory:
                                    try:
                                        request.session['chat_last_tour_id'] = int(tour.id)
                                        request.session['chat_last_payment_method'] = payment_method_req
                                        request.session['chat_last_full_package'] = bool(full_pkg)
                                        request.session['chat_last_include_transport'] = bool(inc_transport)
                                        request.session['chat_last_include_hotel'] = bool(inc_hotel)
                                        request.session['chat_last_extra_activity_ids'] = list(pending_extra_ids or [])
                                    except Exception:
                                        pass

                                if lang == 'fr':
                                    deterministic_text = "✅ Parfait — je pré-remplis la réservation et je l’envoie maintenant (en attente de validation admin)."
                                    if will_replace_existing:
                                        deterministic_text += " (Cela remplace ta réservation précédente.)"
                                else:
                                    deterministic_text = "✅ Great — I’m prefilling and submitting your booking request now (pending admin validation)."
                                    if will_replace_existing:
                                        deterministic_text += " (This replaces your previous reservation.)"

    booking_rules_context = _build_booking_rules_context()
    site_context = _build_country_catalog_context(country, message)

    language_instruction = (
        "Respond in English only. " if lang == 'en' else (
            "Respond in French only. " if lang == 'fr' else "Respond in the same language as the user (French or English). "
        )
    )

    system_prompt = (
        f"You are the official virtual assistant for the {country_label} travel website. "
        "You can answer general travel questions about this country and its cities (what a city is like, how to choose, tips). "
        "If the user asks about another country/site, politely refuse and redirect them to the current site. "
        + language_instruction +
        "Sound natural and human (not robotic). Be concise and helpful. "
        "Ask at most 1 short follow-up question, only when needed. "
        "Do not repeat questions already answered by the user. "
        "Avoid re-confirmation loops: if the user says yes/correct, do not ask to confirm again; move to the next missing detail. "
        "Never ask the user to confirm details (no 'Let's confirm...'); assume provided details are correct unless the user changes them. "
        "Never ask for card/payment details (numbers, CVV, etc). This site only needs a payment method: cash or card. "
        "Do not restate all booking details unless the user asks. "
        + ("This is the first user message in this session: start with a brief friendly greeting (one short sentence). " if welcome_enabled else "Do not add a repetitive greeting if the conversation is already ongoing. ")
        +
        "Do NOT output special navigation markers like [NAVIGATE] or [PREFILL]. The backend/UI handles navigation. "
        "Currency rule: always present prices in USD only; do NOT mention MAD or Moroccan dirhams. "
        "Never invent site inventory (tours IDs, prices, availability) beyond the provided catalog/context. "
        "For booking, ask only for missing fields and follow the booking rules.\n\n"
        f"{booking_rules_context}\n\n"
        f"{site_context}"
    )

    if computed_hints_lines:
        system_prompt = system_prompt + "\n\nComputed booking state (ground truth; follow strictly):\n- " + "\n- ".join(computed_hints_lines)

    if deterministic_text:
        bot_reply = deterministic_text
        used_model = None
    else:
        bot_reply = None

    if session_memory and session_history:
        def _fmt_role(r: str) -> str:
            return 'Assistant' if r in {'assistant', 'bot'} else 'User'

        recent = session_history[-session_history_max:]
        recent_lines = []
        for item in recent:
            role = _fmt_role(str(item.get('role') or 'user'))
            content = str(item.get('content') or '').strip()
            if not content:
                continue
            recent_lines.append(f"{role}: {content}")
        if recent_lines:
            system_prompt = system_prompt + "\n\nRecent conversation (context):\n" + "\n".join(recent_lines[-session_history_max:])

    try:
        if bot_reply is None:
            if settings.HF_API_TOKEN:
                hf_model = getattr(settings, 'HF_MODEL', None) or 'Qwen/Qwen2.5-7B-Instruct:fastest'
                hf_fallback = getattr(settings, 'HF_FALLBACK_MODEL', None) or ''

                def _run_full(model_to_use: str) -> str:
                    return _hf_router_chat_completion_full_text(
                        model_to_use,
                        settings.HF_API_TOKEN,
                        system_prompt,
                        message,
                        max_tokens=int(getattr(settings, 'HF_MAX_NEW_TOKENS', 250) or 250),
                        temperature=float(getattr(settings, 'HF_TEMPERATURE', 0.7) or 0.7),
                        top_p=float(getattr(settings, 'HF_TOP_P', 0.95) or 0.95),
                    )

                try:
                    bot_reply = _run_full(hf_model)
                    used_model = hf_model
                except Exception as e:
                    msg = str(e or '').lower()
                    if (not hf_fallback) and ('model_not_supported' in msg) and (HF_ROUTER_DEFAULT_MODEL != hf_model):
                        bot_reply = _run_full(HF_ROUTER_DEFAULT_MODEL)
                        used_model = HF_ROUTER_DEFAULT_MODEL
                    elif hf_fallback and hf_fallback != hf_model:
                        bot_reply = _run_full(hf_fallback)
                        used_model = hf_fallback
                    else:
                        raise

            elif settings.OPENAI_API_KEY:
                used_model = getattr(settings, 'OPENAI_MODEL', None) or 'gpt-4o'
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ]
                response = client.chat.completions.create(
                    model=used_model,
                    messages=messages,
                    max_tokens=300,
                    temperature=0.7,
                )
                bot_reply = response.choices[0].message.content.strip()
            else:
                return JsonResponse({'error': 'AI assistant not configured.'}, status=503)

        # else: bot_reply is deterministic (no model call)

    except Exception:
        logging.exception('[ai_chat] Model exception')
        return JsonResponse({'error': 'AI assistant unavailable.'}, status=503)

    bot_reply = _redact_secrets(str(bot_reply or '').strip())
    if not welcome_enabled:
        bot_reply = _strip_welcome_banner(bot_reply, country_label)

    if session_memory:
        try:
            session_history = request.session.get('chat_history') or []
            if not isinstance(session_history, list):
                session_history = []
            if bot_reply:
                session_history.append({'role': 'assistant', 'content': bot_reply})
            request.session['chat_history'] = session_history[-session_history_max:]
        except Exception:
            pass

    result = {
        'reply': bot_reply,
        'model': used_model,
        'action': action or {},
    }
    # Backward compat for older frontends
    if action:
        result.update(action)

    if getattr(settings, 'CHAT_DEBUG', False):
        result['debug'] = {
            'request_id': request_id,
            'provider': 'huggingface' if getattr(settings, 'HF_API_TOKEN', '') else ('openai' if getattr(settings, 'OPENAI_API_KEY', '') else None),
            'country': country,
            'lang': lang,
            'model_used': used_model,
            'message_chars': len(message or ''),
            'system_prompt_chars': len(system_prompt or ''),
            'computed_hints_lines': computed_hints_lines,
        }

    return JsonResponse(result)


def generate_fallback_reply(message, country, lang: str | None = None):
    country = _normalize_country(country)
    country_label = _country_label(country)
    msg_lower = message.lower()

    forced_lang = (getattr(settings, 'CHAT_FORCE_LANGUAGE', '') or '').strip().lower()
    lang = (lang or forced_lang or _detect_language(message) or '').strip().lower()
    if lang not in {'en', 'fr'}:
        lang = 'en'

    if any(w in msg_lower for w in ['price', 'cost', 'prix', 'tarif']):
        if lang == 'fr':
            return f"Les prix dépendent du tour sur le site {country_label}. Dis-moi la destination, les dates et le nombre de personnes, et je te propose la meilleure option."
        return f"Prices vary by tour on the {country_label} site. Tell me the destination, dates, and number of people, and I’ll suggest the best option."

    if _detect_private_tour_intent(message):
        return _private_tour_reply(country, lang)

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

    # Booking navigation is intentionally strict: only when we have enough concrete info.
    keyword_booking_intent = any(k in msg_lower for k in ['book', 'booking', 'reserve', 'reservation', 'réserver', 'reserver'])
    start_date, end_date, persons, parsed_dest = _extract_booking_details(message)
    has_core_booking_fields = bool(parsed_dest and start_date and end_date and persons)
    booking_intent = bool(keyword_booking_intent or has_core_booking_fields)

    if booking_intent:
        if start_date and end_date and persons:
            requested_nights = max(0, (end_date - start_date).days)
            if requested_nights <= 5 and _is_range_available(country, start_date, end_date, buffer_days=0):
                tour, status, _candidates = _select_tour_for_booking(country, message, parsed_dest)
                if tour and status == 'ok':
                    action['navigate'] = reverse('tour_detail', args=[tour.slug])
                    action['prefill'] = {
                        'start_date': start_date.strftime('%Y-%m-%d'),
                        'end_date': end_date.strftime('%Y-%m-%d'),
                        'persons': persons,
                    }
                    pm = _extract_payment_method(message)
                    if pm:
                        action['prefill']['payment_method'] = pm

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

            active_statuses = ['pending', 'booked']

            try:
                has_conflict = Reservation.objects.filter(
                    tour__country=country,
                    status__in=active_statuses,
                    start_date__lte=range_end,
                    end_date__gte=start_date_val,
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
