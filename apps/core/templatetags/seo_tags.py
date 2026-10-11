from django import template

from apps.core.seo import metadata

register = template.Library()


@register.simple_tag(takes_context=True)
def morocco_metadata(context):
    return metadata(context['request'], tour=context.get('tour'), post=context.get('post'))
