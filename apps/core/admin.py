from django.contrib import admin
from .models import Destination, Tour, Section, BlogPost, Promotion
from .models import ContactMessage


@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(Tour)
class TourAdmin(admin.ModelAdmin):
    list_display = ('title', 'destination', 'price_per_night', 'is_promotion', 'discount_percent')
    list_filter = ('destination', 'is_promotion')
    search_fields = ('title',)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'order', 'show_in_nav')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_at')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('name', 'percent', 'active', 'apply_to_all')


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'created_at')
    readonly_fields = ('created_at',)
