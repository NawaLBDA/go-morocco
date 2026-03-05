#!/usr/bin/env python
"""
Security & Performance Check Script
Run before deploying to production
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'travel_agency.settings')

import django
django.setup()

from django.core.management import call_command
from django.conf import settings

print("=" * 70)
print("🔒 SECURITY & PERFORMANCE CHECK")
print("=" * 70)

# 1. Check Django Security Issues
print("\n✅ Running Django security check...")
try:
    call_command('check', '--deploy', verbosity=0)
    print("   ✓ No critical security issues found")
except SystemExit:
    print("   ⚠️ Some warnings found (check above)")

# 2. Check Settings
print("\n📋 SETTINGS CHECK:")
print(f"   DEBUG: {settings.DEBUG} {'✓' if not settings.DEBUG else '❌ MUST BE FALSE IN PRODUCTION'}")
print(f"   ENVIRONMENT: {os.environ.get('ENVIRONMENT', 'Not set')}")
print(f"   SECURE_SSL_REDIRECT: {settings.SECURE_SSL_REDIRECT if hasattr(settings, 'SECURE_SSL_REDIRECT') else 'Not set'}")
print(f"   SECRET_KEY: {'***hidden***' if settings.SECRET_KEY else 'NOT SET ❌'}")
print(f"   ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}")

# 3. Database Check
print("\n🗄️  DATABASE CHECK:")
db_url = os.environ.get('DATABASE_URL')
if db_url:
    print(f"   ✓ DATABASE_URL is set")
    if 'postgresql' in db_url:
        print(f"   ✓ Using PostgreSQL (recommended)")
else:
    print(f"   ⚠️ DATABASE_URL not set (using local database)")

# 4. Static Files Check
print("\n📦 STATIC FILES:")
print(f"   STATIC_URL: {settings.STATIC_URL}")
print(f"   STATIC_ROOT: {settings.STATIC_ROOT}")
print(f"   Storage: {settings.STATICFILES_STORAGE}")

# 5. Caching Check
print("\n⚡ CACHING:")
print(f"   Cache Backend: {settings.CACHES['default']['BACKEND']}")
print(f"   Session Engine: {settings.SESSION_ENGINE}")

# 6. Cloudinary Check
print("\n🖼️  CLOUDINARY (Images):")
cloudinary_configured = (
    os.environ.get('CLOUDINARY_CLOUD_NAME') and
    os.environ.get('CLOUDINARY_API_KEY') and
    os.environ.get('CLOUDINARY_API_SECRET')
)
if cloudinary_configured:
    print(f"   ✓ Cloudinary configured")
else:
    print(f"   ⚠️ Cloudinary not configured (optional but recommended)")

# 7. Stripe Check
print("\n💳 STRIPE:")
stripe_configured = (
    settings.STRIPE_SECRET_KEY and
    settings.STRIPE_PUBLIC_KEY
)
if stripe_configured:
    print(f"   ✓ Stripe configured")
else:
    print(f"   ⚠️ Stripe not configured")

# 8. HTTPS/Security Headers
print("\n🔐 HTTPS & SECURITY HEADERS:")
is_production = os.environ.get('ENVIRONMENT') == 'production'
print(f"   Production Mode: {is_production}")
if is_production:
    print(f"   ✓ SECURE_SSL_REDIRECT: {settings.SECURE_SSL_REDIRECT}")
    print(f"   ✓ HSTS enabled: {hasattr(settings, 'SECURE_HSTS_SECONDS')}")
    print(f"   ✓ Secure cookies: {settings.SESSION_COOKIE_SECURE}")
else:
    print(f"   ℹ️ Not in production mode - some security features disabled")

print("\n" + "=" * 70)
print("✅ CHECK COMPLETE!")
print("=" * 70)
print("\nNext steps:")
print("1. Review any warnings above")
print("2. Set all environment variables in Render")
print("3. Push to GitHub: git push origin main")
print("4. Check Render deployment logs")
print("=" * 70)
