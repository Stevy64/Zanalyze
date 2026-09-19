# Generated on PythonAnywhere — options TraceActivite (apostrophe typographique)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('paris', '0018_accueil_salon'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='traceactivite',
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'Trace d’activité',
                'verbose_name_plural': 'Traces d’activité',
            },
        ),
    ]
