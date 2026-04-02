from django import template

register = template.Library()

@register.filter
def split(value, arg):
    """Split a string by a separator."""
    return value.split(arg)


@register.filter
def trim(value):
    """Trim leading/trailing whitespace (alias for str.strip)."""
    if value is None:
        return ''
    return str(value).strip()