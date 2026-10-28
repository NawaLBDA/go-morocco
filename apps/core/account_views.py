from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordResetView
from django.core.paginator import Paginator
from django.shortcuts import render
from django.views.decorators.http import require_safe
from django.views.decorators.cache import never_cache
from .models import Reservation, SiteSettings
from .email_identity import email_identity
from .context_processors import get_country_from_site


@login_required
@never_cache
@require_safe
def profile(request):
    return render(request, 'account/profile.html', {'traveler_profile': getattr(request.user, 'profile', None)})


@login_required
@never_cache
@require_safe
def my_reservations(request):
    bookings = Reservation.objects.filter(user=request.user).select_related('tour', 'tour__region').order_by('-created_at', '-pk')
    return render(request, 'account/reservations.html', {'bookings': Paginator(bookings, 12).get_page(request.GET.get('page'))})


class TravelerPasswordResetView(PasswordResetView):
    template_name = 'account/password_reset.html'
    email_template_name = 'emails/password_reset.txt'
    html_email_template_name = 'emails/password_reset.html'
    subject_template_name = 'emails/password_reset_subject.txt'

    def form_valid(self, form):
        brand, self.from_email, inbox = email_identity(get_country_from_site(self.request))
        self.extra_email_context = {'brand': brand, 'inbox': inbox}
        return super().form_valid(form)
