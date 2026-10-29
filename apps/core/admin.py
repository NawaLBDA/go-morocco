from apps.core.countries import uses_scheduled_departures
from decimal import Decimal, InvalidOperation
from datetime import timedelta

from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.html import format_html, format_html_join
from .models import (
    Destination, DestinationImage,
    Tour, Reservation,
    Section,
    BlogPost, BlogImage,
    Promotion,
    ContactMessage, ContactEmailSettings, BookingNotificationSettings, BookingNotification,
    Information, ChatMessage,
    TourExtraActivity,
    TourActivity,
    TourItineraryLeg,
    TourDeparture, DepartureDay,
    CountryContent, Guide,
)
from django.forms.models import BaseInlineFormSet


def _parse_coordinates(value: str):
    raw = (value or '').strip()
    if not raw:
        return None, None

    parts = [p.strip() for p in raw.split(',')]
    if len(parts) != 2:
        raise forms.ValidationError("Use format: latitude, longitude")

    try:
        latitude = Decimal(parts[0])
        longitude = Decimal(parts[1])
    except (InvalidOperation, ValueError):
        raise forms.ValidationError("Coordinates must be valid numbers like: 34.0318501020754, -6.835778065718815")

    return latitude, longitude


class TourActivityAdminForm(forms.ModelForm):
    map_search = forms.CharField(
        required=False,
        help_text="Search a place or click directly on the map below.",
        label="Map search",
    )
    coordinates = forms.CharField(
        required=False,
        help_text="Paste coordinates or a Google Maps value, for example: 34.0318501020754, -6.835778065718815",
        label="Coordinates",
        widget=forms.TextInput(),
    )

    class Meta:
        model = TourActivity
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'cols': 60}),
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
        }

    class Media:
        css = {
            'all': (
                'admin/css/tour_map_picker.css',
            )
        }
        js = (
            'admin/js/tour_map_picker.js',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.latitude is not None and self.instance.longitude is not None:
            self.fields['coordinates'].initial = f"{self.instance.latitude}, {self.instance.longitude}"
        if self.instance and self.instance.pk and self.instance.location_display:
            self.fields['map_search'].initial = self.instance.location_display

    def clean(self):
        cleaned_data = super().clean()
        coordinates_value = cleaned_data.get('coordinates', '')
        latitude = cleaned_data.get('latitude')
        longitude = cleaned_data.get('longitude')
        if coordinates_value:
            latitude, longitude = _parse_coordinates(coordinates_value)
        cleaned_data['latitude'] = latitude
        cleaned_data['longitude'] = longitude
        return cleaned_data


class TourExtraActivityAdminForm(forms.ModelForm):
    map_search = forms.CharField(
        required=False,
        help_text="Search a place or click directly on the map below.",
        label="Map search",
    )
    coordinates = forms.CharField(
        required=False,
        help_text="Paste coordinates or a Google Maps value, for example: 34.0318501020754, -6.835778065718815",
        label="Coordinates",
        widget=forms.TextInput(),
    )

    class Meta:
        model = TourExtraActivity
        fields = '__all__'
        widgets = {
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
        }

    class Media:
        css = {
            'all': (
                'admin/css/tour_map_picker.css',
            )
        }
        js = (
            'admin/js/tour_map_picker.js',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.latitude is not None and self.instance.longitude is not None:
            self.fields['coordinates'].initial = f"{self.instance.latitude}, {self.instance.longitude}"
        if self.instance and self.instance.pk and self.instance.location_display:
            self.fields['map_search'].initial = self.instance.location_display

    def clean(self):
        cleaned_data = super().clean()
        coordinates_value = cleaned_data.get('coordinates', '')
        latitude = cleaned_data.get('latitude')
        longitude = cleaned_data.get('longitude')
        if coordinates_value:
            latitude, longitude = _parse_coordinates(coordinates_value)
        cleaned_data['latitude'] = latitude
        cleaned_data['longitude'] = longitude
        if cleaned_data.get('insert_into_itinerary'):
            if not cleaned_data.get('itinerary_day_number'):
                self.add_error('itinerary_day_number', "Choose the itinerary day for this extra activity.")
            if not cleaned_data.get('itinerary_start_time'):
                self.add_error('itinerary_start_time', "Choose the start time for this extra activity.")
            duration = cleaned_data.get('itinerary_duration_minutes')
            if not duration or int(duration) <= 0:
                self.add_error('itinerary_duration_minutes', "Enter a duration in minutes greater than 0.")
        return cleaned_data


class TourItineraryLegAdminForm(forms.ModelForm):
    class Meta:
        model = TourItineraryLeg
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        tour = kwargs.pop('tour_instance', None)
        super().__init__(*args, **kwargs)
        queryset = TourActivity.objects.none()

        if self.instance and self.instance.pk:
            queryset = TourActivity.objects.filter(
                tour=self.instance.tour
            ).order_by('display_order', 'id')
        elif tour and getattr(tour, 'pk', None):
            queryset = TourActivity.objects.filter(
                tour=tour
            ).order_by('display_order', 'id')

        self.fields['from_activity'].queryset = queryset
        self.fields['to_activity'].queryset = queryset

    def clean(self):
        cleaned_data = super().clean()
        from_activity = cleaned_data.get('from_activity')
        to_activity = cleaned_data.get('to_activity')

        if from_activity and to_activity:
            if from_activity == to_activity:
                raise forms.ValidationError("From and to itinerary stops must be different.")
            if from_activity.tour_id != to_activity.tour_id:
                raise forms.ValidationError("Both itinerary stops must belong to the same tour.")
            if (from_activity.day_number or 1) != (to_activity.day_number or 1):
                raise forms.ValidationError("Both itinerary stops must belong to the same day.")

        return cleaned_data


class TourItineraryLegInlineFormSet(BaseInlineFormSet):
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['tour_instance'] = self.instance
        return kwargs


class CountryScopedAdmin(admin.ModelAdmin):
    country_lookup = 'country'

    def get_list_filter(self, request):
        return (self.country_lookup,) + tuple(super().get_list_filter(request))

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'country':
            from .models import Country
            return forms.ChoiceField(choices=[(c.slug, c.name) for c in Country.objects.all()], label='Country')
        return super().formfield_for_dbfield(db_field, request, **kwargs)



class DestinationImageInline(admin.TabularInline):
    model = DestinationImage
    extra = 3


@admin.register(Destination)
class DestinationAdmin(CountryScopedAdmin):
    list_display = ('name',)
    inlines = [DestinationImageInline]


@admin.register(Information)
class InformationAdmin(CountryScopedAdmin):
    list_display = ('title', 'country', 'created_at')
    search_fields = ('title', 'content')
    list_filter = ('country',)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'created_at')
    list_filter = ('role', 'user')
    search_fields = ('message',)


class TourExtraActivityInline(admin.StackedInline):
    classes = ('collapse',)
    model = TourExtraActivity
    form = TourExtraActivityAdminForm
    extra = 1
    verbose_name = "Extra itinerary option"
    verbose_name_plural = "Extra itinerary options"
    fields = (
        'title', 'description', 'image',
        'city', 'place_name', 'map_search', 'coordinates', 'latitude', 'longitude',
        'price', 'is_per_night',
        'insert_into_itinerary', 'itinerary_day_number', 'itinerary_start_time', 'itinerary_duration_minutes',
        'is_active',
    )

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        if obj is None or uses_scheduled_departures(obj.country):
            formset.form.base_fields['is_per_night'].label = 'Charge per included day'
        return formset


class TourActivityInline(admin.StackedInline):
    model = TourActivity
    form = TourActivityAdminForm
    extra = 1
    verbose_name = "Tour itinerary stop"
    verbose_name_plural = "Tour itinerary"
    fields = (
        'title', 'description', 'image',
        'day_number', 'point_role',
        'city', 'place_name', 'start_time', 'end_time', 'map_search', 'coordinates', 'latitude', 'longitude',
        'display_order', 'is_active',
    )


class TourItineraryLegInline(admin.TabularInline):
    classes = ('collapse',)
    model = TourItineraryLeg
    form = TourItineraryLegAdminForm
    formset = TourItineraryLegInlineFormSet
    extra = 1
    verbose_name = "Itinerary route segment"
    verbose_name_plural = "Itinerary route segments"
    fields = (
        'from_activity', 'to_activity', 'distance_label',
        'display_order', 'is_active',
    )


class TourDepartureFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        for form in self.forms:
            data = form.cleaned_data
            if not data or data.get('DELETE'):
                continue
            start, end = data.get('start_date'), data.get('end_date')
            if start and end and (end - start).days + 1 > self.instance.max_days:
                raise forms.ValidationError(f'Departures must be at most {self.instance.max_days} days. Increase the tour maximum first.')


class TourDepartureAdminForm(forms.ModelForm):
    end_date = forms.DateField(required=False, widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        help_text='Calculated from the start date and the tour maximum. You may shorten the period, including to one day.')

    class Meta:
        model = TourDeparture
        fields = '__all__'
        widgets = {'start_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})}

    class Media:
        js = ('admin/js/departure_dates.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['max_concurrent_bookings'].required = False

    def clean(self):
        data = super().clean()
        data['max_concurrent_bookings'] = data.get('max_concurrent_bookings') or self.instance.max_concurrent_bookings or 1
        tour = data.get('tour') or (self.instance.tour if self.instance.tour_id else None)
        if data.get('start_date') and not data.get('end_date') and tour:
            data['end_date'] = data['start_date'] + timedelta(days=tour.max_days - 1)
        return data


class TourDepartureInline(admin.TabularInline):
    model = TourDeparture
    form = TourDepartureAdminForm
    formset = TourDepartureFormSet
    extra = 0
    show_change_link = True
    fields = ('start_date', 'end_date', 'max_participants', 'max_concurrent_bookings', 'deaf_only', 'is_published')
    verbose_name_plural = 'Scheduled departures — programme generated from the numbered tour itinerary'


class DepartureDayForm(forms.ModelForm):
    class Meta:
        model = DepartureDay
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        departure_tour_id = kwargs.pop('departure_tour_id', None)
        super().__init__(*args, **kwargs)
        if 'activities' not in self.fields:
            return
        if departure_tour_id or self.instance.departure_id:
            tour_id = departure_tour_id or self.instance.departure.tour_id
            self.fields['activities'].queryset = TourActivity.objects.filter(tour_id=tour_id)
        else:
            self.fields['activities'].queryset = TourActivity.objects.none()

    def clean(self):
        data = super().clean()
        if self.instance.departure_id and data.get('activities'):
            if data['activities'].exclude(tour=self.instance.departure.tour).exists():
                raise forms.ValidationError('Choose activities from this tour only.')
        return data


class DepartureDayFormSet(BaseInlineFormSet):
    auto_programme = False

    def total_form_count(self):
        count = super().total_form_count()
        if (self.auto_programme and self.is_bound and self.instance.pk
                and self.instance.start_date and self.instance.end_date):
            # Parent dates are validated first. Ignore trailing rows removed by a
            # shorter departure; TourDeparture.sync_programme prunes them on save.
            count = min(count, self.get_queryset().filter(day_number__lte=self.instance.duration_days).count())
        return count

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['departure_tour_id'] = self.instance.tour_id
        return kwargs

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        included = 0
        for form in self.forms:
            data = form.cleaned_data
            if not data or data.get('DELETE'):
                continue
            if data.get('day_number', 0) > self.instance.duration_days:
                raise forms.ValidationError('Programme days must fall within the departure dates.')
            included += bool(data.get('is_visible'))
        if self.instance.is_published and not included:
            raise forms.ValidationError('A published departure must include at least one day.')
        if self.instance.pk and self.instance.reservations.filter(status__in=['pending', 'booked']).exists():
            if any(form.has_changed() for form in self.forms):
                raise forms.ValidationError('This departure is already reserved. Create a new departure to change its programme.')


class DepartureDayInline(admin.TabularInline):
    model = DepartureDay
    form = DepartureDayForm
    formset = DepartureDayFormSet
    extra = 0
    can_delete = False
    readonly_fields = ('day_number', 'calendar_date', 'planned_activities')
    fields = ('day_number', 'calendar_date', 'planned_activities', 'is_visible')

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.auto_programme = True
        return formset

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description='Date')
    def calendar_date(self, obj):
        return obj.departure.start_date + timedelta(days=obj.day_number - 1)

    @admin.display(description='Activities from Tour itinerary')
    def planned_activities(self, obj):
        activities = obj.activities.all()
        if not activities:
            return 'No activities yet. Add them to this day in the tour itinerary.'
        return format_html('<ul class="programme-summary">{}</ul>', format_html_join('', '<li>{} {}</li>',
            ((activity.start_time.strftime('%H:%M') if activity.start_time else '', activity.title) for activity in activities)))


class GuideScheduleAdmin(CountryScopedAdmin):
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if request.method == 'POST':
            from apps.reservations.availability import lock_guide_calendar
            tour = Tour.objects.filter(pk=request.POST.get('tour')).first() if str(request.POST.get('tour', '')).isdigit() else None
            if tour is None and object_id:
                obj = self.get_queryset(request).filter(pk=object_id).first()
                tour = obj if isinstance(obj, Tour) else getattr(obj, 'tour', None)
            country = tour.country if tour else request.POST.get('country', 'morocco')
            from .models import Country
            country = country if Country.objects.filter(slug=country).exists() else 'morocco'
            with lock_guide_calendar(country):
                return super().changeform_view(request, object_id, form_url, extra_context)
        return super().changeform_view(request, object_id, form_url, extra_context)


@admin.register(TourDeparture)
class TourDepartureAdmin(GuideScheduleAdmin):
    country_lookup = 'tour__country'
    form = TourDepartureAdminForm
    change_form_template = 'admin/departure_change_form.html'
    fields = ('tour', 'start_date', 'end_date', 'max_participants', 'max_concurrent_bookings', 'deaf_only', 'is_published')
    list_display = ('tour', 'start_date', 'end_date', 'max_participants', 'max_concurrent_bookings', 'deaf_only', 'active_days', 'is_published')
    list_filter = ('is_published', ('tour', admin.RelatedOnlyFieldListFilter))
    inlines = [DepartureDayInline]

    def get_inlines(self, request, obj=None):
        return self.inlines if obj else []

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        data = {}
        for tour in Tour.objects.all().prefetch_related('activity_cards'):
            programme = {}
            for activity in tour.activity_cards.all():
                if activity.is_active:
                    programme.setdefault(str(activity.day_number), []).append(activity.title)
            data[str(tour.pk)] = {'days': tour.max_days, 'programme': programme}
        return super().changeform_view(request, object_id, form_url,
            {**(extra_context or {}), 'departure_tour_metadata': data})

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        context['departure_current_tour'] = obj.tour_id if obj else ''
        return super().render_change_form(request, context, add, change, form_url, obj)

    def get_readonly_fields(self, request, obj=None):
        return ('tour',) if obj else ()


class TourTeamAdminForm(forms.ModelForm):
    class Meta:
        model = Tour
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        country = self.data.get('country') if self.is_bound else (self.instance.country if self.instance.pk else None)
        if country and 'guides' in self.fields:
            self.fields['guides'].queryset = Guide.objects.filter(country_id=country)

    def clean(self):
        data = super().clean()
        guides = data.get('guides')
        country = data.get('country') or self.instance.country
        if guides is not None and guides.exclude(country_id=country).exists():
            self.add_error('guides', 'Choose guides belonging to the same country as this tour.')
        return data


@admin.register(Tour)
class TourAdmin(GuideScheduleAdmin):
    form = TourTeamAdminForm
    list_display = ('title', 'destination', 'price_per_night', 'is_promotion', 'discount_percent')
    list_filter = (('destination', admin.RelatedOnlyFieldListFilter), 'is_promotion')
    search_fields = ('title', 'description', 'activities', 'included', 'not_included')
    inlines = [TourActivityInline, TourItineraryLegInline, TourExtraActivityInline, TourDepartureInline]
    fieldsets = (
        ('Tour essentials', {'fields': ('country', 'title', 'destination', 'image', 'description', 'price_per_night', 'max_days', 'deaf_only', 'explanation_video_url')}),
        ('Guiding team', {'fields': ('guides',), 'description': 'Choose one or more guides, or leave empty to show the active team for this country.'}),
        ('What is included', {'fields': ('included', 'not_included', 'activities'), 'classes': ('collapse',)}),
        ('Promotion and address', {'fields': ('is_promotion', 'discount_percent', 'slug'), 'classes': ('collapse',)}),
    )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        for departure in form.instance.departures.all():
            departure.sync_programme()

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj is None or uses_scheduled_departures(obj.country):
            form.base_fields['price_per_night'].label = 'Price per person / day'
            form.base_fields['max_days'].label = 'Maximum days per departure'
        return form


class ReservationTeamAdminForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tour_id = self.data.get('tour') if self.is_bound else self.instance.tour_id
        tour = Tour.objects.filter(pk=tour_id).first() if str(tour_id).isdigit() else None
        if tour and 'assigned_guides' in self.fields:
            self.fields['assigned_guides'].queryset = Guide.objects.filter(country_id=tour.country)

    def clean(self):
        data = super().clean()
        guides, tour = data.get('assigned_guides'), data.get('tour')
        if guides is not None and tour:
            if guides.exclude(country_id=tour.country).exists():
                self.add_error('assigned_guides', 'Choose guides from this country.')
            if data.get('start_date') and data.get('end_date') and data.get('status') in ('pending', 'booked'):
                if Reservation.objects.filter(assigned_guides__in=guides, status__in=['pending', 'booked'],
                        start_date__lte=data['end_date'], end_date__gte=data['start_date']).exclude(pk=self.instance.pk).exists():
                    self.add_error('assigned_guides', 'A selected guide is already guiding another group on these dates.')
        return data


@admin.register(Reservation)
class ReservationAdmin(CountryScopedAdmin):
    form = ReservationTeamAdminForm
    country_lookup = 'tour__country'
    readonly_fields = ('account_deaf_status',)
    exclude = ('full_package', 'include_transport', 'include_hotel', 'transport_price_per_night', 'hotel_price_per_night')

    @admin.display(description='Deaf (account holder)')
    def account_deaf_status(self, obj):
        if not obj or not obj.user_id:
            return 'Not provided'
        profile = getattr(obj.user, 'profile', None)
        return ('Yes' if profile.is_deaf else 'No') if profile else 'Not provided'

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        # Keep ModelForm validation and persistence under the same calendar lock.
        # This also gives the Django admin a normal form error on a conflict.
        if request.method == 'POST':
            tour_id = request.POST.get('tour')
            tour = Tour.objects.filter(pk=tour_id).first() if tour_id and tour_id.isdigit() else None
            if tour:
                from apps.reservations.availability import lock_guide_calendar
                with lock_guide_calendar(tour.country):
                    return super().changeform_view(request, object_id, form_url, extra_context)
        return super().changeform_view(request, object_id, form_url, extra_context)

    list_display = (
        'tour', 'user', 'account_deaf_status', 'num_persons',
        'start_date', 'end_date',
        'extras_total',
        'total_price', 'status',
        'payment_method', 'payment_status',
        'created_at'
    )
    list_filter = ('status', 'payment_method', 'payment_status', 'created_at')
    search_fields = ('user__username', 'user__email', 'tour__title', 'guest_full_name', 'guest_phone')


class SectionAdmin(CountryScopedAdmin):
    list_display = ('title', 'slug', 'order', 'show_in_nav')
    prepopulated_fields = {'slug': ('title',)}


class BlogImageInline(admin.TabularInline):
    model = BlogImage
    extra = 4


@admin.register(BlogPost)
class BlogPostAdmin(CountryScopedAdmin):
    list_display = ('title', 'city', 'story_kind', 'trip_date', 'is_demo')
    list_filter = ('story_kind', 'is_demo', 'country')
    fields = ('country', 'title', 'slug', 'story_kind', 'city', 'trip_date', 'is_demo', 'content', 'image', 'starter_image', 'video_url')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [BlogImageInline]


@admin.register(Promotion)
class PromotionAdmin(CountryScopedAdmin):
    list_display = ('name', 'percent', 'active', 'apply_to_all')


@admin.register(ContactMessage)
class ContactMessageAdmin(CountryScopedAdmin):
    list_display = ('name', 'email', 'subject', 'message_site', 'created_at')
    readonly_fields = ('created_at',)

    def get_queryset(self, request):
        # Historical messages did not record their website; do not assign them by guesswork.
        return admin.ModelAdmin.get_queryset(self, request)

    @admin.display(description='Website')
    def message_site(self, obj):
        return obj.country.title() if obj.country else 'Unassigned legacy message'


@admin.register(ContactEmailSettings)
class ContactEmailSettingsAdmin(CountryScopedAdmin):
    list_display = ('country', 'recipient_email')
    fields = ('country', 'recipient_email', 'outgoing_email_status')
    readonly_fields = ('outgoing_email_status',)

    @admin.display(description='Outgoing email')
    def outgoing_email_status(self, obj):
        from django.conf import settings
        if settings.EMAIL_BACKEND in (
            'django.core.mail.backends.console.EmailBackend',
            'django.core.mail.backends.locmem.EmailBackend',
            'django.core.mail.backends.dummy.EmailBackend',
            'django.core.mail.backends.filebased.EmailBackend',
        ):
            return 'Email delivery is disabled: configure an outgoing email provider on the server. Contact messages are still saved in admin.'
        return 'Delivery uses the server email provider. Set a verified sender email in Global website settings, or DEFAULT_FROM_EMAIL on the server. Changing the inbox does not change the sender.'

    def has_add_permission(self, request):
        return super().has_add_permission(request)


class CountryContentAdmin(CountryScopedAdmin):
    list_display = ('country', 'hero_title')

    def has_add_permission(self, request):
        return super().has_add_permission(request)


@admin.register(BookingNotificationSettings)
class BookingNotificationSettingsAdmin(CountryScopedAdmin):
    list_display = ('country',)
    fields = ('country', 'email_recipients', 'whatsapp_recipients', 'whatsapp_content_sid', 'server_configuration')
    readonly_fields = ('server_configuration',)

    @admin.display(description='Server configuration')
    def server_configuration(self, obj):
        from django.conf import settings
        whatsapp_ready = all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_WHATSAPP_FROM])
        return f'Email backend: {settings.EMAIL_BACKEND}. WhatsApp server credentials: {"configured" if whatsapp_ready else "missing"}. Provider acceptance does not confirm delivery; check Booking notifications for each attempt.'
    def has_add_permission(self, request):
        return super().has_add_permission(request)


@admin.register(BookingNotification)
class BookingNotificationAdmin(CountryScopedAdmin):
    country_lookup = 'reservation__tour__country'
    list_display = ('reservation', 'event', 'audience', 'channel', 'recipient', 'status', 'created_at')
    list_filter = ('event', 'audience', 'channel', 'status')
    readonly_fields = ('reservation', 'event', 'audience', 'context', 'channel', 'recipient', 'status', 'error', 'provider_reference', 'created_at')
    actions = ('retry_notifications',)
    def has_add_permission(self, request):
        return False
    @admin.action(description='Retry pending or failed notifications')
    def retry_notifications(self, request, queryset):
        from apps.reservations.notifications import deliver_notification
        for notice in queryset.filter(status__in=['pending', 'failed']):
            deliver_notification(notice.pk)
        self.message_user(request, 'Notification attempts finished. Review each status and error.')


from .models import Country, SiteSettings, HomeHero


class HomeHeroInline(admin.StackedInline):
    model = HomeHero
    extra = 0


@admin.register(HomeHero)
class HomeHeroAdmin(admin.ModelAdmin):
    list_display = ('title', 'country', 'is_active', 'order')
    list_editable = ('is_active', 'order')
    list_filter = ('is_active', 'country')

class CountryGuideInline(admin.StackedInline):
    model = Guide
    extra = 0
    fields = ('name', 'photo', 'description', 'is_active', 'order')
    show_change_link = True


@admin.register(Guide)
class GuideAdmin(admin.ModelAdmin):
    list_display = ('name', 'country', 'is_active', 'order')
    list_filter = ('country', 'is_active')
    search_fields = ('name', 'description', 'country__name')
    ordering = ('country__name', 'order', 'name')


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    inlines = (CountryGuideInline,)
    list_display = ('name', 'slug', 'is_active', 'max_concurrent_groups', 'order')
    list_editable = ('is_active', 'order')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)
    def get_readonly_fields(self, request, obj=None):
        return ('slug',) if obj else ()

    def get_prepopulated_fields(self, request, obj=None):
        return {} if obj else {'slug': ('name',)}

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if request.method == 'POST' and object_id:
            country = self.get_queryset(request).filter(pk=object_id).first()
            if country:
                from apps.reservations.availability import lock_guide_calendar
                with lock_guide_calendar(country.slug):
                    return super().changeform_view(request, object_id, form_url, extra_context)
        return super().changeform_view(request, object_id, form_url, extra_context)

@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    inlines = (HomeHeroInline,)
    exclude = ('assistant_enabled', 'whatsapp_number')
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists() and super().has_add_permission(request)
    def has_delete_permission(self, request, obj=None):
        return False


from .models import WaitlistEntry

@admin.register(WaitlistEntry)
class WaitlistAdmin(CountryScopedAdmin):
    country_lookup = 'departure__tour__country'
    list_display = ('user', 'departure', 'num_persons', 'email', 'status', 'email_sent_at', 'created_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'email', 'departure__tour__title')
    readonly_fields = ('user', 'departure', 'num_persons', 'email', 'message', 'status', 'reservation',
        'decided_by', 'decided_at', 'email_sent_at', 'email_error', 'created_at')
    actions = ('accept_requests', 'decline_requests', 'retry_emails')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def decide(self, request, queryset, accept):
        from .models import WaitlistEntry
        from apps.reservations.waitlist import decide_waitlist
        for entry in queryset.filter(status='waiting'):
            try:
                decide_waitlist(entry.pk, accept=accept, staff=request.user, note=entry.decision_note)
            except ValidationError as exc:
                self.message_user(request, f'Request #{entry.pk}: {" ".join(exc.messages)}', level='error')

    @admin.action(description='Accept requests and email travelers')
    def accept_requests(self, request, queryset):
        self.decide(request, queryset, True)

    @admin.action(description='Decline requests and email travelers')
    def decline_requests(self, request, queryset):
        self.decide(request, queryset, False)

    @admin.action(description='Retry unsent decision emails')
    def retry_emails(self, request, queryset):
        from apps.reservations.waitlist import send_decision_email
        for entry in queryset.exclude(status='waiting').filter(email_sent_at__isnull=True):
            send_decision_email(entry.pk)
