# Generated manually — analytics visiteurs + traces activité

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('paris', '0016_points_decay'),
    ]

    operations = [
        migrations.CreateModel(
            name='VisiteJour',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('jour', models.DateField(db_index=True, unique=True)),
                ('visiteurs', models.PositiveIntegerField(default=0)),
                ('pages_vues', models.PositiveIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Visite du jour',
                'verbose_name_plural': 'Visites quotidiennes',
                'ordering': ['-jour'],
            },
        ),
        migrations.CreateModel(
            name='TraceActivite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('type', models.CharField(
                    choices=[
                        ('visite', 'Visite'),
                        ('inscription', 'Inscription'),
                        ('connexion', 'Connexion'),
                        ('pronostic', 'Pronostic'),
                        ('proposition', 'Proposition'),
                        ('vote', 'Vote'),
                        ('chat', 'Salon'),
                        ('vip', 'Premium'),
                        ('admin', 'Admin'),
                        ('autre', 'Autre'),
                    ],
                    db_index=True,
                    default='autre',
                    max_length=20,
                )),
                ('label', models.CharField(max_length=220)),
                ('detail', models.CharField(blank=True, default='', max_length=400)),
                ('path', models.CharField(blank=True, default='', max_length=200)),
                ('user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='traces_activite',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': "Trace d'activité",
                'verbose_name_plural': "Traces d'activité",
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='traceactivite',
            index=models.Index(fields=['-created_at', 'type'], name='trace_at_type'),
        ),
    ]
