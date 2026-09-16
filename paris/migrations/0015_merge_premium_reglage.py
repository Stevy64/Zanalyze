# Merge des deux feuilles 0014 (PA alter + premium gamification).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('paris', '0014_alter_reglagesite_vip_tarif_libelle_and_more'),
        ('paris', '0014_premium_gamification'),
    ]

    operations = []
