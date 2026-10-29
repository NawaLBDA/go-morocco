from django.db import migrations


def announce_destinations(apps, schema_editor):
    Country = apps.get_model('core', 'Country')
    database = schema_editor.connection.alias
    for order, (slug, name) in enumerate([
        ('nigeria', 'Nigeria'), ('morocco', 'Morocco'),
        ('ireland', 'Ireland'), ('jamaica', 'Jamaica'),
    ]):
        coming = slug in ('nigeria', 'jamaica')
        country, _ = Country.objects.using(database).get_or_create(slug=slug, defaults={'name': name})
        Country.objects.using(database).filter(pk=country.pk).update(
            is_active=True, coming_soon=coming, order=order,
            **({'introduction': f'{name} is in the works. Our team is preparing new cultural journeys. Dates and prices will be announced when ready.'} if coming else {}))
    apps.get_model('core', 'SiteSettings').objects.using(database).filter(pk=1).update(
        regions_text='Nigeria • Morocco • Ireland • Jamaica')


class Migration(migrations.Migration):
    dependencies = [('core', '0055_country_coming_soon')]
    operations = [migrations.RunPython(announce_destinations, migrations.RunPython.noop)]
