"""Server-rendered Morocco metadata; no invented ratings, prices or credentials."""
import json
from urllib.parse import urlsplit

from django.conf import settings
from django.templatetags.static import static
from django.utils.html import strip_tags
from django.utils.text import Truncator

BRAND = 'Basma Morocco Experience'
PUBLIC_PAGES = {'home', 'reservations', 'blog_list', 'blog_detail', 'tour_detail', 'about', 'contact'}


def morocco_url(path='/'):
    origin = settings.MOROCCO_SITE_URL.rstrip('/')
    path = urlsplit(path).path
    if path == '/morocco' or path.startswith('/morocco/'):
        path = path[len('/morocco'):] or '/'
    return origin + '/' + path.lstrip('/')


def is_local_preview(request):
    host = request.get_host().split(':')[0].lower()
    return host in {'localhost', '127.0.0.1', 'testserver', '[::1]'} or host.endswith('.local')


def plain_excerpt(value, limit=160):
    return Truncator(' '.join(strip_tags(value or '').split())).chars(limit)


def metadata(request, *, tour=None, post=None):
    page = getattr(request.resolver_match, 'url_name', '')
    titles = {
        'home': f'Private Morocco Tours with a Local Guide | {BRAND}',
        'reservations': f'Choose Your Private Morocco Tour | {BRAND}',
        'blog_list': f'Morocco Travel Stories & Experiences | {BRAND}',
        'contact': f'Contact Your Morocco Guide | {BRAND}',
        'about': f'About Your Morocco Journey | {BRAND}',
        'login': f'Sign In | {BRAND}',
        'register': f'Create an Account | {BRAND}',
    }
    descriptions = {
        'home': 'Discover Morocco with Basma, your independent local guide. Explore private tours, choose your dates and plan a journey for you or your group.',
        'reservations': 'Compare Morocco tours, explore destinations and check your private guide’s availability. Choose your dates and send a booking request to Basma.',
        'blog_list': 'Explore Morocco through travel stories, photographs and local experiences. Find inspiration for your next privately guided journey with Basma.',
        'contact': 'Contact Basma to discuss your Morocco itinerary, dates and group size. Ask a question or explore available tours to request a private journey.',
        'about': 'Discover Basma Morocco Experience and the personal approach behind your Morocco journey, from local connections to thoughtful trip planning.',
    }
    title = titles.get(page, BRAND)
    description = descriptions.get(page, descriptions['home'])
    canonical = morocco_url(request.path_info)
    image = morocco_url(static('img/hero-ma.jpg'))
    image_alt = 'Morocco travel with Basma'
    og_type = 'website'
    demo = False
    if tour is not None:
        title = f'{tour.title} – {tour.destination.name} | {BRAND}'
        description = plain_excerpt(tour.description) or (
            f'Explore {tour.title} in {tour.destination.name}, Morocco. View the itinerary, '
            'check your guide’s availability and request a private tour.'
        )
        if tour.image:
            image = request.build_absolute_uri(tour.image.url)
        image_alt = f'{tour.title}, {tour.destination.name}'
        demo = (tour.slug or '').startswith('demo-')
    elif post is not None:
        title = f'{post.title} | {BRAND}'
        description = plain_excerpt(post.content)
        if post.image:
            image = request.build_absolute_uri(post.image.url)
        image_alt = post.title
        og_type = 'article'
        demo = (post.slug or '').startswith('demo-')

    filtered = page in {'home', 'reservations'} and any(
        request.GET.get(key) for key in ('q', 'date', 'start_date', 'end_date')
    )
    private = page not in PUBLIC_PAGES or demo or is_local_preview(request)
    robots = 'noindex, follow' if private or filtered else 'index, follow, max-image-preview:large'
    root = morocco_url('/')
    guide_id, site_id = root + '#guide', root + '#website'
    graph = [
        {'@type': 'Person', '@id': guide_id, 'name': 'Basma',
         'jobTitle': 'Independent Morocco tour guide', 'url': root},
        {'@type': 'WebSite', '@id': site_id, 'name': BRAND, 'url': root, 'inLanguage': 'en'},
        {'@type': 'WebPage', '@id': canonical + '#webpage', 'url': canonical,
         'name': title, 'description': description, 'inLanguage': 'en',
         'isPartOf': {'@id': site_id}, 'about': {'@id': guide_id}},
    ]
    if tour is not None:
        graph.append({'@type': 'TouristTrip', '@id': canonical + '#trip',
                      'name': tour.title, 'description': description, 'url': canonical,
                      'image': image, 'provider': {'@id': guide_id},
                      'touristType': 'Private travelers and groups'})
    if post is not None:
        graph.append({'@type': 'BlogPosting', '@id': canonical + '#article',
                      'headline': post.title, 'description': description,
                      'datePublished': post.created_at.isoformat(),
                      'mainEntityOfPage': {'@id': canonical + '#webpage'}, 'image': [image]})
    if tour is not None or post is not None:
        section, path = ('Tours', '/reservations/') if tour is not None else ('Our Experiences', '/blog/')
        graph.append({'@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': root},
            {'@type': 'ListItem', 'position': 2, 'name': section, 'item': morocco_url(path)},
            {'@type': 'ListItem', 'position': 3, 'name': tour.title if tour is not None else post.title, 'item': canonical},
        ]})
    # Escape HTML-significant characters before embedding JSON in a script element.
    schema = json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=True)
    schema = schema.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return {'title': title, 'description': description, 'canonical': canonical,
            'image': image, 'image_alt': image_alt, 'og_type': og_type, 'robots': robots,
            'schema': '' if private else schema,
            'published': post.created_at.isoformat() if post is not None else ''}
