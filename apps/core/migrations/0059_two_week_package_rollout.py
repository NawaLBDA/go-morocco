import os
from django.db import migrations


def populate(apps, schema_editor):
    if os.environ.get('RENDER', '').lower() == 'true':
        from apps.core.package_rollout import apply_package_rollout
        apply_package_rollout(apps, schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = [('core', '0058_country_visibility_and_package_pricing')]
    operations = [migrations.RunPython(populate, migrations.RunPython.noop)]
