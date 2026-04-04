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

from .models import Tour, Reservation, BlogPost, Destination, ContactMessage, BlogComment, UserProfile, CountryContent, Section, Information, ChatMessage
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

    country = _normalize_country(get_country_from_site(request) or 'morocco')
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
    country_label = _country_label(country)
    site_context = _build_country_catalog_context(country, message)

    language_instruction = (
        "Respond in English only. " if lang == 'en' else (
            "Respond in French only. " if lang == 'fr' else "Respond in the same language as the user (French or English). "
        )
    )

    system_prompt = (
        f"You are the official virtual assistant for the {country_label} travel website only. "
        f"You must ONLY answer using information relevant to {country_label}. "
        "If the user asks about another country/site, politely refuse and redirect them to questions about the current site. "
        + language_instruction +
        "Be conversational, natural, and helpful. Ask 1 short follow-up question when needed. "
        "When the user greets (hello/hi/salut/salam) or asks to start (e.g., 'can I ask?'), greet warmly and say: "
        f"'Hello! Your virtual assistant is ready for {country_label}. You can ask in English or French about tours, booking, and travel tips.' "
        "Then invite their question. "
        "Do NOT repeat or dump the provided site context verbatim; never echo long blocks of text. "
        "Only include booking navigation markers when the user explicitly asks to book AND provides a date range AND number of people, "
        "AND the mentioned tour/destination exists on this site AND the dates are available. "
        "When those conditions are met, include: [NAVIGATE: /tour/<id>/] and [PREFILL: start_date=YYYY-MM-DD,end_date=YYYY-MM-DD,persons=N]. "
        "Never invent tours, destinations, prices, or policies; use the provided catalog/context. "
        "If the user wants to book, ask for missing info (dates, people) and respect the booking rules in context.\n\n"
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
    msg_lower = message.lower()
    booking_intent = any(k in msg_lower for k in ['book', 'booking', 'reserve', 'reservation', 'réserver', 'reserver'])
    start_date_req, end_date_req, persons_req, parsed_dest = _extract_booking_details(message)
    destination_hint = None
    if not _is_greeting(message) and not _is_smalltalk(message):
        destination_hint = _resolve_destination_hint(country, message, parsed_dest)


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

    # Deterministic DB-backed reply first (works even when external LLM quota/config is missing).
    deterministic_reply = ''
    include_admin_hint = bool(getattr(request, 'user', None) and getattr(request.user, 'is_staff', False))

    if _is_smalltalk(message):
        deterministic_reply = _smalltalk_reply(country, lang)

    if _detect_how_it_works_intent(message) and not deterministic_reply:
        deterministic_reply = _how_it_works_reply(country, lang)

    # If the user asked about a specific destination but there are no tours for it, be explicit.
    if (not deterministic_reply) and parsed_dest and (not destination_hint) and _detect_list_tours_intent(message):
        if not _tours_for_hint(country, parsed_dest):
            asked = parsed_dest
            deterministic_reply = (
                f"Désolé — je n’ai pas encore de tour pour “{asked}” sur ce site."
                if lang == 'fr' else
                f"Sorry — we don’t have a tour for “{asked}” on this site yet."
            )

    if _detect_list_tours_intent(message) and not destination_hint and not deterministic_reply:
        deterministic_reply = _list_tours_reply(country, lang, limit=6)

    if _detect_list_cities_intent(message) and not deterministic_reply:
        deterministic_reply = _list_cities_reply(country, lang, limit=12)

    # If user already chose a destination + people but didn't provide dates yet, ask for dates.
    if destination_hint and persons_req and not (start_date_req and end_date_req) and not deterministic_reply:
        if lang == 'fr':
            deterministic_reply = f"Parfait — pour {persons_req} personnes à {destination_hint}. Quelles sont tes dates (arrivée et départ) ?"
        else:
            deterministic_reply = f"Great — for {persons_req} people in {destination_hint}. What dates are you considering (check-in and check-out)?"

    info_intents = _detect_info_intent(message)
    if info_intents:
        tours = _find_relevant_tours(country, destination_hint, limit=3) if destination_hint else []
        deterministic_reply = _format_tour_info_reply(
            country,
            tours,
            info_intents,
            lang,
            include_booking_tip=booking_intent,
            include_admin_hint=include_admin_hint,
        )

    if booking_intent and not deterministic_reply:
        if start_date_req and end_date_req:
            requested_nights = max(0, (end_date_req - start_date_req).days)
            if requested_nights > 11:
                deterministic_reply = (
                    "Désolé, la durée maximale est de 11 nuits. Peux-tu choisir une période plus courte ?"
                    if lang == 'fr' else
                    "Sorry — the maximum stay is 11 nights. Can you pick a shorter date range?"
                )
            else:
                # If the user mentioned a specific tour/city, verify it exists before talking about date availability.
                tour_check, status_check, candidates_check = _select_tour_for_booking(country, message, booking_hint)
                explicit_id = _extract_explicit_tour_id(message)
                if (explicit_id or booking_hint) and status_check != 'ok':
                    if status_check == 'multiple' and candidates_check:
                        titles = [f"{t.id}: {t.title}" for t in candidates_check[:5]]
                        deterministic_reply = (
                            "Plusieurs tours correspondent. Peux-tu me dire lequel (ID ou titre) ?\n- "
                            + "\n- ".join(titles)
                            if lang == 'fr' else
                            "I found multiple matching tours. Which one do you want to book (ID or title)?\n- "
                            + "\n- ".join(titles)
                        )
                    else:
                        asked = (f"tour #{explicit_id}" if explicit_id else (booking_hint or 'that destination'))
                        deterministic_reply = (
                            f"Désolé — ce tour/destination (“{asked}”) n’est pas encore disponible sur ce site."
                            if lang == 'fr' else
                            f"Sorry — this tour/destination (“{asked}”) isn’t available on this site yet."
                        )

            if deterministic_reply:
                pass
            elif not _is_range_available(country, start_date_req, end_date_req, buffer_days=3):
                suggestions = _suggest_available_ranges(country, nights=min(max(requested_nights, 3), 11), limit=4)
                if lang == 'fr':
                    if suggestions:
                        sug_txt = " ; ".join([f"{s.strftime('%d %b %Y')} → {e.strftime('%d %b %Y')}" for s, e in suggestions])
                        deterministic_reply = (
                            "Ces dates semblent déjà bloquées sur ce site. Voici des alternatives disponibles : "
                            + sug_txt
                            + ". Tu préfères laquelle ?"
                        )
                    else:
                        deterministic_reply = "Ces dates semblent indisponibles. Donne-moi une autre période (+ le nombre de personnes) et je propose des options."
                else:
                    if suggestions:
                        sug_txt = "; ".join([f"{s.strftime('%d %b %Y')} → {e.strftime('%d %b %Y')}" for s, e in suggestions])
                        deterministic_reply = (
                            "Those dates look unavailable on this site. Here are available alternatives: "
                            + sug_txt
                            + ". Which one do you prefer?"
                        )
                    else:
                        deterministic_reply = "Those dates look unavailable on this site. Share another date range (+ number of people) and I’ll suggest options."
            else:
                if not persons_req:
                    deterministic_reply = (
                        "Parfait — pour combien de personnes ?"
                        if lang == 'fr' else
                        "Great — for how many people?"
                    )
                else:
                    tour, status, candidates = _select_tour_for_booking(country, message, booking_hint)
                    if not tour:
                        if status == 'multiple' and candidates:
                            titles = [f"{t.id}: {t.title}" for t in candidates[:5]]
                            deterministic_reply = (
                                "Plusieurs tours correspondent. Peux-tu me dire lequel (ID ou titre) ?\n- "
                                + "\n- ".join(titles)
                                if lang == 'fr' else
                                "I found multiple matching tours. Which one do you want to book (ID or title)?\n- "
                                + "\n- ".join(titles)
                            )
                        else:
                            explicit_id = _extract_explicit_tour_id(message)
                            if (not booking_hint) and (not explicit_id):
                                deterministic_reply = (
                                    "Pour quel tour / quelle ville veux-tu réserver ? Donne le nom de la destination ou l’ID du tour."
                                    if lang == 'fr' else
                                    "Which tour/city do you want to book? Tell me the destination name or the tour ID."
                                )
                            else:
                                asked = (f"tour #{explicit_id}" if explicit_id else (booking_hint or 'that destination'))
                                deterministic_reply = (
                                    f"Désolé — ce tour/destination (“{asked}”) n’est pas encore disponible sur ce site."
                                    if lang == 'fr' else
                                    f"Sorry — this tour/destination (“{asked}”) isn’t available on this site yet."
                                )
                    else:
                        selected_tour_id = int(tour.id)
                        action['navigate'] = reverse('tour_detail', args=[tour.id])
                        action['prefill'] = {
                            'start_date': start_date_req.strftime('%Y-%m-%d'),
                            'end_date': end_date_req.strftime('%Y-%m-%d'),
                            'persons': persons_req,
                        }
                        deterministic_reply = (
                            f"Super — je t’ouvre la réservation pour {tour.title}."
                            if lang == 'fr' else
                            f"Great — I’m opening the booking for {tour.title}."
                        )
        else:
            suggestions = _suggest_available_ranges(country, nights=5, limit=4)
            if lang == 'fr':
                if suggestions:
                    sug_txt = " ; ".join([f"{s.strftime('%d %b %Y')} → {e.strftime('%d %b %Y')}" for s, e in suggestions])
                    deterministic_reply = (
                        "Bien sûr. Donne-moi tes dates exactes et le nombre de personnes (et la ville si tu veux). "
                        "Exemples de périodes disponibles (5 nuits) : " + sug_txt + "."
                    )
                else:
                    deterministic_reply = "Bien sûr. Donne-moi tes dates exactes et le nombre de personnes, et je vérifie la disponibilité."
            else:
                if suggestions:
                    sug_txt = "; ".join([f"{s.strftime('%d %b %Y')} → {e.strftime('%d %b %Y')}" for s, e in suggestions])
                    deterministic_reply = (
                        "Sure — tell me your dates and number of people (and the destination if you want). "
                        "Examples of available windows (5 nights): " + sug_txt + "."
                    )
                else:
                    deterministic_reply = "Sure — tell me your dates and number of people and I’ll check availability."

    if not deterministic_reply and destination_hint:
        tours = _find_relevant_tours(country, destination_hint, limit=2)
        deterministic_reply = _format_tour_info_reply(
            country,
            tours,
            {'price', 'activities'},
            lang,
            include_booking_tip=False,
            include_admin_hint=include_admin_hint,
        )

    if not deterministic_reply:
        deterministic_reply = _answer_from_site_content(country, message, lang)

    if getattr(settings, 'CHAT_FORCE_LLM', False) and deterministic_reply:
        # Give the model extra grounded hints without forcing the exact wording.
        system_prompt = (
            system_prompt
            + "\n\nComputed hints (ground truth from the website/DB logic; do not contradict):\n"
            + deterministic_reply
        )

    # If booking details are complete and the range is available, prepare a navigation action.
    if booking_intent and start_date_req and end_date_req and persons_req:
        requested_nights = max(0, (end_date_req - start_date_req).days)
        if requested_nights <= 11 and _is_range_available(country, start_date_req, end_date_req, buffer_days=3):
            tour, status, _candidates = _select_tour_for_booking(country, message, booking_hint)
            if tour:
                selected_tour_id = int(tour.id)
                action['navigate'] = reverse('tour_detail', args=[tour.id])
                action['prefill'] = {
                    'start_date': start_date_req.strftime('%Y-%m-%d'),
                    'end_date': end_date_req.strftime('%Y-%m-%d'),
                    'persons': persons_req,
                }

    def event_stream():
        full_text_parts: list[str] = []

        llm_available = bool(getattr(settings, 'HF_API_TOKEN', '') or getattr(settings, 'OPENAI_API_KEY', ''))

        if getattr(settings, 'CHAT_DEBUG', False):
            yield _sse_pack({
                'type': 'debug',
                'request_id': request_id,
                'forced_llm': bool(getattr(settings, 'CHAT_FORCE_LLM', False)),
                'provider': 'huggingface' if getattr(settings, 'HF_API_TOKEN', '') else ('openai' if getattr(settings, 'OPENAI_API_KEY', '') else None),
                'model_config': getattr(settings, 'HF_MODEL', None) or None,
                'session_memory': session_memory,
            })

        # If no LLM is configured, fall back to deterministic responses.
        if _is_greeting(message) and (not llm_available or not getattr(settings, 'CHAT_FORCE_LLM', False)):
            greet = _greeting_reply(country, lang)
            greet = _redact_secrets(greet)
            yield _sse_pack({'type': 'delta', 'text': greet})
            yield _sse_pack({'type': 'final', 'text': greet, 'action': action or {}, 'model': None})
            return

        if deterministic_reply and (not llm_available or not getattr(settings, 'CHAT_FORCE_LLM', False)):
            reply = _redact_secrets(deterministic_reply)
            yield _sse_pack({'type': 'delta', 'text': reply})
            yield _sse_pack({'type': 'final', 'text': reply, 'action': action or {}, 'model': None})
            return

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

            # If we forced the LLM but it failed, fall back to the grounded deterministic reply.
            if getattr(settings, 'CHAT_FORCE_LLM', False) and deterministic_reply:
                reply = _redact_secrets(deterministic_reply)
                full_text_parts = [reply]
                yield _sse_pack({'type': 'delta', 'text': reply})
                final_text = reply
                parsed_action, cleaned = parse_actions_from_response(final_text, country)
                final_action = action or parsed_action or {}
                final_text = cleaned.strip() if cleaned else final_text
                yield _sse_pack({'type': 'final', 'text': final_text, 'action': final_action, 'model': None})
                return

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
                # Provide a useful non-LLM fallback instead of a generic error.
                try:
                    err = (generate_fallback_reply(message, country, lang=lang) or '').strip()
                except Exception:
                    err = None

            if not err:
                if lang == 'fr':
                    err = "Désolé — le modèle IA a eu un problème. Réessaie dans un instant."
                else:
                    err = "Sorry — the AI model had an issue. Please try again in a moment."

            err = _redact_secrets(err)

            full_text_parts = [err]
            yield _sse_pack({'type': 'delta', 'text': err})

        final_text = _redact_secrets(''.join(full_text_parts).strip())
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
    if requested_nights > 11 or (not _is_range_available(country, start_date_req, end_date_req, buffer_days=3)):
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
                line = f"- {header}: {t.price_per_night} par nuit."
            else:
                line = f"- {header}: {t.price_per_night} per night."
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
                ).exclude(status__in=["rejected", "cancelled", "completed"]).order_by("-created_at").first()
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

    try:
        # Privacy: do not persist or return chat history.
        return JsonResponse({'history': []})
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
        ).exclude(status__in=["rejected", "cancelled", "completed"]).order_by("-created_at").first()

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
        "extra_activities": list(tour.extra_activities.filter(is_active=True).order_by('id')),
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

    message = _redact_secrets(payload.get('message', '').strip())
    if not message:
        return JsonResponse({'error': 'Message cannot be empty.'}, status=400)

    country = _normalize_country(get_country_from_site(request) or 'morocco')
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

    bot_reply = ''
    action = {}
    used_model = None
    lang = getattr(settings, 'CHAT_FORCE_LANGUAGE', '') or _detect_language(message)

    if _is_greeting(message):
        bot_reply = _greeting_reply(country, lang)
    elif _is_smalltalk(message):
        bot_reply = _smalltalk_reply(country, lang)

    if _detect_how_it_works_intent(message) and not bot_reply:
        bot_reply = _how_it_works_reply(country, lang)

    if _detect_list_cities_intent(message) and not bot_reply:
        bot_reply = _list_cities_reply(country, lang, limit=12)

    booking_intent = any(k in message.lower() for k in ['book', 'booking', 'reserve', 'reservation', 'réserver', 'reserver'])
    include_admin_hint = bool(getattr(request, 'user', None) and getattr(request.user, 'is_staff', False))

    # Parse once, reuse everywhere
    start_date_req, end_date_req, persons_req, parsed_dest = _extract_booking_details(message)
    destination_hint = None
    if not _is_greeting(message) and not _is_smalltalk(message):
        destination_hint = _resolve_destination_hint(country, message, parsed_dest)


    # If the user asked about a specific destination but there are no tours for it, be explicit.
    if (not bot_reply) and parsed_dest and (not destination_hint) and _detect_list_tours_intent(message):
        if not _tours_for_hint(country, parsed_dest):
            asked = parsed_dest
            bot_reply = (
                f"Désolé — je n’ai pas encore de tour pour “{asked}” sur ce site."
                if lang == 'fr' else
                f"Sorry — we don’t have a tour for “{asked}” on this site yet."
            )

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

    # DB-backed informational Q&A (price / activities / what's included) — highest priority
    info_intents = _detect_info_intent(message)
    if info_intents and not bot_reply:
        tours = _find_relevant_tours(country, destination_hint, limit=3) if destination_hint else []
        bot_reply = _format_tour_info_reply(
            country,
            tours,
            info_intents,
            lang,
            include_booking_tip=booking_intent,
            include_admin_hint=include_admin_hint,
        )

    if _detect_list_tours_intent(message) and not destination_hint and not bot_reply:
        bot_reply = _list_tours_reply(country, lang, limit=6)

    if destination_hint and persons_req and not (start_date_req and end_date_req) and not bot_reply:
        if lang == 'fr':
            bot_reply = f"Parfait — pour {persons_req} personnes à {destination_hint}. Quelles sont tes dates (arrivée et départ) ?"
        else:
            bot_reply = f"Great — for {persons_req} people in {destination_hint}. What dates are you considering (check-in and check-out)?"

    # Booking intelligence (works even without OpenAI credits)
    if booking_intent and not bot_reply:
        # If dates provided, validate rules + availability first.
        if start_date_req and end_date_req:
            requested_nights = max(0, (end_date_req - start_date_req).days)
            if requested_nights > 11:
                bot_reply = (
                    "Désolé, la durée maximale est de 11 nuits. Peux-tu choisir une période plus courte ?"
                    if lang == 'fr' else
                    "Sorry — the maximum stay is 11 nights. Can you pick a shorter date range?"
                )
            else:
                # If the user mentioned a specific tour/city, verify it exists before talking about date availability.
                tour_check, status_check, candidates_check = _select_tour_for_booking(country, message, booking_hint)
                explicit_id = _extract_explicit_tour_id(message)
                if (explicit_id or booking_hint) and status_check != 'ok':
                    if status_check == 'multiple' and candidates_check:
                        titles = [f"{t.id}: {t.title}" for t in candidates_check[:5]]
                        bot_reply = (
                            "Plusieurs tours correspondent. Lequel veux-tu réserver (ID ou titre) ?\n- "
                            + "\n- ".join(titles)
                            if lang == 'fr' else
                            "I found multiple matching tours. Which one do you want to book (ID or title)?\n- "
                            + "\n- ".join(titles)
                        )
                    else:
                        asked = (f"tour #{explicit_id}" if explicit_id else (booking_hint or 'that destination'))
                        bot_reply = (
                            f"Désolé — ce tour/destination (“{asked}”) n’est pas encore disponible sur ce site."
                            if lang == 'fr' else
                            f"Sorry — this tour/destination (“{asked}”) isn’t available on this site yet."
                        )

            if bot_reply:
                pass
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
                    tour, status, candidates = _select_tour_for_booking(country, message, booking_hint)
                    if not tour:
                        if status == 'multiple' and candidates:
                            titles = [f"{t.id}: {t.title}" for t in candidates[:5]]
                            bot_reply = (
                                "Plusieurs tours correspondent. Lequel veux-tu réserver (ID ou titre) ?\n- "
                                + "\n- ".join(titles)
                                if lang == 'fr' else
                                "I found multiple matching tours. Which one do you want to book (ID or title)?\n- "
                                + "\n- ".join(titles)
                            )
                        else:
                            explicit_id = _extract_explicit_tour_id(message)
                            if (not booking_hint) and (not explicit_id):
                                bot_reply = (
                                    "Pour quel tour / quelle ville veux-tu réserver ? Donne le nom de la destination ou l’ID du tour."
                                    if lang == 'fr' else
                                    "Which tour/city do you want to book? Tell me the destination name or the tour ID."
                                )
                            else:
                                asked = (f"tour #{explicit_id}" if explicit_id else (booking_hint or 'that destination'))
                                bot_reply = (
                                    f"Désolé — ce tour/destination (“{asked}”) n’est pas encore disponible sur ce site."
                                    if lang == 'fr' else
                                    f"Sorry — this tour/destination (“{asked}”) isn’t available on this site yet."
                                )
                    else:
                        selected_tour_id = int(tour.id)
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

    # If user sends just a destination name, be helpful instead of resetting the conversation
    if not bot_reply and destination_hint:
        tours = _find_relevant_tours(country, destination_hint, limit=2)
        bot_reply = _format_tour_info_reply(
            country,
            tours,
            {'price', 'activities'},
            lang,
            include_booking_tip=False,
            include_admin_hint=include_admin_hint,
        )

    if not bot_reply:
        bot_reply = _answer_from_site_content(country, message, lang)

    # If the user wants the HuggingFace model to always respond, keep the computed reply as hints.
    computed_hints = ''
    if getattr(settings, 'CHAT_FORCE_LLM', False) and bot_reply:
        computed_hints = bot_reply
        bot_reply = ''

    site_context = ''
    system_prompt = ''

    try:
        country_label = _country_label(country)
        site_context = _build_country_catalog_context(country, message)

        language_instruction = (
            "Respond in English only. " if lang == 'en' else (
                "Respond in French only. " if lang == 'fr' else "Respond in the same language as the user (French or English). "
            )
        )

        system_prompt = (
            f"You are the official virtual assistant for the {country_label} travel website only. "
            f"You must ONLY answer using information relevant to {country_label}. "
            "If the user asks about another country/site, politely refuse and redirect them to questions about the current site. "
            + language_instruction +
            "Be conversational, concise, and helpful. Ask 1 short follow-up question when needed. "
            "When the user greets (hello/hi/salut/salam) or asks to start (e.g., 'can I ask?'), greet warmly and say: "
            f"'Hello! Your virtual assistant is ready for {country_label}. You can ask in English or French about tours, booking, and travel tips.' "
            "Then invite their question. "
            "Do NOT repeat or dump the provided site context verbatim; never echo long blocks of text. "
            "Do NOT tell the user to type a specific magic command like 'book ...'. Instead, understand natural language and ask for missing info. "
            "Only include booking navigation markers when the user explicitly asks to book AND provides a date range AND number of people, "
            "AND the mentioned tour/destination exists on this site AND the dates are available. "
            "When those conditions are met, include: [NAVIGATE: /tour/<id>/] and [PREFILL: start_date=YYYY-MM-DD,end_date=YYYY-MM-DD,persons=N]. "
            "Never invent tours, destinations, or prices; use the provided catalog/context.\n\n"
            f"{site_context}"
        )

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

        # Prefer HuggingFace over OpenAI when configured.
        if settings.HF_API_TOKEN and not bot_reply:
            try:
                hf_model = getattr(settings, 'HF_MODEL', None) or 'Qwen/Qwen2.5-7B-Instruct:fastest'
                hf_fallback = getattr(settings, 'HF_FALLBACK_MODEL', None) or ''
                if computed_hints:
                    system_prompt = (
                        system_prompt
                        + "\n\nComputed hints (ground truth from the website/DB logic; do not contradict):\n"
                        + computed_hints
                    )

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

                bot_reply = _redact_secrets(str(bot_reply or '').strip())
                parsed_action, bot_reply = parse_actions_from_response(bot_reply, country)
                parsed_action = _filter_navigation_action(
                    parsed_action,
                    country=country,
                    booking_intent=booking_intent,
                    start_date_req=start_date_req,
                    end_date_req=end_date_req,
                    persons_req=persons_req,
                    allowed_tour_id=selected_tour_id,
                )
                action = action or parsed_action or {}
            except Exception:
                logging.exception('[ai_chat] HF exception')
                bot_reply = computed_hints or ''
                action = {}

        if (not settings.HF_API_TOKEN) and settings.OPENAI_API_KEY and not bot_reply:
            try:
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ]

                response = client.chat.completions.create(
                    model=getattr(settings, 'OPENAI_MODEL', None) or "gpt-4o",
                    messages=messages,
                    max_tokens=300,
                    temperature=0.7
                )

                bot_reply = response.choices[0].message.content.strip()
                parsed_action, bot_reply = parse_actions_from_response(bot_reply, country)
                parsed_action = _filter_navigation_action(
                    parsed_action,
                    country=country,
                    booking_intent=booking_intent,
                    start_date_req=start_date_req,
                    end_date_req=end_date_req,
                    persons_req=persons_req,
                    allowed_tour_id=selected_tour_id,
                )
                action = action or parsed_action or {}

            except Exception:
                logging.exception('[ai_chat] OpenAI exception')
                # Keep any already computed deterministic reply (availability checks, etc).
                bot_reply = bot_reply or ''
                action = action or {}

        if not bot_reply:
            bot_reply = generate_fallback_reply(message, country, lang=lang)
            action = parse_actions(message, country)

    except Exception:
        logging.exception('[ai_chat] Unhandled exception')
        bot_reply = (
            'Désolé, une erreur est survenue. Veuillez réessayer dans quelques instants.'
            if lang == 'fr' else
            'Sorry — an error occurred. Please try again in a moment.'
        )
        action = parse_actions(message, country)

    if not action:
        action = parse_actions(message, country)

    bot_reply = _redact_secrets(bot_reply)

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

    result = {'reply': bot_reply, 'model': used_model}
    if getattr(settings, 'CHAT_DEBUG', False):
        result['debug'] = {
            'request_id': request_id,
            'provider': 'huggingface' if getattr(settings, 'HF_API_TOKEN', '') else ('openai' if getattr(settings, 'OPENAI_API_KEY', '') else None),
            'forced_llm': bool(getattr(settings, 'CHAT_FORCE_LLM', False)),
            'session_memory': session_memory,
            'country': country,
            'lang': lang,
            'model_used': used_model,
            'message_chars': len(message or ''),
            'site_context_chars': len(site_context or ''),
            'system_prompt_chars': len(system_prompt or ''),
            'computed_hints_chars': len(computed_hints or ''),
        }
    result.update(action)
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

    # Booking navigation is intentionally strict: only when user mentioned a valid tour.
    booking_intent = any(k in msg_lower for k in ['book', 'booking', 'reserve', 'reservation', 'réserver', 'reserver'])
    if booking_intent:
        start_date, end_date, persons, parsed_dest = _extract_booking_details(message)
        if start_date and end_date and persons:
            requested_nights = max(0, (end_date - start_date).days)
            if requested_nights <= 11 and _is_range_available(country, start_date, end_date, buffer_days=3):
                tour, status, _candidates = _select_tour_for_booking(country, message, parsed_dest)
                if tour and status == 'ok':
                    action['navigate'] = reverse('tour_detail', args=[tour.id])
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
