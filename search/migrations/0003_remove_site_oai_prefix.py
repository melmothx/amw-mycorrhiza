# Generated by Django 4.2.1 on 2023-06-18 07:21

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0002_site_oai_metadata_format_site_oai_set'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='site',
            name='oai_prefix',
        ),
    ]
