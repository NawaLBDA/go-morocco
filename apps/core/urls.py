
from django.urls import path
from .views import home, tour_detail, blog_list, blog_detail, about, contact, register
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', home, name='home'),
    path('tour/<int:tour_id>/', tour_detail, name='tour_detail'),
    path('blog/', blog_list, name='blog_list'),
    path('blog/<slug:slug>/', blog_detail, name='blog_detail'),
    path('about/', about, name='about'),
    path('contact/', contact, name='contact'),
    path('register/', register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
]
