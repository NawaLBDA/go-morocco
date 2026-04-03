from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.home, name='home'),
    path('reservations/', views.reservations, name='reservations'),
    path('tour/<int:tour_id>/', views.tour_detail, name='tour_detail'),

    path('blog/', views.blog_list, name='blog_list'),
    path('blog/<slug:slug>/', views.blog_detail, name='blog_detail'),

    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),

    path('register/', views.register, name='register'),

    path('login/', auth_views.LoginView.as_view(
        template_name='login.html',
        redirect_authenticated_user=True
    ), name='login'),

    path('logout/', views.custom_logout, name='logout'),

    # Twilio Robocall API
    path('api/robo-call/<int:reservation_id>/', views.start_robo_call, name='start_robo_call'),
    path('twiml/call-first/<int:reservation_id>/', views.twiml_call_first, name='twiml_call_first'),
    path('twiml/call-fallback/<int:reservation_id>/', views.twiml_call_fallback, name='twiml_call_fallback'),
    path('twiml/call-complete/<int:reservation_id>/', views.twiml_call_complete, name='twiml_call_complete'),
    path('api/ai-chat/', views.ai_chat, name='ai_chat'),
    path('api/ai-chat-stream/', views.ai_chat_stream, name='ai_chat_stream'),
    path('api/ai-chat-history/', views.ai_chat_history, name='ai_chat_history'),
]
