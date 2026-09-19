from django.conf import settings
from django.db import models
from django.utils import timezone


class Competition(models.Model):
    code = models.SlugField(max_length=20, unique=True)   # 'PL', 'BL', 'UCL', 'FAC', …
    nom = models.CharField(max_length=80)                  # 'Premier League'
    pays = models.CharField(max_length=40, blank=True)
    ordre = models.PositiveSmallIntegerField(default=100)  # ordre d'affichage
    actif = models.BooleanField(default=True)
    sofascore_id = models.PositiveIntegerField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ['ordre', 'nom']
        verbose_name = 'Compétition'
        verbose_name_plural = 'Compétitions'

    def __str__(self):
        return self.nom


class Equipe(models.Model):
    nom = models.CharField(max_length=80, unique=True)
    nom_court = models.CharField(max_length=24)            # pour l'affichage mobile
    slug = models.SlugField(unique=True)
    sofascore_id = models.PositiveIntegerField(null=True, blank=True, unique=True)
    thesportsdb_id = models.PositiveIntegerField(null=True, blank=True, unique=True)
    # URL logo chargeable par le navigateur (évite le proxy serveur / egress PA)
    logo_externe = models.URLField(max_length=500, blank=True, default='')
    # Fiche club précalculée (forme / classement / récents) pour hébergeurs sans API live
    fiche_club = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = 'Équipe'
        verbose_name_plural = 'Équipes'

    def __str__(self):
        return self.nom_court or self.nom


class Match(models.Model):
    STATUT = [('a_venir', 'À venir'), ('en_cours', 'En cours'),
              ('termine', 'Terminé'), ('reporte', 'Reporté')]

    competition = models.ForeignKey(Competition, on_delete=models.PROTECT,
                                    related_name='matchs')
    domicile = models.ForeignKey(Equipe, on_delete=models.PROTECT, related_name='+')
    exterieur = models.ForeignKey(Equipe, on_delete=models.PROTECT, related_name='+')
    coup_denvoi = models.DateTimeField(db_index=True)
    journee = models.CharField(max_length=40, blank=True)  # 'Journée 1'
    statut = models.CharField(max_length=10, choices=STATUT, default='a_venir')
    sofascore_id = models.PositiveIntegerField(null=True, blank=True, unique=True)

    # résultat, rempli après le match
    buts_dom = models.PositiveSmallIntegerField(null=True, blank=True)
    buts_ext = models.PositiveSmallIntegerField(null=True, blank=True)
    buts_dom_mt = models.PositiveSmallIntegerField(null=True, blank=True)
    buts_ext_mt = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['coup_denvoi']
        verbose_name = 'Match'
        verbose_name_plural = 'Matchs'
        indexes = [models.Index(fields=['statut', 'coup_denvoi']),
                   models.Index(fields=['competition', 'coup_denvoi'])]
        constraints = [models.UniqueConstraint(
            fields=['domicile', 'exterieur', 'coup_denvoi'], name='match_unique')]

    def __str__(self):
        return f"{self.domicile} – {self.exterieur}"

    @property
    def score(self):
        if self.buts_dom is None: return None
        return f"{self.buts_dom}-{self.buts_ext}"


class Cote(models.Model):
    """Une cote relevée. Sert d'entrée au calcul, jamais de critère de décision."""
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='cotes')
    bookmaker = models.CharField(max_length=40)            # 'consensus', 'PMUG', ...
    marche = models.CharField(max_length=20)               # '1X2', 'OU25', 'BTTS'
    selection = models.CharField(max_length=20)            # '1', 'N', '2', 'over', 'under'
    valeur = models.DecimalField(max_digits=7, decimal_places=3)
    nb_sources = models.PositiveSmallIntegerField(default=1)
    releve_le = models.DateTimeField()

    class Meta:
        verbose_name = 'Cote'
        verbose_name_plural = 'Cotes'
        indexes = [models.Index(fields=['match', 'marche'])]

    def __str__(self):
        return f"{self.match} {self.marche} {self.selection} {self.valeur}"


class Analyse(models.Model):
    """Le résultat du moteur pour un match, à un instant donné."""
    match = models.OneToOneField(Match, on_delete=models.CASCADE, related_name='analyse')
    buts_dom_attendus = models.FloatField()
    buts_ext_attendus = models.FloatField()
    p1 = models.FloatField()
    pn = models.FloatField()
    p2 = models.FloatField()
    score_probable = models.CharField(max_length=8)
    profil = models.CharField(max_length=16)               # equilibre / moyen / desequilibre
    marge_marche = models.FloatField()
    residu = models.FloatField()                           # qualité de l'ajustement
    version_moteur = models.CharField(max_length=12)
    calcule_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Analyse moteur'
        verbose_name_plural = 'Analyses moteur'

    def __str__(self):
        return f"Analyse {self.match}"


class Option(models.Model):
    """Une option de pari proposée pour un match."""
    NIVEAU = [('prudente', 'Prudent'), ('recommandee', 'Recommandé'),
              ('equilibree', 'Équilibrée'), ('audacieuse', 'Audacieuse'),
              ('filet', 'Sécurité'), ('detail', 'Détail')]
    ORIGINE = [('marche', 'Marché'), ('calcul', 'Calculé')]
    RESULTAT = [('attente', 'En attente'), ('gagne', 'Gagné'),
                ('perdu', 'Perdu'), ('annule', 'Annulé')]

    analyse = models.ForeignKey(Analyse, on_delete=models.CASCADE, related_name='options')
    famille = models.CharField(max_length=32)              # 'Total buts', 'Handicap', ...
    code = models.CharField(max_length=32)                 # CLÉ : voir évaluateur ci-dessous
    libelle = models.CharField(max_length=120)             # texte affiché, en français
    probabilite = models.FloatField()                      # après correction
    cote_juste = models.FloatField()
    niveau = models.CharField(max_length=12, choices=NIVEAU, default='detail')
    origine = models.CharField(max_length=8, choices=ORIGINE)

    # rempli automatiquement après le match
    resultat = models.CharField(max_length=8, choices=RESULTAT, default='attente')
    regle_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Tip / option'
        verbose_name_plural = 'Tips / options'
        indexes = [models.Index(fields=['niveau', 'resultat']),
                   models.Index(fields=['famille', 'resultat'])]

    def __str__(self):
        return f"{self.libelle} ({self.code})"


class Contexte(models.Model):
    """Forme, absents, à savoir. Texte libre en français, affiché tel quel."""
    match = models.OneToOneField(Match, on_delete=models.CASCADE, related_name='contexte')
    forme_dom = models.TextField(blank=True)
    forme_ext = models.TextField(blank=True)
    absents_dom = models.TextField(blank=True)
    absents_ext = models.TextField(blank=True)
    tendance_buts = models.TextField(blank=True)
    a_savoir = models.TextField(blank=True)
    confrontations = models.TextField(blank=True)
    fiabilite = models.CharField(max_length=8, default='moyenne')
    source = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = 'Contexte match'
        verbose_name_plural = 'Contextes match'

    def __str__(self):
        return f"Contexte {self.match}"


class PropositionParis(models.Model):
    """Proposition libre d'un utilisateur sur un match (pour stats / votes)."""
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='propositions')
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='propositions',
    )
    libelle = models.CharField(max_length=160)
    confiance = models.PositiveSmallIntegerField(default=50)  # 1–99 affiché en %
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Proposition utilisateur'
        verbose_name_plural = 'Propositions utilisateurs'
        constraints = [
            models.UniqueConstraint(
                fields=['match', 'auteur'],
                name='prop_unique_user_match',
            ),
        ]

    def __str__(self):
        return f"{self.libelle} ({self.match})"


class Vote(models.Model):
    CHOIX = [('like', 'Like'), ('dislike', 'Dislike')]
    proposition = models.ForeignKey(
        PropositionParis, on_delete=models.CASCADE, related_name='votes',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='votes',
    )
    choix = models.CharField(max_length=8, choices=CHOIX)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Vote proposition'
        verbose_name_plural = 'Votes propositions'
        constraints = [
            models.UniqueConstraint(
                fields=['proposition', 'user'], name='vote_unique_user_prop',
            ),
        ]

    def __str__(self):
        return f"{self.user} → {self.choix}"


class VoteOption(models.Model):
    """Accord / désaccord sur une recommandation du moteur (consensus)."""
    CHOIX = [('like', 'D’accord'), ('dislike', 'Pas d’accord')]
    option = models.ForeignKey(
        Option, on_delete=models.CASCADE, related_name='votes_consensus',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='votes_options',
    )
    choix = models.CharField(max_length=8, choices=CHOIX)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Vote tip'
        verbose_name_plural = 'Votes tips'
        constraints = [
            models.UniqueConstraint(
                fields=['option', 'user'], name='vote_unique_user_option',
            ),
        ]

    def __str__(self):
        return f"{self.user} → {self.option_id} {self.choix}"


class Profil(models.Model):
    """Catégorie compte : membre (défaut) ou Premium (justifs + Salon + Nos Zanalyze)."""
    CATEGORIES = [
        ('membre', 'Membre'),
        ('premium', 'Premium'),
    ]
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profil',
    )
    categorie = models.CharField(
        max_length=16, choices=CATEGORIES, default='membre', db_index=True,
    )
    vip_depuis = models.DateTimeField(
        null=True, blank=True,
        help_text='Date de la dernière activation Premium.',
    )
    vip_expire_le = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text='Fin d’abonnement (en général +1 mois après validation). Editable pour prolonger.',
    )
    points_premium = models.PositiveIntegerField(
        default=0,
        help_text='Points challenge (pronostics / propositions).',
    )
    points_decay_le = models.DateTimeField(
        null=True, blank=True,
        help_text='Dernière application de la décroissance (−1 pt / 24 h).',
    )
    note_admin = models.CharField(max_length=200, blank=True)
    accueil_salon = models.BooleanField(
        default=False,
        help_text='Si vrai, le prochain chargement app ouvre le Salon avec un message de bienvenue.',
    )

    class Meta:
        verbose_name = 'Profil utilisateur'
        verbose_name_plural = 'Profils utilisateurs'

    def __str__(self):
        return f'{self.user.username} ({self.categorie})'

    @property
    def est_vip(self) -> bool:
        return self.abonnement_vip_actif

    @property
    def abonnement_vip_actif(self) -> bool:
        # 'vip' legacy encore possible avant migration data.
        if self.categorie not in ('premium', 'vip'):
            return False
        if self.vip_expire_le is None:
            return True  # legacy sans date → actif jusqu’à retrait
        return self.vip_expire_le > timezone.now()

    def activer_vip(self, mois: int = 1) -> None:
        """Active (ou renouvelle) le Premium pour N mois à partir de maintenant."""
        from paris.vip import debut_abonnement
        debut, fin = debut_abonnement(mois)
        self.categorie = 'premium'
        self.vip_depuis = debut
        self.vip_expire_le = fin
        self.accueil_salon = True

    def prolonger_vip(self, mois: int = 1) -> None:
        """Ajoute N mois à la fin d’abonnement (ou depuis maintenant si expiré)."""
        from paris.vip import nouvelle_expiration
        maintenant = timezone.now()
        self.categorie = 'premium'
        if not self.vip_depuis:
            self.vip_depuis = maintenant
        self.vip_expire_le = nouvelle_expiration(self.vip_expire_le, mois)
        self.accueil_salon = True

    def retirer_vip(self) -> None:
        self.categorie = 'membre'
        self.vip_expire_le = timezone.now()
        self.accueil_salon = False


class PronosticPremium(models.Model):
    """Pronostic 1X2 d’un membre Premium (gamification / classement)."""
    CHOIX = [
        ('1', 'Domicile'),
        ('N', 'Nul'),
        ('2', 'Extérieur'),
    ]
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='pronostics')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='pronostics',
    )
    choix = models.CharField(max_length=1, choices=CHOIX)
    points = models.PositiveSmallIntegerField(null=True, blank=True)
    gagne = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Pronostic Premium'
        verbose_name_plural = 'Pronostics Premium'
        constraints = [
            models.UniqueConstraint(
                fields=['match', 'user'],
                name='prono_unique_user_match',
            ),
        ]

    def __str__(self):
        return f'{self.user} → {self.match_id} ({self.choix})'


class ReglageSite(models.Model):
    """Réglages globaux (singleton) — WhatsApp Premium, etc."""
    whatsapp_phone = models.CharField(
        max_length=32, blank=True,
        help_text='Numéro international sans + (ex. 33612345678).',
    )
    whatsapp_message = models.CharField(
        max_length=300, blank=True,
        default='Bonjour, je souhaite devenir Premium sur Zanalyze.',
        help_text='Message prérempli quand l’utilisateur ouvre WhatsApp.',
    )
    whatsapp_url = models.URLField(
        blank=True,
        help_text='Lien WhatsApp complet (prioritaire si renseigné).',
    )
    vip_tarif_libelle = models.CharField(
        max_length=120, blank=True, default='Premium Zanalyze',
        help_text='Court libellé affiché sur le CTA (ex. « Premium — 4,99 € / mois »).',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Réglages site'
        verbose_name_plural = 'Réglages site'

    def __str__(self):
        return 'Réglages Zanalyze'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> 'ReglageSite':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def lien_whatsapp_vip(self) -> str:
        from urllib.parse import quote
        import os
        import re
        if (self.whatsapp_url or '').strip():
            return self.whatsapp_url.strip()
        phone = re.sub(r'\D', '', self.whatsapp_phone or '')
        if not phone:
            phone = re.sub(
                r'\D', '',
                os.environ.get('ZANALYZ_WHATSAPP_PHONE')
                or os.environ.get('C2B_WHATSAPP_PHONE', ''),
            )
        if not phone:
            return ''
        msg = (self.whatsapp_message or 'Bonjour, je souhaite devenir Premium sur Zanalyze.').strip()
        return f'https://wa.me/{phone}?text={quote(msg)}'


class MessageChat(models.Model):
    """Message du Salon Premium — purgé automatiquement après 24 h."""
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='messages_chat',
    )
    texte = models.CharField(max_length=400, blank=True, default='')
    image = models.FileField(upload_to='salon/%Y/%m/%d/', blank=True, null=True)
    systeme = models.BooleanField(
        default=False, db_index=True,
        help_text='Annonce système (bienvenue Premium, etc.).',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Message Salon Premium'
        verbose_name_plural = 'Messages Salon Premium'

    def __str__(self):
        apercu = (self.texte or '').strip() or ('[image]' if self.image else '')
        return f'{self.auteur_id}:{apercu[:40]}'


class VisiteJour(models.Model):
    """Agrégats quotidiens visiteurs / pages (rempli par le middleware analytics)."""
    jour = models.DateField(unique=True, db_index=True)
    visiteurs = models.PositiveIntegerField(default=0)
    pages_vues = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-jour']
        verbose_name = 'Visite du jour'
        verbose_name_plural = 'Visites quotidiennes'

    def __str__(self):
        return f'{self.jour} · {self.visiteurs} visiteurs'


class TraceActivite(models.Model):
    """Fil d’activité plateforme pour le suivi admin."""
    TYPES = [
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
    ]
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    type = models.CharField(max_length=20, choices=TYPES, default='autre', db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='traces_activite',
    )
    label = models.CharField(max_length=220)
    detail = models.CharField(max_length=400, blank=True, default='')
    path = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Trace d’activité'
        verbose_name_plural = 'Traces d’activité'
        indexes = [
            models.Index(fields=['-created_at', 'type'], name='trace_at_type'),
        ]

    def __str__(self):
        who = self.user.username if self.user_id else 'anonyme'
        return f'{self.created_at:%d/%m %H:%M} · {who} · {self.label}'
