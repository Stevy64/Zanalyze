# Generated manually — branche PA (makemigrations local) avant 0014_premium_gamification.
# Même nom que sur PythonAnywhere pour permettre le merge du graphe.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paris', '0013_option_niveau_labels'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reglagesite',
            name='vip_tarif_libelle',
            field=models.CharField(
                blank=True,
                default='Premium Zanalyze',
                help_text='Court libellé affiché sur le CTA (ex. « Premium — 4,99 € / mois »).',
                max_length=120,
            ),
        ),
        migrations.AlterField(
            model_name='reglagesite',
            name='whatsapp_message',
            field=models.CharField(
                blank=True,
                default='Bonjour, je souhaite devenir Premium sur Zanalyze.',
                help_text='Message prérempli quand l’utilisateur ouvre WhatsApp.',
                max_length=300,
            ),
        ),
    ]
