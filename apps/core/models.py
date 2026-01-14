
from django.db import models

class Destination(models.Model):
    name = models.CharField(max_length=150)
    image = models.ImageField(upload_to='img/destinations/', blank=True, null=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Section(models.Model):
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    content = models.TextField(blank=True)
    image = models.ImageField(upload_to='img/sections/', blank=True, null=True)
    order = models.IntegerField(default=0)
    show_in_nav = models.BooleanField(default=True)

    def __str__(self):
        return self.title


class BlogPost(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    content = models.TextField()
    image = models.ImageField(upload_to='img/blog/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class ContactMessage(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField()
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.subject or 'Contact'}"


class Promotion(models.Model):
    name = models.CharField(max_length=120)
    percent = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=False)
    apply_to_all = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.percent}%)"


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

    def discounted_price(self):
        base = self.price_per_night
        if self.is_promotion and self.discount_percent:
            return base - (base * self.discount_percent / 100)
        # check global promotion
        global_promo = Promotion.objects.filter(active=True, apply_to_all=True).first()
        if global_promo:
            return base - (base * global_promo.percent / 100)
        return base
