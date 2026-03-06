"""
Template filters and tags for performance optimization.
"""
from django import template
from django.utils.safestring import mark_safe
import re

register = template.Library()


@register.filter
def cloudinary_optimize(image_url, params='w_800,f_auto,q_auto'):
    """
    Optimize Cloudinary image URLs for faster delivery.
    
    Usage: {{ image_url|cloudinary_optimize:"w_600,f_auto,q_80" }}
    
    Default parameters optimize for web (auto format, auto quality, max 800px width)
    """
    if not image_url:
        return image_url
    
    # If already a Cloudinary URL, modify it
    if 'res.cloudinary.com' in image_url:
        # Extract the version and resource path
        match = re.search(r'(res\.cloudinary\.com/[^/]+/image/upload/)(.*)', image_url)
        if match:
            base = match.group(1)
            resource = match.group(2)
            return f"{base}{params}/{resource}"
    
    return image_url


@register.filter
def lazy_load_src(image_url):
    """
    Prepare image URL for lazy loading with data-src.
    """
    return image_url


@register.simple_tag
def optimized_image(image_url, width=800, quality='auto', format_type='auto', lazy=True, **kwargs):
    """
    Generate optimized image tag with lazy loading.
    
    Usage: {% optimized_image tour.image.url width=600 quality=80 lazy=True %}
    """
    if not image_url:
        return ''
    
    # Build Cloudinary transformation
    params = f'w_{width},f_{format_type},q_{quality}'
    
    if 'res.cloudinary.com' in image_url:
        match = re.search(r'(res\.cloudinary\.com/[^/]+/image/upload/)(.*)', image_url)
        if match:
            base = match.group(1)
            resource = match.group(2)
            optimized_url = f"{base}{params}/{resource}"
        else:
            optimized_url = image_url
    else:
        optimized_url = image_url
    
    # Generate img tag
    alt_text = kwargs.get('alt', '')
    css_class = kwargs.get('class', '')
    
    if lazy:
        # Use data-src for lazy loading (requires JavaScript)
        img_html = f'<img src="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 16 9%22%3E%3C/svg%3E" data-src="{optimized_url}" alt="{alt_text}" class="lazy {css_class}" loading="lazy">'
    else:
        img_html = f'<img src="{optimized_url}" alt="{alt_text}" class="{css_class}" loading="lazy">'
    
    return mark_safe(img_html)
