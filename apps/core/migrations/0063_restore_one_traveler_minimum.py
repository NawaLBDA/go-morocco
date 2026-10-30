from django.db import migrations


def restore_default(apps, schema_editor):
    apps.get_model('core', 'Tour').objects.using(schema_editor.connection.alias).filter(
        min_travelers=5).update(min_travelers=1)


class Migration(migrations.Migration):
    dependencies = [('core', '0062_optional_deposit_before_approval')]
    operations = [migrations.RunPython(restore_default, migrations.RunPython.noop)]
