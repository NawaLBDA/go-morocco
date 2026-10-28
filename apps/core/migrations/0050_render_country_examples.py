import os
from django.db import migrations


def populate_requested_render_catalogue(apps, schema_editor):
    # This one-time content launch was requested specifically for the Render site.
    # Other environments can explicitly run seed_country_examples.
    if os.environ.get('RENDER', '').lower() == 'true':
        from apps.core.catalogue_examples import seed_examples
        seed_examples(apps, schema_editor.connection.alias, activate_countries=True)


class Migration(migrations.Migration):
    dependencies = [('core', '0049_email_only_contact')]
    operations = [migrations.RunPython(populate_requested_render_catalogue, migrations.RunPython.noop)]
