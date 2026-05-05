from django.urls import path
from . import views

urlpatterns = [
    # ✅ create booking (POST)
    path("tour/<int:tour_id>/book/", views.book_tour, name="book_tour"),
    path("api/chat-book-tour/", views.chat_book_tour, name="chat_book_tour"),

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
    path("dashboard/reservation/<int:id>/update/", views.admin_update_reservation, name="admin_update_reservation"),
    path("dashboard/reservation/<int:id>/validate/", views.validate_reservation, name="validate_reservation"),
    path("dashboard/reservation/<int:id>/reject/", views.reject_reservation, name="reject_reservation"),
    path("dashboard/reservation/<int:id>/paid/", views.mark_paid_reservation, name="mark_paid_reservation"),
    path("dashboard/reservation/<int:id>/cancel/", views.admin_cancel_reservation, name="admin_cancel_reservation"),
    path("dashboard/reservation/<int:id>/delete/", views.delete_reservation, name="delete_reservation"),
    path("dashboard/reservation/<int:id>/report/", views.download_reservation_report, name="download_reservation_report"),

    # webhook
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
]
