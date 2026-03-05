from .models import Section, Tour

def sections_processor(request):
    sections = Section.objects.filter(show_in_nav=True).order_by('order')
    # ✅ Check if there are any promotions to display the promo bar
    has_promotion = Tour.objects.filter(is_promotion=True, discount_percent__gt=0).exists()
    return {'sections': sections, 'has_promotion': has_promotion}
