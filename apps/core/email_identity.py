from email.utils import formataddr
from django.conf import settings
from .models import SiteSettings, ContactEmailSettings


def email_identity(country):
    site = SiteSettings.objects.filter(pk=1).first() or SiteSettings()
    inbox = ContactEmailSettings.objects.filter(country=country).values_list('recipient_email', flat=True).first() or site.support_email
    sender = formataddr((site.brand_name, site.sender_email)) if site.sender_email else settings.DEFAULT_FROM_EMAIL
    return site.brand_name, sender, inbox
