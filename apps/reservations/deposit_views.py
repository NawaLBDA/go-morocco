from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from apps.core.models import Reservation
from .deposits import record_deposit_received


@login_required
@require_POST
def mark_deposit_received(request, id):
    if not request.user.is_active or not request.user.is_staff:
        return HttpResponseForbidden('Staff access is required.')
    get_object_or_404(Reservation, pk=id)
    try:
        record_deposit_received(id, request.user)
        messages.success(request, 'Deposit recorded as received. The booking can now be reviewed for approval.')
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    return redirect('admin_reservations')
