from django.db import migrations, models


def seed_calendar(apps, schema_editor):
    apps.get_model('core', 'GuideCalendar').objects.using(
        schema_editor.connection.alias,
    ).get_or_create(country='morocco')


class Migration(migrations.Migration):
    dependencies = [('core', '0030_tourextraactivity_insert_into_itinerary_and_more')]
    operations = [
        migrations.CreateModel(
            name='GuideCalendar',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('country', models.CharField(max_length=50, unique=True)),
            ],
        ),
        migrations.RunPython(seed_calendar, migrations.RunPython.noop),
    ]
