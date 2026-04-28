from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify

from cloudinary.models import CloudinaryField

# =========================
# Destination
# =========================
class Destination(models.Model):
    name = models.CharField(max_length=150)
    image = models.ImageField(upload_to='img/destinations/', blank=True, null=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class DestinationImage(models.Model):
    destination = models.ForeignKey(
        Destination,
        on_delete=models.CASCADE,
        related_name='gallery'
    )
    image = models.ImageField(upload_to='img/destinations/gallery/')

    def __str__(self):
        return f"Image for {self.destination.name}"


# =========================
# Sections (Pages content)
# =========================
class Section(models.Model):
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    content = models.TextField(blank=True)
    image = models.ImageField(upload_to='img/sections/', blank=True, null=True)
    order = models.IntegerField(default=0)
    show_in_nav = models.BooleanField(default=True)

    country = models.CharField(max_length=50, default='morocco')

    def __str__(self):
        return self.title


# =========================
# Blog
# =========================
class BlogPost(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    content = models.TextField()
    image = CloudinaryField('image', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    country = models.CharField(max_length=50, default='morocco')

    def __str__(self):
        return self.title



class BlogImage(models.Model):
    post = models.ForeignKey(
        BlogPost,
        on_delete=models.CASCADE,
        related_name='gallery'
    )
    image = CloudinaryField('image')

    def __str__(self):
        return f"Image for {self.post.title}"



class BlogComment(models.Model):
    post = models.ForeignKey(
        BlogPost,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.post.title}"


# =========================
# Contact
# =========================
class ContactMessage(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField()
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.subject or 'Contact'}"


# =========================
# Promotion
# =========================
class Promotion(models.Model):
    name = models.CharField(max_length=120)
    percent = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=False)
    apply_to_all = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.percent}%)"


# =========================
# Tour
# =========================
from django.db import models
from cloudinary.models import CloudinaryField

class Tour(models.Model):
    destination = models.ForeignKey(Destination, on_delete=models.CASCADE, related_name='tours')
    title = models.CharField(max_length=200)

    slug = models.SlugField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text="URL slug (auto-generated).",
    )

    image = CloudinaryField('image', blank=True, null=True)

    price_per_night = models.DecimalField(max_digits=8, decimal_places=2)
    description = models.TextField(blank=True)

    transport = models.CharField(max_length=255, blank=True)
    transport_price_per_night = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Optional: transport add-on price per night per person.",
    )
    hotel = models.CharField(max_length=255, blank=True)
    hotel_price_per_night = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Optional: hotel add-on price per night per person.",
    )
    activities = models.TextField(blank=True)

    included = models.TextField(blank=True, help_text="What is included (one item per line).")
    not_included = models.TextField(blank=True, help_text="What is NOT included (one item per line).")

    is_promotion = models.BooleanField(default=False)
    discount_percent = models.IntegerField(default=0)

    country = models.CharField(max_length=50, default='morocco')

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(f"{getattr(self.destination, 'name', '')}-{self.title}") or slugify(self.title) or 'tour'
            slug = base
            i = 2
            while Tour.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{i}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)


class TourExtraActivity(models.Model):
    """Optional add-on activity priced per tour."""

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='extra_activities')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    is_per_night = models.BooleanField(
        default=False,
        help_text="If enabled, the price is charged per night per person. Otherwise per trip per person.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.tour.title} - {self.title}"


class Information(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    file = models.FileField(upload_to='information_files/', blank=True, null=True)
    country = models.CharField(max_length=50, default='morocco')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class ChatMessage(models.Model):
    ROLE_CHOICES = (
        ('user', 'User'),
        ('bot', 'Bot'),
    )
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, null=True, blank=True)
    session_key = models.CharField(max_length=255, blank=True, null=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.role}: {self.message[:30]}'


# =========================
# Reservation (BOOKING)
# =========================
class Reservation(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('booked', 'Booked'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    )

    PAYMENT_CHOICES = (
        ('cash', 'Cash'),
        ('card', 'Card Payment'),
    )

    PAYMENT_STATUS = (
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reservations')
    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='reservations')

    start_date = models.DateField()
    end_date = models.DateField()

    num_persons = models.PositiveIntegerField(default=1)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Package selections (pricing is computed server-side)
    full_package = models.BooleanField(default=False)
    include_transport = models.BooleanField(default=False)
    include_hotel = models.BooleanField(default=False)
    selected_extra_activities = models.JSONField(default=list, blank=True)
    extras_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Snapshot of prices at booking time (so totals remain auditable if Tour pricing changes)
    base_price_per_night = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    transport_price_per_night = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    hotel_price_per_night = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    booking_for_other = models.BooleanField(default=False)
    guest_full_name = models.CharField(max_length=150, blank=True)
    guest_phone = models.CharField(max_length=30, blank=True)

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')

    payment_method = models.CharField(
        max_length=10,
        choices=PAYMENT_CHOICES,
        null=True,
        blank=True,
        default=None,
    )
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS, default='unpaid')

    stripe_payment_intent = models.CharField(max_length=255, blank=True, null=True)

    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.tour.title} ({self.status})"


    @property
    def nights(self):
        return max(0, (self.end_date - self.start_date).days)
# =========================
# Country Content
# =========================
class CountryContent(models.Model):
    country = models.CharField(max_length=50, unique=True)
    hero_title = models.CharField(max_length=200, default="Discover Morocco")
    hero_subtitle = models.TextField(blank=True)
    hero_image = models.ImageField(upload_to='img/heroes/', blank=True, null=True)

    def __str__(self):
        return f"Content for {self.country}"

# =========================
# Profile user
# =========================
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20)
    country = models.CharField(max_length=80)
    postal_code = models.CharField(max_length=20)

    def __str__(self):
        return self.user.username
