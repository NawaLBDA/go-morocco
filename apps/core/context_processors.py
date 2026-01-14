from .models import Section

def sections_processor(request):
    sections = Section.objects.filter(show_in_nav=True).order_by('order')
    return {'sections': sections}
