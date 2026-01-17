from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User


@receiver(post_save, sender=User)
def auto_detect_admin(sender, instance, created, **kwargs):
    """
    Auto-detect if username contains 'admin' and grant staff/superuser permissions
    """
    if 'admin' in instance.username.lower():
        if not instance.is_staff or not instance.is_superuser:
            instance.is_staff = True
            instance.is_superuser = True
            instance.save(update_fields=['is_staff', 'is_superuser'])
