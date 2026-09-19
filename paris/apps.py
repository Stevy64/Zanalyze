from django.apps import AppConfig


class ParisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'paris'
    verbose_name = 'Zanalyze'

    def ready(self):
        from django.contrib.auth import get_user_model
        from django.db import OperationalError, ProgrammingError
        from django.db.models.signals import post_save
        from django.utils import timezone

        from paris.models import Profil

        User = get_user_model()

        def assurer_profil(sender, instance, created, **kwargs):
            try:
                profil, _ = Profil.objects.get_or_create(user=instance)
            except (OperationalError, ProgrammingError):
                # Migrations pas encore appliquées (ex. nouvelle colonne Profil).
                return
            if not (instance.is_superuser or instance.is_staff):
                return
            # Admin / staff = Premium permanent (sans date d'expiration).
            dirty = False
            if profil.categorie != 'premium':
                profil.categorie = 'premium'
                dirty = True
            if not profil.vip_depuis:
                profil.vip_depuis = timezone.now()
                dirty = True
            if profil.vip_expire_le is not None:
                profil.vip_expire_le = None
                dirty = True
            if dirty:
                profil.save(update_fields=['categorie', 'vip_depuis', 'vip_expire_le'])

        post_save.connect(assurer_profil, sender=User, dispatch_uid='paris_profil_user')
