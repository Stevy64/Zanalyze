# Accueil Salon Premium + flag accueil_salon

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paris', '0017_analytics'),
    ]

    operations = [
        migrations.AddField(
            model_name='profil',
            name='accueil_salon',
            field=models.BooleanField(
                default=False,
                help_text='Si vrai, le prochain chargement app ouvre le Salon avec un message de bienvenue.',
            ),
        ),
        migrations.AddField(
            model_name='messagechat',
            name='systeme',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='Annonce système (bienvenue Premium, etc.).',
            ),
        ),
    ]
