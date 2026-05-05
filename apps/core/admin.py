from decimal import Decimal, InvalidOperation

from django.contrib import admin
from django import forms
from .models import (
    Destination, DestinationImage,
    Tour, Reservation,
    Section,
    BlogPost, BlogImage,
    Promotion,
    ContactMessage,
    Information, ChatMessage,
    TourExtraActivity,
    TourActivity,
    TourItineraryLeg,
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
        help_text="Paste from Google Maps, for example: 34.0318501020754, -6.835778065718815",
        label="Coordinates",
        widget=forms.TextInput(attrs={"readonly": "readonly"}),
    )

    class Meta:
        model = TourActivity
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
        return cleaned_data


class TourExtraActivityAdminForm(forms.ModelForm):
    map_search = forms.CharField(
        required=False,
        help_text="Search a place or click directly on the map below.",
        label="Map search",
    )
    coordinates = forms.CharField(
        required=False,
        help_text="Paste from Google Maps, for example: 34.0318501020754, -6.835778065718815",
        label="Coordinates",
        widget=forms.TextInput(attrs={"readonly": "readonly"}),
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


class DestinationImageInline(admin.TabularInline):
    model = DestinationImage
    extra = 3


@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = ('name',)
    inlines = [DestinationImageInline]


@admin.register(Information)
class InformationAdmin(admin.ModelAdmin):
    list_display = ('title', 'country', 'created_at')
    search_fields = ('title', 'content')
    list_filter = ('country',)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'created_at')
    list_filter = ('role', 'user')
    search_fields = ('message',)


class TourExtraActivityInline(admin.StackedInline):
    model = TourExtraActivity
    form = TourExtraActivityAdminForm
    extra = 1
    verbose_name = "Extra itinerary option"
    verbose_name_plural = "Extra itinerary options"
    fields = (
        'title', 'description', 'image',
        'city', 'place_name', 'map_search', 'coordinates', 'latitude', 'longitude',
        'price', 'is_per_night', 'is_active',
    )


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
    model = TourItineraryLeg
    form = TourItineraryLegAdminForm
    formset = TourItineraryLegInlineFormSet
    extra = 1
    verbose_name = "Itinerary route segment"
    verbose_name_plural = "Itinerary route segments"
    fields = (
        'from_activity', 'to_activity', 'distance_label',
        'transport_mode', 'transport_label', 'display_order', 'is_active',
    )


@admin.register(Tour)
class TourAdmin(admin.ModelAdmin):
    list_display = ('title', 'destination', 'price_per_night', 'is_promotion', 'discount_percent')
    list_filter = ('destination', 'is_promotion')
    search_fields = ('title', 'description', 'transport', 'hotel', 'activities', 'included', 'not_included')
    inlines = [TourActivityInline, TourItineraryLegInline, TourExtraActivityInline]


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        'tour', 'user', 'num_persons',
        'start_date', 'end_date',
        'full_package', 'include_transport', 'include_hotel',
        'extras_total',
        'total_price', 'status',
        'payment_method', 'payment_status',
        'created_at'
    )
    list_filter = ('status', 'payment_method', 'payment_status', 'created_at')
    search_fields = ('user__username', 'user__email', 'tour__title', 'guest_full_name', 'guest_phone')


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'order', 'show_in_nav')
    prepopulated_fields = {'slug': ('title',)}


class BlogImageInline(admin.TabularInline):
    model = BlogImage
    extra = 4


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_at')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [BlogImageInline]


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('name', 'percent', 'active', 'apply_to_all')


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'created_at')
    readonly_fields = ('created_at',)
