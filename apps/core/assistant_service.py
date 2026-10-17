import logging
import openai
from django.conf import settings

logger = logging.getLogger(__name__)


def stream_answer(system_prompt, message):
    """Try configured providers in order; never splice two partial answers."""
    from .views import _hf_router_chat_completion_stream
    candidates = []
    if settings.HF_API_TOKEN:
        for model in dict.fromkeys([settings.HF_MODEL, getattr(settings, 'HF_FALLBACK_MODEL', '')]):
            if model:
                candidates.append(('huggingface', model))
    if settings.OPENAI_API_KEY:
        candidates.append(('openai', settings.OPENAI_MODEL))
    for provider, model in candidates:
        emitted = False
        try:
            if provider == 'huggingface':
                tokens = _hf_router_chat_completion_stream(model, settings.HF_API_TOKEN,
                    system_prompt, message, max_tokens=300, temperature=.7, top_p=.95)
            else:
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY, timeout=20, max_retries=0)
                response = client.chat.completions.create(model=model,
                    messages=[{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': message}],
                    stream=True)
                tokens = (event.choices[0].delta.content for event in response if event.choices)
            for token in tokens:
                if token:
                    emitted = True
                    yield token.replace('\u2014', '-').replace('\u2013', '-')
            if emitted:
                return
            raise RuntimeError('Empty provider response')
        except Exception as exc:
            logger.warning('Assistant provider=%s model=%s failed: %s status=%s',
                provider, model, type(exc).__name__, getattr(exc, 'status_code', 'unknown'))
            if emitted:
                yield '\n\nThe response was interrupted. Please try again or contact us for help.'
                return
    raise RuntimeError('No configured assistant provider returned an answer')


def unavailable_answer(country, lang):
    from .views import _list_tours_reply
    intro = ('L’assistant est temporairement indisponible. Voici les tours du site ; ouvrez un tour pour voir son programme et ses dates.'
             if lang == 'fr' else 'The assistant is temporarily unavailable. Here are tours from the website; open a tour to see its programme and dates.')
    return intro + '\n\n' + _list_tours_reply(country, lang)
