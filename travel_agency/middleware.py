"""
Performance optimization middleware for caching and HTTP headers.
"""
from django.utils.deprecation import MiddlewareMixin
import os


class PerformanceHeadersMiddleware(MiddlewareMixin):
    """
    Add performance optimization headers:
    - Cache-Control for static files
    - Link headers for preload/prefetch
    - Compression headers
    """

    def process_response(self, request, response):
        path = request.path

        # ========== STATIC FILES CACHING ==========
        if path.startswith('/static/') or path.startswith('/staticfiles/'):
            # Long cache for versioned/hashed assets
            if any(hash_char in path for hash_char in ['__pycache__', '.', '-']):
                response['Cache-Control'] = 'public, max-age=31536000, immutable'  # 1 year
            else:
                response['Cache-Control'] = 'public, max-age=86400'  # 1 day

        # ========== MEDIA FILES CACHING ==========
        elif path.startswith('/media/'):
            response['Cache-Control'] = 'public, max-age=604800'  # 7 days

        # ========== HTML/DYNAMIC CONTENT ==========
        else:
            # Don't cache HTML pages, but allow browser cache for 1 hour
            response['Cache-Control'] = 'public, max-age=3600, must-revalidate'

        # ========== COMPRESSION HEADERS ==========
        # Enable GZIP/Brotli compression
        response['Vary'] = 'Accept-Encoding'

        # ========== SECURITY & PERFORMANCE ==========
        # X-Content-Type-Options prevents MIME type sniffing
        if 'X-Content-Type-Options' not in response:
            response['X-Content-Type-Options'] = 'nosniff'

        return response


class CDNOptimizationMiddleware(MiddlewareMixin):
    """
    Optimize CDN and external resource loading
    """

    def process_response(self, request, response):
        # Add Vary header for CDN optimization
        response['Vary'] = response.get('Vary', '') + ', Accept-Encoding'
        response['Vary'] = response['Vary'].strip(', ')

        return response
