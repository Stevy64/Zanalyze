"""Répare / recrée des comptes (admin ou membre) si la connexion est bloquée.

Exemples (PythonAnywhere) :
  python manage.py ensure_admin --username admin --password admin --force
  python manage.py ensure_admin --username stevy --password 'stevyc2b64!' --force --member
  python manage.py ensure_admin --username stevy --password 'stevyc2b64!' --force --promote
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = 'Crée ou réinitialise un compte (admin staff ou membre) + profil.'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True)
        parser.add_argument('--password', required=True)
        parser.add_argument('--email', default='', help='Email optionnel.')
        parser.add_argument(
            '--promote', action='store_true',
            help='Force staff + superuser (admin Django).',
        )
        parser.add_argument(
            '--member', action='store_true',
            help='Compte app sans droits admin (défaut si ni --promote ni staff existant).',
        )
        parser.add_argument(
            '--premium', action='store_true',
            help='Active le badge Premium (1 mois) sur le profil.',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Ignore les validateurs de mot de passe (récupération urgence).',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        username = (options['username'] or '').strip()
        password = options['password'] or ''
        email = (options.get('email') or '').strip()
        if not username:
            raise CommandError('Username vide.')
        if not password:
            raise CommandError('Mot de passe vide.')

        if not options['force']:
            try:
                validate_password(password)
            except ValidationError as e:
                raise CommandError(
                    ' '.join(e.messages)
                    + ' (ajoute --force pour forcer en récupération).'
                ) from e
        else:
            self.stdout.write(self.style.WARNING(
                'Attention : validateurs MDP ignorés (--force).'
            ))

        user = User.objects.filter(username__iexact=username).first()
        want_admin = bool(options['promote'])
        want_member = bool(options['member'])
        if want_admin and want_member:
            raise CommandError('Choisis --promote (admin) OU --member, pas les deux.')

        created = False
        if user is None:
            if want_admin or not want_member:
                # Par défaut : superuser si on ne précise pas --member.
                if want_member:
                    user = User.objects.create_user(
                        username=username,
                        email=email or '',
                        password=password,
                    )
                else:
                    # create_superuser valide le MDP → set_password après si --force
                    user = User(username=username, email=email or f'{username}@example.com')
                    user.is_staff = True
                    user.is_superuser = True
                    user.is_active = True
                    user.set_password(password)
                    user.save()
                created = True
                role = 'admin' if (user.is_staff or user.is_superuser) else 'membre'
                self.stdout.write(self.style.SUCCESS(f'Compte {role} créé : {user.username}'))
            else:
                user = User.objects.create_user(
                    username=username,
                    email=email or '',
                    password=password,
                )
                created = True
                self.stdout.write(self.style.SUCCESS(f'Compte membre créé : {user.username}'))
        else:
            # Compte existant : reset MDP + droits
            if want_admin or (
                not want_member and (user.is_staff or user.is_superuser or options['promote'])
            ):
                user.is_staff = True
                user.is_superuser = True
            elif want_member:
                # Ne retire pas le staff sauf demande explicite member-only
                pass
            elif not (user.is_staff or user.is_superuser) and not want_member:
                # Existant non-staff, pas de --member : on reset juste le MDP
                pass

            if options['promote']:
                user.is_staff = True
                user.is_superuser = True

            user.is_active = True
            if email:
                user.email = email
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(
                f'Compte mis à jour (MDP reset) : {user.username} '
                f'[staff={user.is_staff} super={user.is_superuser}]'
            ))

        from paris.models import Profil

        profil, _ = Profil.objects.get_or_create(user=user)
        if user.is_staff or user.is_superuser or options['premium']:
            profil.categorie = 'premium'
            profil.vip_depuis = profil.vip_depuis or timezone.now()
            if user.is_staff or user.is_superuser:
                profil.vip_expire_le = None
            elif options['premium'] and (
                profil.vip_expire_le is None
                or profil.vip_expire_le <= timezone.now()
            ):
                from paris.vip import debut_abonnement
                debut, fin = debut_abonnement(1)
                profil.vip_depuis = debut
                profil.vip_expire_le = fin
            profil.save(update_fields=['categorie', 'vip_depuis', 'vip_expire_le'])
        else:
            if profil.categorie not in ('membre', 'premium'):
                profil.categorie = 'membre'
                profil.save(update_fields=['categorie'])

        # Vérifie immédiatement que le MDP marche
        from django.contrib.auth import authenticate
        ok = authenticate(username=user.username, password=password)
        if ok is None:
            raise CommandError(
                'Échec : le mot de passe n’a pas pu être vérifié après écriture.'
            )

        action = 'créé' if created else 'réparé'
        self.stdout.write(self.style.SUCCESS(
            f'OK — compte {action}. Connexion testée avec succès pour « {user.username} ».'
        ))
