
from django.shortcuts import render, get_object_or_404, redirect
from .models import Tour, Section, BlogPost
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages


def home(request):
    query = request.GET.get('q')
    if query:
        tours = Tour.objects.filter(title__icontains=query)
    else:
        tours = Tour.objects.all()
    sections = Section.objects.filter(show_in_nav=True).order_by('order')
    return render(request, 'home.html', {'tours': tours, 'sections': sections})


def tour_detail(request, tour_id):
    tour = get_object_or_404(Tour, id=tour_id)
    return render(request, 'tour_detail.html', {'tour': tour})


def blog_list(request):
    posts = BlogPost.objects.order_by('-created_at')
    return render(request, 'blog_list.html', {'posts': posts})


def blog_detail(request, slug):
    post = get_object_or_404(BlogPost, slug=slug)
    return render(request, 'blog_detail.html', {'post': post})


def about(request):
    return render(request, 'about.html')


def contact(request):
    success = False
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        from .models import ContactMessage
        ContactMessage.objects.create(name=name, email=email, subject=subject, message=message)
        success = True
    return render(request, 'contact.html', {'success': success})


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created. You can log in now.')
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'register.html', {'form': form})
