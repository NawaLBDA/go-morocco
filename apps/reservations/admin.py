from django.contrib import admin
from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('user', 'tour', 'nights', 'persons', 'total_price', 'created_at')
    list_filter = ('created_at',)
