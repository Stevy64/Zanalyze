# Historique abonnements Premium + compteur d’acceptations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def initialiser_acceptations_existantes(apps, schema_editor):
    from django.utils import timezone

    Profil = apps.get_model('paris', 'Profil')
    HistoriqueAbonnement = apps.get_model('paris', 'HistoriqueAbonnement')
    for p in Profil.objects.all().iterator():
        if int(getattr(p, 'premium_acceptations', 0) or 0) > 0:
            continue
        if not p.vip_depuis and p.categorie not in ('premium', 'vip'):
            continue
        p.premium_acceptations = 1
        p.save(update_fields=['premium_acceptations'])
        HistoriqueAbonnement.objects.create(
            profil_id=p.pk,
            type='premier',
            ordre=1,
            mois=1,
            debut=p.vip_depuis or p.vip_expire_le or timezone.now(),
            expire_le=p.vip_expire_le,
            note='Initialisation depuis l’historique existant',
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('paris', '0020_merge_0019_trace_whatsapp'),
    ]

    operations = [
        migrations.AddField(
            model_name='profil',
            name='premium_acceptations',
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    'Nombre d’acceptations Premium (1 = premier abo, 2+ = renouvellements). '
                    'Incrémenté à chaque octroi ou prolongation admin.'
                ),
            ),
        ),
        migrations.CreateModel(
            name='HistoriqueAbonnement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(
                    choices=[
                        ('premier', 'Premier abonnement'),
                        ('renouvellement', 'Renouvellement'),
                        ('prolongation', 'Prolongation'),
                        ('retrait', 'Retrait'),
                    ],
                    db_index=True,
                    max_length=20,
                )),
                ('ordre', models.PositiveIntegerField(
                    default=0,
                    help_text='N° de cycle (1 = premier, 2 = 1er renouvellement, …).',
                )),
                ('mois', models.PositiveSmallIntegerField(default=1)),
                ('debut', models.DateTimeField()),
                ('expire_le', models.DateTimeField(blank=True, null=True)),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('admin_user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='acceptations_premium',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('profil', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='historique_abonnements',
                    to='paris.profil',
                )),
            ],
            options={
                'verbose_name': 'Historique abonnement',
                'verbose_name_plural': 'Historique abonnements',
                'ordering': ['-created_at'],
            },
        ),
        migrations.RunPython(initialiser_acceptations_existantes, migrations.RunPython.noop),
    ]
