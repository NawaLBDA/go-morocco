import os
from django.db import migrations


def populate(apps, schema_editor):
    if os.environ.get('RENDER', '').lower() == 'true':
        from apps.core.ireland_example import seed_ireland_example
        seed_ireland_example(apps, schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = [('core', '0056_launch_destination_announcements')]
    operations = [migrations.RunPython(populate, migrations.RunPython.noop)]
