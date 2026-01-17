from django.db import models
from django.contrib.auth.models import User


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

    def __str__(self):
        return self.title


# =========================
# Blog
# =========================
class BlogPost(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    content = models.TextField()
    image = models.ImageField(upload_to='img/blog/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class BlogImage(models.Model):
    post = models.ForeignKey(
        BlogPost,
        on_delete=models.CASCADE,
        related_name='gallery'
    )
    image = models.ImageField(upload_to='img/blog/gallery/')

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
class Tour(models.Model):
    destination = models.ForeignKey(Destination, on_delete=models.CASCADE, related_name='tours')
    title = models.CharField(max_length=200)
    image = models.ImageField(upload_to='img/tours/', blank=True, null=True)
    price_per_night = models.DecimalField(max_digits=8, decimal_places=2)
    description = models.TextField(blank=True)

    transport = models.CharField(max_length=255, blank=True)
    hotel = models.CharField(max_length=255, blank=True)
    activities = models.TextField(blank=True)

    is_promotion = models.BooleanField(default=False)
    discount_percent = models.IntegerField(default=0)

    def __str__(self):
        return self.title


# =========================
# Reservation (BOOKING)
# =========================
class Reservation(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('booked', 'Booked'),
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

    booking_for_other = models.BooleanField(default=False)
    guest_full_name = models.CharField(max_length=150, blank=True)
    guest_phone = models.CharField(max_length=30, blank=True)

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')

    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default='cash')
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
# Profile user
# =========================
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20)
    country = models.CharField(max_length=80)
    postal_code = models.CharField(max_length=20)

    def __str__(self):
        return self.user.username
