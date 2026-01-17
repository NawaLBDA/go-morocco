from django.contrib import admin
from .models import (
    Destination, DestinationImage,
    Tour, Reservation,
    Section,
    BlogPost, BlogImage,
    Promotion,
    ContactMessage
)


class DestinationImageInline(admin.TabularInline):
    model = DestinationImage
    extra = 3


@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = ('name',)
    inlines = [DestinationImageInline]


@admin.register(Tour)
class TourAdmin(admin.ModelAdmin):
    list_display = ('title', 'destination', 'price_per_night', 'is_promotion', 'discount_percent')
    list_filter = ('destination', 'is_promotion')
    search_fields = ('title',)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        'tour', 'user', 'num_persons',
        'start_date', 'end_date',
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
