import os
from django.db import migrations


def classify_articles_and_add_render_examples(apps, schema_editor):
    alias=schema_editor.connection.alias
    Post=apps.get_model('core','BlogPost')
    Post.objects.using(alias).filter(slug__in=[
        'starter-morocco-city-connections','starter-nigeria-city-connections','rabat-between-river-and-ocean'
    ]).update(story_kind='inspiration')
    if os.environ.get('RENDER','').lower()=='true':
        from apps.core.memory_examples import seed_memory_examples
        seed_memory_examples(apps,alias)


class Migration(migrations.Migration):
    dependencies=[('core','0051_travel_memory_fields')]
    operations=[migrations.RunPython(classify_articles_and_add_render_examples,migrations.RunPython.noop)]
