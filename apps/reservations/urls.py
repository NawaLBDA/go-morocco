
from django.urls import path
from .views import book_tour

urlpatterns = [
    path('<int:tour_id>/', book_tour, name='book_tour'),
]
