from django.urls import path
from . import views

urlpatterns = [
    # ✅ tour detail (page booking)
    path("tour/<int:tour_id>/", views.tour_detail, name="tour_detail"),

    # ✅ create booking (POST)
    path("tour/<int:tour_id>/book/", views.book_tour, name="book_tour"),

    # ✅ Stripe intent (AFTER validation admin)  ✅ NEW
    path(
        "reservation/<int:reservation_id>/create-intent/",
        views.create_payment_intent_for_reservation,
        name="create_payment_intent_for_reservation"
    ),

    # cancel
    path("reservation/<int:id>/cancel/", views.cancel_reservation, name="cancel_reservation"),

    # admin dashboard
    path("dashboard/reservations/", views.admin_reservations, name="admin_reservations"),
    path("dashboard/reservation/<int:id>/validate/", views.validate_reservation, name="validate_reservation"),
    path("dashboard/reservation/<int:id>/reject/", views.reject_reservation, name="reject_reservation"),
    path("dashboard/reservation/<int:id>/paid/", views.mark_paid_reservation, name="mark_paid_reservation"),
path("dashboard/reservation/<int:id>/cancel/", views.admin_cancel_reservation, name="admin_cancel_reservation"),

    # webhook
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
]
