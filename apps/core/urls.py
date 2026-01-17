from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.home, name='home'),
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
]
