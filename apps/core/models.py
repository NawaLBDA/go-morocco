from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from .countries import validate_country, uses_scheduled_departures

from cloudinary.models import CloudinaryField

class Country(models.Model):
    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=False, help_text='Only active countries are offered to travelers.')
    is_visible = models.BooleanField(default=True, db_default=True, verbose_name='Show this country', help_text='Hide this country and its public tours and stories without deleting data. Independent of the coming-soon announcement.')
    coming_soon = models.BooleanField(default=False, help_text='Announcement only: hide tour prices and disable new bookings until ready.')
    uses_scheduled_departures = models.BooleanField(default=True, help_text='Published departures, daily pricing and a private-group guide calendar. Disable for legacy flexible nightly tours.')
    image = models.ImageField(upload_to='img/countries/', blank=True)
    introduction = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    max_concurrent_groups = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)],
        help_text='Maximum private groups guided at the same time across this country. Keep 1 for a small team.')

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = 'Countries'

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.pk and self.max_concurrent_groups:
            from django.utils import timezone
            from apps.reservations.availability import active_reservations, peak_groups
            rows = list(active_reservations(self.slug).filter(end_date__gte=timezone.localdate()).values('start_date', 'end_date'))
            if rows and peak_groups(rows, min(r['start_date'] for r in rows), max(r['end_date'] for r in rows)) > self.max_concurrent_groups:
                raise ValidationError({'max_concurrent_groups': 'Existing groups exceed this limit. Reassign or cancel the affected bookings before lowering it.'})


class CountryLinkedModel(models.Model):
    # Retain the original slug API for integrations; region provides referential integrity.
    region = models.ForeignKey(Country, to_field='slug', on_delete=models.PROTECT,
        related_name='%(class)s_records', editable=False, null=True, blank=True)

    class Meta:
        abstract = True
        constraints = [models.CheckConstraint(
            condition=(models.Q(region__isnull=False, country=models.F('region')) |
                       models.Q(region__isnull=True, country='')),
            name='%(app_label)s_%(class)s_country_link')]

    def clean(self):
        super().clean()
        validate_country(self.country)
        self.region_id = self.country or None

    def save(self, *args, **kwargs):
        self.region_id = self.country or None
        if kwargs.get('update_fields') and 'country' in kwargs['update_fields']:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'region'}
        return super().save(*args, **kwargs)


class SiteSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    brand_name = models.CharField(max_length=100, default='Culture Hop Tours')
    tagline = models.CharField(max_length=180, default='Many cultures. Unforgettable journeys.')
    regions_text = models.CharField(max_length=200, default='Africa • Caribbean • Middle East • Ireland', help_text='Brand horizons, not a list of currently bookable destinations.')
    hero_title = models.CharField(max_length=180, default='Many cultures. Unforgettable journeys.')
    hero_subtitle = models.TextField(default='Different countries, cultures, people and experiences, brought together in journeys that stay with you. Our story begins in Morocco.')
    hero_image = models.ImageField(upload_to='img/site/', blank=True)
    support_email = models.EmailField(default='info@culturehoptours.com', verbose_name='Public contact email', help_text='Contact form and public enquiries. The mailbox must exist with your email provider.')
    booking_email = models.EmailField(default='omasampson@culturehoptours.com', verbose_name='Booking administration inbox', help_text='Receives booking and status notifications in addition to the traveler. Kept separate from the contact inbox.')
    sender_email = models.EmailField(blank=True, help_text='Future professional sender address. Verify it with your email provider before using it. Empty: use server DEFAULT_FROM_EMAIL.')
    whatsapp_number = models.CharField(max_length=25, blank=True, default='')
    christmas_theme = models.BooleanField(default=True, help_text='Show festive styling while a Christmas promotion is active.')
    assistant_enabled = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = 'Global website settings'

    def __str__(self):
        return 'Global website settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)


# =========================
# Destination
# =========================
class Guide(models.Model):
    country = models.ForeignKey(Country, to_field='slug', on_delete=models.PROTECT, related_name='guides')
    name = models.CharField(max_length=120)
    photo = models.ImageField(upload_to='img/guides/', blank=True)
    description = models.TextField()
    is_active = models.BooleanField(default=True, help_text='Only active guides are shown to travelers.')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name', 'pk']

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.pk and self.country_id and (self.tours.exclude(country=self.country_id).exists() or self.assigned_bookings.exclude(tour__country=self.country_id).exists()):
            raise ValidationError({'country': 'Remove this guide from tours in the previous country before changing their country.'})


class Destination(CountryLinkedModel):
    country = models.CharField(max_length=50, default='morocco')
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
class Section(CountryLinkedModel):
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
class BlogPost(CountryLinkedModel):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    content = models.TextField()
    video_url = models.URLField(blank=True, help_text='Optional short trip video; hosted externally.')
    image = CloudinaryField('image', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    story_kind = models.CharField(max_length=20, default='memory', choices=[('memory', 'Travel memory'), ('inspiration', 'Planning inspiration')])
    trip_date = models.DateField(blank=True, null=True, help_text='Date of the past trip represented by this memory.')
    city = models.CharField(max_length=100, blank=True)
    is_demo = models.BooleanField(default=False, help_text='Show a visible demo label for fictional stories and generated images. Uncheck only after replacing them with real content.')
    starter_image = models.CharField(max_length=20, blank=True, choices=[('rabat', 'Demo Rabat group'), ('marrakech', 'Demo Marrakech craft visit'), ('lagos', 'Demo Lagos art visit')], help_text='Initial demo cover; an uploaded image takes priority.')

    country = models.CharField(max_length=50, default='morocco')

    def __str__(self):
        return self.title

    @property
    def cover_url(self):
        if self.image:
            return self.image.url
        from django.templatetags.static import static
        return static(f'img/demo-memory-{self.starter_image}.webp') if self.starter_image in {'rabat', 'marrakech', 'lagos'} else static('img/culture-hop-ch.svg')

    @property
    def memory_date(self):
        from django.utils import timezone
        return self.trip_date or (timezone.localtime(self.created_at).date() if self.created_at else None)



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
class HomeHero(models.Model):
    settings = models.ForeignKey(SiteSettings, on_delete=models.CASCADE, related_name='heroes', default=1)
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=180)
    subtitle = models.TextField(blank=True)
    caption = models.CharField(max_length=180, blank=True)
    image = models.ImageField(upload_to='img/heroes/', blank=True)
    starter_image = models.CharField(max_length=40, blank=True, choices=[('morocco', 'Morocco dunes'), ('nigeria', 'Nigeria landscape illustration')])
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'pk']
        verbose_name_plural = 'Homepage hero slides'

    @property
    def image_url(self):
        from django.templatetags.static import static
        return self.image.url if self.image else static('img/nigeria-hero.webp' if self.starter_image == 'nigeria' else 'img/global-hero.webp')

    def __str__(self):
        return self.title


class ContactEmailSettings(CountryLinkedModel):
    country = models.CharField(max_length=50, unique=True, default='morocco')
    recipient_email = models.EmailField(help_text='Contact form notifications are sent to this address. Outgoing email must also be configured on the server.')

    class Meta:
        verbose_name = 'Contact email settings'
        verbose_name_plural = 'Contact email settings'

    def __str__(self):
        return f'{self.country.title()} contact email'


class BookingNotificationSettings(CountryLinkedModel):
    country = models.CharField(max_length=50, unique=True, default='morocco')
    email_recipients = models.TextField(blank=True, help_text='One staff email address per line.')
    whatsapp_recipients = models.TextField(blank=True, help_text='One staff WhatsApp number per line, including country code, e.g. +212600000000.')
    whatsapp_content_sid = models.CharField(max_length=34, blank=True, help_text='Approved Twilio template Content SID (HX...). See the server setup guide for template variables.')

    class Meta:
        verbose_name_plural = 'Booking notification settings'

    def __str__(self):
        return f'{self.country.title()} booking notifications'

    def clean(self):
        super().clean()
        import re
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        emails = list(dict.fromkeys(x.strip() for x in self.email_recipients.splitlines() if x.strip()))
        phones = list(dict.fromkeys(x.strip() for x in self.whatsapp_recipients.splitlines() if x.strip()))
        for email in emails:
            try:
                validate_email(email)
            except ValidationError:
                raise ValidationError({'email_recipients': 'Enter one valid email address per line.'})
        if any(not re.fullmatch(r'\+[1-9]\d{7,14}', phone) for phone in phones):
            raise ValidationError({'whatsapp_recipients': 'Use international numbers, e.g. +212600000000, one per line.'})
        if phones and not re.fullmatch(r'HX[0-9a-fA-F]{32}', self.whatsapp_content_sid):
            raise ValidationError({'whatsapp_content_sid': 'Enter the approved template Content SID (HX followed by 32 hexadecimal characters).'})
        self.email_recipients = '\n'.join(emails)
        self.whatsapp_recipients = '\n'.join(phones)


class BookingNotification(models.Model):
    reservation = models.ForeignKey('Reservation', on_delete=models.CASCADE, related_name='notifications')
    channel = models.CharField(max_length=10, choices=[('email', 'Email'), ('whatsapp', 'WhatsApp')])
    recipient = models.CharField(max_length=254)
    event = models.CharField(max_length=20, default='requested', choices=[('requested', 'Request received'), ('approved', 'Booking approved'), ('paid', 'Payment received'), ('rejected', 'Booking declined'), ('cancelled', 'Booking cancelled'), ('completed', 'Journey completed')])
    audience = models.CharField(max_length=12, default='staff', choices=[('staff', 'Team'), ('traveler', 'Traveler')])
    context = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, default='pending', choices=[('pending', 'Pending'), ('sending', 'Sending'), ('sent', 'Accepted by provider'), ('failed', 'Failed')])
    error = models.CharField(max_length=255, blank=True)
    provider_reference = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['reservation', 'channel', 'recipient', 'event', 'audience'], name='unique_booking_event_recipient')]

    def __str__(self):
        return f'Booking {self.reservation_id} | {self.channel} | {self.status}'


class ContactMessage(CountryLinkedModel):
    country = models.CharField(max_length=50, blank=True, default='')
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
class Promotion(CountryLinkedModel):
    country = models.CharField(max_length=50, default='morocco')
    name = models.CharField(max_length=120)
    percent = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(100)])
    starts_on = models.DateField(blank=True, null=True)
    ends_on = models.DateField(blank=True, null=True)
    christmas = models.BooleanField(default=False)
    active = models.BooleanField(default=False)
    apply_to_all = models.BooleanField(default=False)

    def clean(self):
        super().clean()
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError({'ends_on': 'The promotion must end on or after its start date.'})

    def __str__(self):
        return f"{self.name} ({self.percent}%)"


# =========================
# Tour
# =========================
from django.db import models
from cloudinary.models import CloudinaryField

class Tour(CountryLinkedModel):
    guides = models.ManyToManyField(Guide, blank=True, related_name='tours',
        help_text='Choose one or more guides from this country. Leave empty to show the active country team.')
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

    package_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(4000)], help_text='USD per person for the complete 14-day journey. Minimum $4,000. Empty only for legacy daily-priced tours.')
    min_travelers = models.PositiveIntegerField(default=5, db_default=5, validators=[MinValueValidator(1)],
        verbose_name='Minimum travelers per group', help_text='Minimum group size for this package. The total is the price per person multiplied by the number of travelers.')
    max_travelers = models.PositiveIntegerField(default=20, db_default=20, validators=[MinValueValidator(1)],
        verbose_name='Maximum travelers per group', help_text='Maximum for this package. An individual departure may have a lower capacity.')
    package_days = models.PositiveIntegerField(default=14, db_default=14, validators=[MinValueValidator(14), MaxValueValidator(14)])
    price_per_night = models.DecimalField(max_digits=8, decimal_places=2)
    max_days = models.PositiveIntegerField(default=14, validators=[MinValueValidator(1)],
        help_text="Morocco: maximum days per departure, including arrival and departure days. Increase this before adding longer departures.")
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
    discount_percent = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    deaf_only = models.BooleanField(default=False, verbose_name='Deaf travelers only', help_text='Only accounts registered as deaf can book this tour.')
    explanation_video_url = models.URLField(blank=True, help_text="Accessible explanatory video for this tour.")

    country = models.CharField(max_length=50, default='morocco')

    @property
    def group_minimum(self):
        return self.min_travelers if self.package_price is not None else 1

    @property
    def display_price(self):
        return self.package_price if self.package_price is not None else self.price_per_night

    @property
    def cover_url(self):
        if self.image:
            return self.image.url
        from django.templatetags.static import static
        if self.country == 'ireland':
            return static('img/ireland-howth-starter.webp')
        if self.country == 'nigeria':
            return static('img/nigeria-hero.webp')
        images = {'demo-marrakech-atlas': 'morocco-marrakech-starter.webp', 'demo-sahara-stars': 'global-hero.webp',
                  'demo-chefchaouen': 'hero3.jpeg', 'demo-marrakech-culture': 'morocco-marrakech-starter.webp'}
        return static('img/' + images.get(self.slug, 'hero4.jpeg'))

    @property
    def guiding_team(self):
        assigned = self.guides.all()
        if assigned.exists():
            return assigned.filter(is_active=True, country_id=self.country).select_related('country')
        return Guide.objects.filter(country_id=self.country, is_active=True).select_related('country')

    def clean(self):
        super().clean()
        if self.min_travelers and self.max_travelers and self.min_travelers > self.max_travelers:
            raise ValidationError({'max_travelers': 'The maximum must be at least the minimum group size.'})
        if self.pk and self.package_price is not None and self.departures.filter(is_published=True, max_participants__lt=self.min_travelers).exists():
            raise ValidationError({'min_travelers': 'A published departure has a lower capacity. Increase its capacity or unpublish it first.'})
        if self.pk and self.guides.exclude(country_id=self.country).exists():
            raise ValidationError({'country': 'Remove the guides from the previous country before changing this tour country.'})
        if self.destination_id and self.destination.country != self.country:
            raise ValidationError({'destination': 'The destination must belong to the tour country.'})
        if self.pk and self.max_days and uses_scheduled_departures(self.country):
            if any(departure.duration_days > self.max_days for departure in self.departures.filter(is_published=True)):
                raise ValidationError({'max_days': 'An existing published departure exceeds this limit. Update or unpublish it first.'})

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


class TourDeparture(models.Model):
    deaf_only = models.BooleanField(default=False, verbose_name='Deaf travelers only',
        help_text='Only accounts registered as deaf can book these dates.')

    @property
    def requires_deaf(self):
        return self.deaf_only or self.tour.deaf_only

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='departures')
    start_date = models.DateField()
    end_date = models.DateField(help_text="For a one-day tour, use the same start and end date.")
    is_published = models.BooleanField(default=False)
    max_participants = models.PositiveIntegerField(default=20, validators=[MinValueValidator(1)])
    max_concurrent_bookings = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)],
        help_text='Maximum independent groups on this departure. Also limited by the country team capacity. Each group has its own maximum participants.')

    class Meta:
        ordering = ['start_date', 'end_date', 'pk']
        constraints = [models.UniqueConstraint(fields=['tour', 'start_date', 'end_date'], name='unique_tour_departure')]

    @property
    def group_minimum(self):
        return self.tour.group_minimum

    @property
    def group_maximum(self):
        return min(self.max_participants, self.tour.max_travelers)

    @property
    def duration_days(self):
        return (self.end_date - self.start_date).days + 1

    @property
    def active_days(self):
        return self.program_days.filter(is_visible=True).count()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.sync_programme()

    def sync_programme(self):
        """Dates follow the tour's numbered itinerary; reserved programmes stay fixed."""
        if self.reservations.filter(status__in=['pending', 'booked', 'completed']).exists():
            return
        self.program_days.filter(day_number__gt=self.duration_days).delete()
        for number in range(1, self.duration_days + 1):
            day, _ = self.program_days.get_or_create(day_number=number)
            day.activities.set(self.tour.activity_cards.filter(day_number=number, is_active=True))

    def __str__(self):
        return f"{self.tour} | {self.start_date} to {self.end_date}"

    def clean(self):
        super().clean()
        if not self.start_date or not self.end_date or not self.tour_id:
            return
        if self.max_participants and self.max_participants < self.tour.group_minimum:
            raise ValidationError({'max_participants': 'Departure capacity must be at least the package minimum group size.'})
        if self.end_date < self.start_date:
            raise ValidationError({'end_date': 'End date cannot be before start date.'})
        if self.tour.package_price is not None and self.duration_days != self.tour.package_days and not (self.pk and self.reservations.exists()):
            raise ValidationError({'end_date': 'Package departures must last exactly 14 days, including arrival and departure.'})
        if self.duration_days > self.tour.max_days:
            raise ValidationError({'end_date': f'This tour allows {self.tour.max_days} days. Increase Maximum days in the tour settings first.'})
        if self.pk:
            active = self.reservations.filter(status__in=['pending', 'booked'])
            if self.max_concurrent_bookings and active.count() > self.max_concurrent_bookings:
                raise ValidationError({'max_concurrent_bookings': 'This departure already has more reserved groups than this limit.'})
            if self.max_participants and active.filter(num_persons__gt=self.max_participants).exists():
                raise ValidationError({'max_participants': 'An existing group exceeds this maximum. Review its booking before lowering it.'})
            if self.reservations.filter(status__in=['pending', 'booked']).exclude(
                start_date=self.start_date, end_date=self.end_date, tour_id=self.tour_id).exists():
                raise ValidationError('This departure has reservations. Create a new departure instead of changing its dates or tour.')


class DepartureDay(models.Model):
    departure = models.ForeignKey(TourDeparture, on_delete=models.CASCADE, related_name='program_days')
    day_number = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    title = models.CharField(max_length=200, blank=True)
    is_visible = models.BooleanField(default=True, verbose_name="Include this day",
        help_text="Disabled days are excluded from the programme, billable duration and price. The guide remains reserved for the whole departure window.")
    activities = models.ManyToManyField('TourActivity', blank=True, related_name='departure_days')

    class Meta:
        ordering = ['day_number', 'pk']
        constraints = [models.UniqueConstraint(fields=['departure', 'day_number'], name='unique_departure_program_day')]

    def __str__(self):
        return f"Day {self.day_number}: {self.title}"

    def clean(self):
        super().clean()
        if self.departure_id and self.day_number and self.day_number > self.departure.duration_days:
            raise ValidationError({'day_number': 'This day is outside the departure dates.'})


class TourActivity(models.Model):
    """Structured tour activity with optional image and precise place details."""

    POINT_REGULAR = 'regular'
    POINT_START = 'start'
    POINT_END = 'end'
    POINT_ROLE_CHOICES = (
        (POINT_REGULAR, 'Regular stop'),
        (POINT_START, 'Starting point'),
        (POINT_END, 'Ending point'),
    )

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='activity_cards')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = CloudinaryField('image', blank=True, null=True)
    city = models.CharField(max_length=120, blank=True)
    place_name = models.CharField(max_length=200, blank=True)
    day_number = models.PositiveIntegerField(default=1, help_text="Example: 1 for Day 1, 2 for Day 2.")
    point_role = models.CharField(max_length=20, choices=POINT_ROLE_CHOICES, default=POINT_REGULAR)
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    latitude = models.DecimalField(max_digits=18, decimal_places=15, blank=True, null=True)
    longitude = models.DecimalField(max_digits=18, decimal_places=15, blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['day_number', 'display_order', 'id']

    def __str__(self):
        return f"{self.tour.title} - {self.title}"

    @property
    def location_display(self):
        parts = [part.strip() for part in [self.place_name, self.city] if (part or '').strip()]
        return ', '.join(parts)

    @property
    def map_query(self):
        if self.latitude is not None and self.longitude is not None:
            return f"{self.latitude},{self.longitude}"
        return self.location_display or self.title

    @property
    def map_url(self):
        query = (self.map_query or '').strip()
        if not query:
            return ''
        return f"https://www.google.com/maps/search/?api=1&query={query.replace(' ', '+')}"


class TourItineraryLeg(models.Model):
    TRANSPORT_WALK = 'walk'
    TRANSPORT_BUS = 'bus'
    TRANSPORT_TAXI = 'taxi'
    TRANSPORT_INDRIVE = 'indrive'
    TRANSPORT_TRAMWAY = 'tramway'
    TRANSPORT_PRIVATE = 'private'
    TRANSPORT_CAR = 'car'
    TRANSPORT_OTHER = 'other'
    TRANSPORT_CHOICES = (
        (TRANSPORT_WALK, 'On foot'),
        (TRANSPORT_BUS, 'Bus'),
        (TRANSPORT_TAXI, 'Taxi'),
        (TRANSPORT_INDRIVE, 'InDrive'),
        (TRANSPORT_TRAMWAY, 'Tramway'),
        (TRANSPORT_PRIVATE, 'Private transport'),
        (TRANSPORT_CAR, 'Car'),
        (TRANSPORT_OTHER, 'Other'),
    )

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='itinerary_legs')
    from_activity = models.ForeignKey(TourActivity, on_delete=models.CASCADE, related_name='outgoing_legs')
    to_activity = models.ForeignKey(TourActivity, on_delete=models.CASCADE, related_name='incoming_legs')
    distance_label = models.CharField(max_length=80, help_text="Example: 200 m, 3 min, 12 km")
    transport_mode = models.CharField(max_length=20, choices=TRANSPORT_CHOICES, default=TRANSPORT_WALK)
    transport_label = models.CharField(max_length=80, blank=True, help_text="Optional custom label, for example: On foot, Small boat")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'id']
        unique_together = [('tour', 'from_activity', 'to_activity')]

    def __str__(self):
        return f"{self.from_activity.title} -> {self.to_activity.title}"

    @property
    def transport_display_label(self):
        return (self.transport_label or self.get_transport_mode_display() or '').strip()


class TourExtraActivity(models.Model):
    """Optional add-on activity priced per tour."""

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='extra_activities')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = CloudinaryField('image', blank=True, null=True)
    city = models.CharField(max_length=120, blank=True)
    place_name = models.CharField(max_length=200, blank=True)
    latitude = models.DecimalField(max_digits=18, decimal_places=15, blank=True, null=True)
    longitude = models.DecimalField(max_digits=18, decimal_places=15, blank=True, null=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    is_per_night = models.BooleanField(
        default=False,
        help_text="If enabled, the price is charged per night per person. Otherwise per trip per person.",
    )
    insert_into_itinerary = models.BooleanField(
        default=False,
        help_text="If enabled, this extra activity will be inserted into the day itinerary when selected.",
    )
    itinerary_day_number = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Example: 1 for Day 1, 2 for Day 2.",
    )
    itinerary_start_time = models.TimeField(blank=True, null=True)
    itinerary_duration_minutes = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Duration in minutes used to shift the following itinerary stops.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.tour.title} - {self.title}"

    @property
    def location_display(self):
        parts = [part.strip() for part in [self.place_name, self.city] if (part or '').strip()]
        return ', '.join(parts)

    @property
    def has_map_location(self):
        return self.latitude is not None and self.longitude is not None or bool(self.location_display)

    @property
    def map_query(self):
        if self.latitude is not None and self.longitude is not None:
            return f"{self.latitude},{self.longitude}"
        if self.location_display:
            return self.location_display
        return ''

    @property
    def map_url(self):
        query = (self.map_query or '').strip()
        if not query:
            return ''
        return f"https://www.google.com/maps/search/?api=1&query={query.replace(' ', '+')}"


class Information(CountryLinkedModel):
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
class GuideCalendar(CountryLinkedModel):
    """Lock row for the independent guide's shared booking calendar."""
    country = models.CharField(max_length=50, unique=True)


class Reservation(models.Model):
    assigned_guides = models.ManyToManyField(Guide, blank=True, related_name='assigned_bookings',
        help_text='Optional confirmed guides for this private group. Guides cannot overlap another active booking.')
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
        ('transfer', 'Bank transfer'),
    )

    PAYMENT_STATUS = (
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reservations')
    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='reservations')
    departure = models.ForeignKey(TourDeparture, on_delete=models.PROTECT, null=True, blank=True, related_name='reservations')
    package_priced = models.BooleanField(default=False, db_default=False, editable=False)
    priced_per_day = models.BooleanField(default=False, editable=False)
    booked_days = models.PositiveIntegerField(null=True, blank=True, editable=False)

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

    def clean(self):
        super().clean()
        from apps.reservations.availability import validate_reservation
        validate_reservation(self)
        if self.departure_id and self.num_persons > self.departure.max_participants:
            raise ValidationError({'num_persons': 'The group exceeds this departure capacity.'})

    def save(self, *args, **kwargs):
        if self.tour_id and uses_scheduled_departures(self.tour.country):
            from apps.reservations.availability import lock_guide_calendar, validate_reservation
            with lock_guide_calendar(self.tour.country):
                validate_reservation(self)
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)


    @property
    def guiding_team(self):
        return self.assigned_guides.filter(is_active=True, country_id=self.tour.country).select_related('country')

    @property
    def nights(self):
        return max(0, (self.end_date - self.start_date).days)

    @property
    def duration_days(self):
        return self.booked_days if self.booked_days is not None else (self.nights + 1 if self.priced_per_day else self.nights)


class WaitlistEntry(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='waitlist_entries')
    departure = models.ForeignKey(TourDeparture, on_delete=models.PROTECT, related_name='waitlist_entries')
    num_persons = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    email = models.EmailField(help_text='Address for the decision, provided by the traveler.')
    message = models.TextField(blank=True)
    status = models.CharField(max_length=12, default='waiting', choices=[
        ('waiting', 'Waiting for review'), ('accepted', 'Accepted'), ('rejected', 'Declined')])
    reservation = models.OneToOneField(Reservation, on_delete=models.PROTECT, null=True, blank=True, related_name='waitlist_entry')
    decision_note = models.TextField(blank=True)
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='waitlist_decisions')
    decided_at = models.DateTimeField(null=True, blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [models.UniqueConstraint(fields=['user', 'departure'], name='unique_user_departure_waitlist')]

    def __str__(self):
        return f'{self.user} | {self.departure} | {self.get_status_display()}'
# =========================
# Country Content
# =========================
class CountryContent(CountryLinkedModel):
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
    is_deaf = models.BooleanField(default=False, verbose_name='Deaf', help_text='Voluntarily indicated by the account holder at registration.')
    phone = models.CharField(max_length=20)
    country = models.CharField(max_length=80)
    postal_code = models.CharField(max_length=20)

    def __str__(self):
        return self.user.username
