# Generated manually for Premium rename + gamification

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def vip_vers_premium(apps, schema_editor):
    Profil = apps.get_model('paris', 'Profil')
    Profil.objects.filter(categorie='vip').update(categorie='premium')
    ReglageSite = apps.get_model('paris', 'ReglageSite')
    for r in ReglageSite.objects.all():
        changed = False
        if (r.whatsapp_message or '').find('VIP') >= 0:
            r.whatsapp_message = (r.whatsapp_message or '').replace('VIP', 'Premium')
            changed = True
        if (r.vip_tarif_libelle or '').find('VIP') >= 0:
            r.vip_tarif_libelle = (r.vip_tarif_libelle or '').replace('VIP', 'Premium')
            changed = True
        if changed:
            r.save(update_fields=['whatsapp_message', 'vip_tarif_libelle'])


def premium_vers_vip(apps, schema_editor):
    Profil = apps.get_model('paris', 'Profil')
    Profil.objects.filter(categorie='premium').update(categorie='vip')


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('paris', '0013_option_niveau_labels'),
    ]

    operations = [
        migrations.AddField(
            model_name='profil',
            name='points_premium',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Points de la saison (pronostics Premium).',
            ),
        ),
        migrations.RunPython(vip_vers_premium, premium_vers_vip),
        migrations.AlterField(
            model_name='profil',
            name='categorie',
            field=models.CharField(
                choices=[('membre', 'Membre'), ('premium', 'Premium')],
                db_index=True,
                default='membre',
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name='profil',
            name='vip_depuis',
            field=models.DateTimeField(
                blank=True,
                help_text='Date de la dernière activation Premium.',
                null=True,
            ),
        ),
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
        migrations.AlterModelOptions(
            name='messagechat',
            options={
                'ordering': ['created_at'],
                'verbose_name': 'Message Salon Premium',
                'verbose_name_plural': 'Messages Salon Premium',
            },
        ),
        migrations.CreateModel(
            name='PronosticPremium',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('choix', models.CharField(choices=[('1', 'Domicile'), ('N', 'Nul'), ('2', 'Extérieur')], max_length=1)),
                ('points', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('gagne', models.BooleanField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('match', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pronostics', to='paris.match')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pronostics', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Pronostic Premium',
                'verbose_name_plural': 'Pronostics Premium',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='pronosticpremium',
            constraint=models.UniqueConstraint(fields=('match', 'user'), name='prono_unique_user_match'),
        ),
    ]
