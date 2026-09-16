# Generated manually — décroissance points challenge

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paris', '0015_merge_premium_reglage'),
    ]

    operations = [
        migrations.AddField(
            model_name='profil',
            name='points_decay_le',
            field=models.DateTimeField(
                blank=True,
                help_text='Dernière application de la décroissance (−1 pt / 24 h).',
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name='profil',
            name='points_premium',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Points challenge (pronostics / propositions).',
            ),
        ),
    ]
