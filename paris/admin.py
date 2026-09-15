from django.contrib import admin, messages
from django.utils import timezone

from paris.dashboard import build_dashboard_stats
from paris.models import (
    Analyse, Competition, Contexte, Cote, Equipe, Match, MessageChat, Option,
    Profil, PronosticPremium, PropositionParis, ReglageSite, Vote, VoteOption,
)

# Dashboard activité sur l’index admin.
_admin_index_orig = admin.site.index


def _admin_index(request, extra_context=None):
    # Ne pas binder avec __get__ : Django appelle site.index(request, …)
    # sans injecter self (attribut d’instance).
    ctx = dict(extra_context or {})
    ctx['title'] = 'Tableau de bord'
    try:
        ctx['zanalyz_stats'] = build_dashboard_stats()
        ctx['zanalyz_reglages'] = ReglageSite.get_solo()
    except Exception:  # noqa: BLE001 — migrations en cours
        ctx['zanalyz_stats'] = None
        ctx['zanalyz_reglages'] = None
    return _admin_index_orig(request, ctx)


admin.site.index = _admin_index
admin.site.index_template = 'admin/paris/index.html'
admin.site.site_header = 'Zanalyze'
admin.site.site_title = 'Zanalyze Admin'
admin.site.index_title = 'Tableau de bord'
admin.site.enable_nav_sidebar = True


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


@admin.register(Profil)
class ProfilAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'badge_categorie', 'points_premium', 'expire_court', 'note_admin',
    )
    list_filter = ('categorie',)
    search_fields = ('user__username', 'note_admin')
    autocomplete_fields = ('user',)
    list_editable = ()
    actions = ('octroyer_vip', 'prolonger_vip', 'retirer_vip')
    readonly_fields = ()
    fieldsets = (
        (None, {
            'fields': (
                'user', 'categorie', 'points_premium',
                'vip_depuis', 'vip_expire_le', 'note_admin',
            ),
            'description': (
                'À l’octroi, l’abonnement Premium dure 1 mois. '
                'Tu peux prolonger via l’action « Prolonger Premium (+1 mois) » '
                'ou en modifiant « VIP expire le ».'
            ),
        }),
    )

    @admin.display(description='Statut', ordering='categorie')
    def badge_categorie(self, obj):
        from django.utils.html import format_html
        if obj.abonnement_vip_actif:
            return format_html(
                '<span style="display:inline-flex;align-items:center;padding:3px 10px;'
                'border-radius:999px;font-size:11px;font-weight:800;letter-spacing:.04em;'
                'background:#fff4ec;color:#e8631c;border:1px solid #ffd7bf;">Premium</span>',
            )
        if obj.categorie in ('vip', 'premium'):
            return format_html(
                '<span style="display:inline-flex;align-items:center;padding:3px 10px;'
                'border-radius:999px;font-size:11px;font-weight:800;letter-spacing:.04em;'
                'background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;">Expiré</span>',
            )
        return format_html(
            '<span style="display:inline-flex;align-items:center;padding:3px 10px;'
            'border-radius:999px;font-size:11px;font-weight:700;'
            'background:#f3f4f6;color:#6b7280;">Membre</span>',
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
        n = 0
        for profil in queryset:
            profil.activer_vip(mois=1)
            profil.save(update_fields=['categorie', 'vip_depuis', 'vip_expire_le'])
            n += 1
        self.message_user(
            request,
            f'{n} compte(s) Premium activé(s) pour 1 mois.',
            messages.SUCCESS,
        )

    @admin.action(description='Prolonger Premium (+1 mois)')
    def prolonger_vip(self, request, queryset):
        n = 0
        for profil in queryset:
            profil.prolonger_vip(mois=1)
            profil.save(update_fields=['categorie', 'vip_depuis', 'vip_expire_le'])
            n += 1
        self.message_user(
            request,
            f'{n} abonnement(s) prolongé(s) d’un mois.',
            messages.SUCCESS,
        )

    @admin.action(description='Retirer le statut Premium → Membre')
    def retirer_vip(self, request, queryset):
        n = 0
        for profil in queryset:
            profil.retirer_vip()
            profil.save(update_fields=['categorie', 'vip_expire_le'])
            n += 1
        self.message_user(request, f'{n} compte(s) repassé(s) en Membre.', messages.WARNING)


@admin.register(ReglageSite)
class ReglageSiteAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'whatsapp_phone', 'vip_tarif_libelle', 'updated_at')
    fields = (
        'whatsapp_phone', 'whatsapp_message', 'whatsapp_url',
        'vip_tarif_libelle', 'updated_at',
    )
    readonly_fields = ('updated_at',)

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
