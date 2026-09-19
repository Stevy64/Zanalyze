from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django.utils import timezone

from paris.dashboard import build_dashboard_stats
from paris.models import (
    Analyse, Competition, Contexte, Cote, Equipe, HistoriqueAbonnement, Match,
    MessageChat, Option, Profil, PronosticPremium, PropositionParis, ReglageSite,
    TraceActivite, VisiteJour, Vote, VoteOption,
)

# Dashboard activité sur l’index admin.
_admin_index_orig = admin.site.index


def _admin_index(request, extra_context=None):
    # Ne pas binder avec __get__ : Django appelle site.index(request, …)
    # sans injecter self (attribut d’instance).
    import logging
    ctx = dict(extra_context or {})
    ctx['title'] = 'Tableau de bord'
    try:
        ctx['zanalyz_stats'] = build_dashboard_stats()
        ctx['zanalyz_reglages'] = ReglageSite.get_solo()
    except Exception as exc:  # noqa: BLE001 — migrations en cours
        logging.getLogger(__name__).exception('Dashboard admin: %s', exc)
        ctx['zanalyz_stats'] = None
        ctx['zanalyz_reglages'] = None
        from django.conf import settings
        if settings.DEBUG:
            ctx['zanalyz_dashboard_error'] = f'{type(exc).__name__}: {exc}'
    return _admin_index_orig(request, ctx)


admin.site.index = _admin_index
admin.site.index_template = 'admin/paris/index.html'
admin.site.site_header = 'Zanalyze'
admin.site.site_title = 'Zanalyze Admin'
admin.site.index_title = 'Tableau de bord'
admin.site.enable_nav_sidebar = True

# Titres de listes plus courts (mobile-friendly)
_changelist_orig = admin.ModelAdmin.changelist_view


def _changelist_view_titre(self, request, extra_context=None):
    extra = dict(extra_context or {})
    extra.setdefault('title', str(self.opts.verbose_name_plural).capitalize())
    return _changelist_orig(self, request, extra)


admin.ModelAdmin.changelist_view = _changelist_view_titre


# Utilisateurs Django — liste plus lisible
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ('username', 'email', 'is_staff', 'is_active', 'date_joined', 'last_login')
    list_filter = ('is_staff', 'is_active', 'is_superuser')
    search_fields = ('username', 'email')
    ordering = ('-date_joined',)
    readonly_fields = ('last_login', 'date_joined')


def _admin_logout(request, extra_context=None):
    """Après déconnexion admin → page de connexion (pas la page « Logged out »)."""
    from django.contrib.auth.views import LogoutView
    from django.urls import reverse

    defaults = {
        'next_page': reverse('admin:login'),
        'extra_context': {
            **admin.site.each_context(request),
            'has_permission': False,
            **(extra_context or {}),
        },
    }
    request.current_app = admin.site.name
    return LogoutView.as_view(**defaults)(request)


admin.site.logout = _admin_logout


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ('code', 'nom', 'pays', 'ordre', 'actif')
    list_filter = ('actif',)
    search_fields = ('code', 'nom')
    ordering = ('ordre', 'nom')


@admin.register(Equipe)
class EquipeAdmin(admin.ModelAdmin):
    list_display = ('nom', 'nom_court', 'slug', 'sofascore_id', 'thesportsdb_id')
    search_fields = ('nom', 'nom_court', 'slug')
    prepopulated_fields = {'slug': ('nom',)}


class CoteInline(admin.TabularInline):
    model = Cote
    extra = 0


class ContexteInline(admin.StackedInline):
    model = Contexte
    extra = 0
    max_num = 1


class OptionInline(admin.TabularInline):
    model = Option
    extra = 0
    readonly_fields = ('resultat', 'regle_le')


class AnalyseInline(admin.StackedInline):
    model = Analyse
    extra = 0
    max_num = 1


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        'quand', 'competition', 'affiche', 'statut', 'score',
    )
    list_filter = ('statut', 'competition')
    search_fields = ('domicile__nom', 'exterieur__nom', 'journee')
    date_hierarchy = 'coup_denvoi'
    autocomplete_fields = ('competition', 'domicile', 'exterieur')
    inlines = (ContexteInline, CoteInline, AnalyseInline)
    fieldsets = (
        (None, {
            'fields': (
                'competition', 'domicile', 'exterieur',
                'coup_denvoi', 'journee', 'statut',
            ),
        }),
        ('Résultat', {
            'fields': (
                'buts_dom', 'buts_ext', 'buts_dom_mt', 'buts_ext_mt',
            ),
            'description': (
                'Saisie manuelle du score. Le règlement des options '
                'se fera à l’étape 3 (commande regler_options).'
            ),
        }),
    )

    @admin.display(description='Coup d’envoi', ordering='coup_denvoi')
    def quand(self, obj):
        return timezone.localtime(obj.coup_denvoi).strftime('%d/%m %H:%M')

    @admin.display(description='Match')
    def affiche(self, obj):
        return f'{obj.domicile} – {obj.exterieur}'


@admin.register(Analyse)
class AnalyseAdmin(admin.ModelAdmin):
    list_display = (
        'match', 'profil', 'score_probable', 'residu',
        'version_moteur', 'calcule_le',
    )
    list_filter = ('profil', 'version_moteur')
    search_fields = (
        'match__domicile__nom', 'match__exterieur__nom',
    )
    inlines = (OptionInline,)
    readonly_fields = ('calcule_le',)


@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = ('libelle', 'niveau', 'resultat')
    list_filter = ('niveau', 'resultat', 'famille', 'origine')
    search_fields = ('libelle', 'code')
    readonly_fields = ('regle_le',)
    list_per_page = 50


@admin.register(Cote)
class CoteAdmin(admin.ModelAdmin):
    list_display = (
        'match', 'bookmaker', 'marche', 'selection',
        'valeur', 'releve_le',
    )
    list_filter = ('marche', 'bookmaker')


@admin.register(Contexte)
class ContexteAdmin(admin.ModelAdmin):
    list_display = ('match', 'fiabilite', 'source')
    list_filter = ('fiabilite',)


@admin.register(PropositionParis)
class PropositionAdmin(admin.ModelAdmin):
    list_display = ('libelle', 'match', 'auteur', 'confiance', 'created_at')
    search_fields = ('libelle', 'auteur__username')


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ('proposition', 'user', 'choix', 'created_at')
    list_filter = ('choix',)


@admin.register(VoteOption)
class VoteOptionAdmin(admin.ModelAdmin):
    list_display = ('option', 'user', 'choix', 'created_at')
    list_filter = ('choix',)


@admin.register(HistoriqueAbonnement)
class HistoriqueAbonnementAdmin(admin.ModelAdmin):
    list_display = (
        'profil', 'type', 'libelle_cycle', 'mois', 'debut', 'expire_le',
        'admin_user', 'created_at',
    )
    list_filter = ('type',)
    search_fields = ('profil__user__username', 'note', 'admin_user__username')
    autocomplete_fields = ('profil', 'admin_user')
    readonly_fields = (
        'profil', 'type', 'ordre', 'mois', 'debut', 'expire_le',
        'admin_user', 'note', 'created_at',
    )

    @admin.display(description='Cycle', ordering='ordre')
    def libelle_cycle(self, obj):
        return obj.libelle_ordre

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Profil)
class ProfilAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'badge_categorie', 'cycle_premium', 'points_premium',
        'expire_court', 'note_admin',
    )
    list_filter = ('categorie',)
    search_fields = ('user__username', 'note_admin')
    autocomplete_fields = ('user',)
    list_editable = ()
    actions = ('octroyer_vip', 'prolonger_vip', 'retirer_vip')
    inlines = ()
    readonly_fields = ('resume_cycle', 'journal_abonnements')
    fieldsets = (
        (None, {
            'fields': (
                'user', 'categorie', 'points_premium',
                'vip_depuis', 'vip_expire_le', 'note_admin',
            ),
            'description': (
                'À l’octroi, l’abonnement Premium dure 1 mois. '
                'Prolonge via l’action « Prolonger Premium (+1 mois) » '
                'ou en modifiant la date d’expiration.'
            ),
        }),
        ('Abonnement Premium', {
            'fields': ('resume_cycle', 'journal_abonnements'),
            'description': (
                'Cycle courant et journal des acceptations '
                '(1er abo, renouvellements, prolongations, retraits).'
            ),
        }),
    )

    @admin.display(description='Statut', ordering='categorie')
    def badge_categorie(self, obj):
        from django.utils.html import format_html
        if obj.abonnement_vip_actif:
            return format_html(
                '<span class="zyz-pill-tag is-premium">Premium</span>',
            )
        if obj.categorie in ('vip', 'premium'):
            return format_html(
                '<span class="zyz-pill-tag is-expired">Expiré</span>',
            )
        return format_html(
            '<span class="zyz-pill-tag is-membre">Membre</span>',
        )

    @admin.display(description='Cycle', ordering='premium_acceptations')
    def cycle_premium(self, obj):
        return obj.libelle_cycle_premium

    @admin.display(description='Cycle actuel')
    def resume_cycle(self, obj):
        from django.utils.html import format_html
        n = int(obj.premium_acceptations or 0)
        return format_html(
            '<div class="zyz-abo-resume">'
            '<span class="zyz-pill-tag {}">{}</span>'
            '<span class="zyz-abo-resume-meta">{} acceptation{}</span>'
            '</div>',
            'is-premium' if n else 'is-membre',
            obj.libelle_cycle_premium,
            n,
            's' if n != 1 else '',
        )

    @admin.display(description='Journal')
    def journal_abonnements(self, obj):
        from django.utils.html import format_html
        from django.utils.safestring import mark_safe

        if not obj or not obj.pk:
            return format_html(
                '<p class="zyz-abo-empty">Enregistre le profil pour voir le journal.</p>',
            )
        rows = list(obj.historique_abonnements.select_related('admin_user')[:30])
        if not rows:
            return format_html(
                '<p class="zyz-abo-empty">Aucun événement pour l’instant.</p>',
            )

        def _fmt(dt):
            if not dt:
                return '—'
            return timezone.localtime(dt).strftime('%d/%m/%Y %H:%M')

        chunks = []
        for h in rows:
            meta = f'{_fmt(h.debut)} · {h.mois or 0} mois'
            if h.expire_le:
                meta += f' · jusqu’au {_fmt(h.expire_le)}'
            note_bits = []
            if h.admin_user_id:
                note_bits.append(h.admin_user.username)
            if h.note:
                note_bits.append(h.note)
            note_html = (
                format_html('<p class="zyz-abo-note">{}</p>', ' · '.join(note_bits))
                if note_bits else mark_safe('')
            )
            chunks.append(format_html(
                '<li class="zyz-abo-item type-{0}">'
                '<span class="zyz-abo-dot" aria-hidden="true"></span>'
                '<div class="zyz-abo-body">'
                '<div class="zyz-abo-top">'
                '<span class="zyz-abo-type">{1}</span>'
                '<span class="zyz-abo-ordre">{2}</span>'
                '</div>'
                '<p class="zyz-abo-meta">{3}</p>'
                '{4}'
                '</div>'
                '<time class="zyz-abo-time">{5}</time>'
                '</li>',
                h.type,
                h.get_type_display(),
                h.libelle_ordre,
                meta,
                note_html,
                _fmt(h.created_at),
            ))
        return mark_safe(
            '<ul class="zyz-abo-journal" role="list">'
            + ''.join(chunks)
            + '</ul>'
        )

    @admin.display(description='Expire', ordering='vip_expire_le')
    def expire_court(self, obj):
        if not obj.vip_expire_le:
            return '—'
        return timezone.localtime(obj.vip_expire_le).strftime('%d/%m/%Y')

    def save_model(self, request, obj, form, change):
        if obj.categorie in ('vip', 'premium'):
            obj.categorie = 'premium'
            if not obj.vip_depuis:
                obj.vip_depuis = timezone.now()
            if not obj.vip_expire_le:
                from paris.vip import ajouter_mois
                obj.vip_expire_le = ajouter_mois(obj.vip_depuis or timezone.now(), 1)
        super().save_model(request, obj, form, change)

    @admin.action(description='Octroyer Premium (1 mois à partir de maintenant)')
    def octroyer_vip(self, request, queryset):
        from paris.analytics import enregistrer_trace
        from paris.salon_welcome import publier_accueil_salon
        n = 0
        for profil in queryset:
            etait_premium = profil.abonnement_vip_actif
            deja = profil.a_deja_ete_premium
            profil.activer_vip(mois=1)
            type_evt = 'renouvellement' if deja else 'premier'
            profil.enregistrer_acceptation_premium(
                type_evt=type_evt,
                mois=1,
                admin_user=request.user,
                note='Octroi admin (+1 mois)',
            )
            profil.save(update_fields=[
                'categorie', 'vip_depuis', 'vip_expire_le', 'accueil_salon',
                'premium_acceptations',
            ])
            publier_accueil_salon(
                profil, renouvellement=etait_premium or deja,
            )
            enregistrer_trace(
                'vip',
                f'Premium octroyé · {profil.user.username} · {profil.libelle_cycle_premium}',
                user=request.user,
                detail=f'+1 mois · acceptations={profil.premium_acceptations}',
                path='/admin/paris/profil/',
            )
            n += 1
        self.message_user(
            request,
            f'{n} compte(s) Premium activé(s) pour 1 mois.',
            messages.SUCCESS,
        )

    @admin.action(description='Prolonger Premium (+1 mois)')
    def prolonger_vip(self, request, queryset):
        from paris.analytics import enregistrer_trace
        from paris.salon_welcome import publier_accueil_salon
        n = 0
        for profil in queryset:
            profil.prolonger_vip(mois=1)
            profil.enregistrer_acceptation_premium(
                type_evt='prolongation',
                mois=1,
                admin_user=request.user,
                note='Prolongation admin (+1 mois)',
            )
            profil.save(update_fields=[
                'categorie', 'vip_depuis', 'vip_expire_le', 'accueil_salon',
                'premium_acceptations',
            ])
            publier_accueil_salon(profil, renouvellement=True)
            enregistrer_trace(
                'vip',
                f'Premium prolongé · {profil.user.username} · {profil.libelle_cycle_premium}',
                user=request.user,
                detail=f'+1 mois · acceptations={profil.premium_acceptations}',
                path='/admin/paris/profil/',
            )
            n += 1
        self.message_user(
            request,
            f'{n} abonnement(s) prolongé(s) d’un mois.',
            messages.SUCCESS,
        )

    @admin.action(description='Retirer le statut Premium → Membre')
    def retirer_vip(self, request, queryset):
        from paris.analytics import enregistrer_trace
        n = 0
        for profil in queryset:
            profil.retirer_vip()
            profil.enregistrer_acceptation_premium(
                type_evt='retrait',
                admin_user=request.user,
                note='Retrait admin',
            )
            profil.save(update_fields=['categorie', 'vip_expire_le', 'accueil_salon'])
            enregistrer_trace(
                'vip',
                f'Premium retiré · {profil.user.username}',
                user=request.user,
                path='/admin/paris/profil/',
            )
            n += 1
        self.message_user(request, f'{n} compte(s) repassé(s) en Membre.', messages.WARNING)


@admin.register(ReglageSite)
class ReglageSiteAdmin(admin.ModelAdmin):
    list_display = ('resume', 'whatsapp_phone', 'vip_tarif_libelle', 'maj')
    fields = (
        'whatsapp_phone', 'whatsapp_message', 'whatsapp_url',
        'vip_tarif_libelle', 'updated_at',
    )
    readonly_fields = ('updated_at',)

    @admin.display(description='Réglages')
    def resume(self, obj):
        return 'Site Zanalyze'

    @admin.display(description='Mis à jour', ordering='updated_at')
    def maj(self, obj):
        return timezone.localtime(obj.updated_at).strftime('%d/%m/%Y %H:%M')

    def has_add_permission(self, request):
        return not ReglageSite.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PronosticPremium)
class PronosticPremiumAdmin(admin.ModelAdmin):
    list_display = ('user', 'match', 'choix', 'gagne', 'points', 'created_at')
    list_filter = ('choix', 'gagne')
    search_fields = ('user__username',)
    autocomplete_fields = ('user', 'match')
    readonly_fields = ('created_at',)


@admin.register(MessageChat)
class MessageChatAdmin(admin.ModelAdmin):
    list_display = ('quand', 'auteur', 'texte_court', 'a_image')
    list_filter = ()
    search_fields = ('texte', 'auteur__username')
    autocomplete_fields = ('auteur',)
    readonly_fields = ('created_at',)
    date_hierarchy = None

    @admin.display(description='Quand', ordering='created_at')
    def quand(self, obj):
        return timezone.localtime(obj.created_at).strftime('%d/%m %H:%M')

    @admin.display(description='Message')
    def texte_court(self, obj):
        t = obj.texte or ''
        if not t and obj.image:
            return '[image]'
        return t if len(t) <= 48 else t[:45] + '…'

    @admin.display(description='Image', boolean=True)
    def a_image(self, obj):
        return bool(obj.image)


@admin.register(VisiteJour)
class VisiteJourAdmin(admin.ModelAdmin):
    list_display = ('jour', 'visiteurs', 'pages_vues')
    ordering = ('-jour',)
    date_hierarchy = 'jour'
    readonly_fields = ('jour', 'visiteurs', 'pages_vues', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TraceActivite)
class TraceActiviteAdmin(admin.ModelAdmin):
    list_display = ('quand', 'badge_type', 'user', 'label', 'detail_court')
    list_filter = ('type',)
    search_fields = ('label', 'detail', 'user__username')
    readonly_fields = ('created_at', 'type', 'user', 'label', 'detail', 'path')
    list_per_page = 40
    date_hierarchy = 'created_at'

    @admin.display(description='Quand', ordering='created_at')
    def quand(self, obj):
        return timezone.localtime(obj.created_at).strftime('%d/%m %H:%M')

    @admin.display(description='Type', ordering='type')
    def badge_type(self, obj):
        return obj.get_type_display()

    @admin.display(description='Détail')
    def detail_court(self, obj):
        d = obj.detail or ''
        return d if len(d) <= 56 else d[:53] + '…'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
