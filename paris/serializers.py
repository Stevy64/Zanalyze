from rest_framework import serializers

from paris.models import (
    Analyse, Competition, Contexte, Match, MessageChat, Option, PronosticPremium,
    PropositionParis,
)
from paris.moteur import RESIDU_DOUTEUX

NIVEAUX_LISTE = ('prudente', 'equilibree', 'audacieuse')
# Nos Zanalyze / historique : tips + recommandée + filet de sécurité
NIVEAUX_COMPOS = ('prudente', 'recommandee', 'equilibree', 'audacieuse', 'filet')


def _est_vip_request(request) -> bool:
    from paris.roles import est_vip
    user = getattr(request, 'user', None) if request else None
    return est_vip(user)


def _user_request(request):
    return getattr(request, 'user', None) if request else None


def _justifier_si_tip(option, *, analyse=None, match=None, request=None):
    """Justifications réservées selon le rôle / statut du match."""
    from paris.bilan_acces import peut_details_option

    user = _user_request(request)
    if match is None and analyse is not None:
        match = getattr(analyse, 'match', None)
    if analyse is None and match is not None:
        analyse = getattr(match, 'analyse', None)
    if match is not None and not peut_details_option(user, match):
        return None
    if match is None and not _est_vip_request(request):
        return None
    if getattr(option, 'niveau', None) not in NIVEAUX_COMPOS:
        return None
    from paris.justification import justifier_option
    contexte = None
    if match is not None:
        try:
            contexte = match.contexte
        except Exception:  # noqa: BLE001 — Contexte.DoesNotExist
            contexte = None
    try:
        return justifier_option(
            option=option,
            analyse=analyse,
            contexte=contexte,
            domicile=match.domicile.nom_court if match else '',
            exterieur=match.exterieur.nom_court if match else '',
        )
    except Exception:  # noqa: BLE001 — ne pas faire échouer toute la fiche
        return None


def _consensus(option, request):
    cached = getattr(option, '_consensus_cache', None)
    if cached is not None:
        return cached
    votes = list(option.votes_consensus.all())
    likes = sum(1 for v in votes if v.choix == 'like')
    dislikes = sum(1 for v in votes if v.choix == 'dislike')
    mon = None
    if request and getattr(request, 'user', None) and request.user.is_authenticated:
        uid = request.user.id
        for v in votes:
            if v.user_id == uid:
                mon = v.choix
                break
    total = likes + dislikes
    result = {
        'likes': likes,
        'dislikes': dislikes,
        'pct_likes': round(100 * likes / total) if total else None,
        'mon_vote': mon,
    }
    option._consensus_cache = result
    return result


class CompetitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Competition
        fields = ('id', 'code', 'nom', 'pays', 'ordre')


class EquipeCourtSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nom = serializers.CharField()
    nom_court = serializers.CharField()
    slug = serializers.CharField()
    logo_url = serializers.SerializerMethodField()

    def get_logo_url(self, obj):
        """URL directe pour le navigateur (pas le proxy serveur)."""
        from paris.clubs import logo_url_pour
        return logo_url_pour(obj) or None


class OptionListeSerializer(serializers.ModelSerializer):
    likes = serializers.SerializerMethodField()
    dislikes = serializers.SerializerMethodField()
    pct_likes = serializers.SerializerMethodField()
    mon_vote = serializers.SerializerMethodField()
    justification = serializers.SerializerMethodField()

    class Meta:
        model = Option
        fields = (
            'id', 'niveau', 'libelle', 'probabilite', 'resultat',
            'famille', 'code', 'cote_juste', 'origine',
            'likes', 'dislikes', 'pct_likes', 'mon_vote', 'justification',
        )

    def _c(self, obj):
        return _consensus(obj, self.context.get('request'))

    def get_likes(self, obj):
        return self._c(obj)['likes']

    def get_dislikes(self, obj):
        return self._c(obj)['dislikes']

    def get_pct_likes(self, obj):
        return self._c(obj)['pct_likes']

    def get_mon_vote(self, obj):
        return self._c(obj)['mon_vote']

    def get_justification(self, obj):
        match = getattr(obj, '_parent_match', None)
        analyse = getattr(match, 'analyse', None) if match else getattr(obj, 'analyse', None)
        return _justifier_si_tip(
            obj,
            analyse=analyse,
            match=match,
            request=self.context.get('request'),
        )


class MatchListeSerializer(serializers.ModelSerializer):
    competition = CompetitionSerializer()
    domicile = EquipeCourtSerializer()
    exterieur = EquipeCourtSerializer()
    score = serializers.CharField(allow_null=True)
    options = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = (
            'id', 'competition', 'domicile', 'exterieur',
            'coup_denvoi', 'journee', 'statut', 'score', 'options',
        )

    def get_options(self, obj):
        from paris.bilan_acces import filtrer_options_bilan

        try:
            opts = [o for o in obj.analyse.options.all() if o.niveau in NIVEAUX_COMPOS]
        except Analyse.DoesNotExist:
            return []
        user = _user_request(self.context.get('request'))
        opts = filtrer_options_bilan(user, obj, opts)
        ordre = {n: i for i, n in enumerate(NIVEAUX_COMPOS)}
        opts.sort(key=lambda o: ordre.get(o.niveau, 9))
        for o in opts:
            o._parent_match = obj
        return OptionListeSerializer(opts, many=True, context=self.context).data


class OptionDetailSerializer(serializers.ModelSerializer):
    likes = serializers.SerializerMethodField()
    dislikes = serializers.SerializerMethodField()
    pct_likes = serializers.SerializerMethodField()
    mon_vote = serializers.SerializerMethodField()
    justification = serializers.SerializerMethodField()

    class Meta:
        model = Option
        fields = (
            'id', 'famille', 'code', 'libelle', 'probabilite',
            'cote_juste', 'niveau', 'origine', 'resultat',
            'likes', 'dislikes', 'pct_likes', 'mon_vote', 'justification',
        )

    def _c(self, obj):
        return _consensus(obj, self.context.get('request'))

    def get_likes(self, obj):
        return self._c(obj)['likes']

    def get_dislikes(self, obj):
        return self._c(obj)['dislikes']

    def get_pct_likes(self, obj):
        return self._c(obj)['pct_likes']

    def get_mon_vote(self, obj):
        return self._c(obj)['mon_vote']

    def get_justification(self, obj):
        analyse = getattr(obj, 'analyse', None)
        match = getattr(analyse, 'match', None) if analyse else None
        return _justifier_si_tip(
            obj,
            analyse=analyse,
            match=match,
            request=self.context.get('request'),
        )


class AnalyseSerializer(serializers.ModelSerializer):
    douteuse = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()

    class Meta:
        model = Analyse
        fields = (
            'buts_dom_attendus', 'buts_ext_attendus',
            'p1', 'pn', 'p2', 'score_probable', 'profil',
            'marge_marche', 'residu', 'douteuse',
            'version_moteur', 'calcule_le', 'options',
        )

    def get_douteuse(self, obj):
        return obj.residu > RESIDU_DOUTEUX

    def get_options(self, obj):
        from paris.bilan_acces import filtrer_options_bilan

        match = getattr(obj, 'match', None)
        opts = list(obj.options.all())
        user = _user_request(self.context.get('request'))
        if match is not None:
            opts = filtrer_options_bilan(user, match, opts)
            for o in opts:
                o._parent_match = match
        return OptionDetailSerializer(opts, many=True, context=self.context).data


class ContexteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contexte
        fields = (
            'forme_dom', 'forme_ext', 'absents_dom', 'absents_ext',
            'tendance_buts', 'a_savoir', 'confrontations',
            'fiabilite',
        )


class MatchDetailSerializer(serializers.ModelSerializer):
    competition = CompetitionSerializer()
    domicile = EquipeCourtSerializer()
    exterieur = EquipeCourtSerializer()
    score = serializers.CharField(allow_null=True)
    analyse = serializers.SerializerMethodField()
    contexte = serializers.SerializerMethodField()
    bilan_complet = serializers.SerializerMethodField()
    mon_pronostic = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = (
            'id', 'competition', 'domicile', 'exterieur',
            'coup_denvoi', 'journee', 'statut',
            'buts_dom', 'buts_ext', 'buts_dom_mt', 'buts_ext_mt',
            'score', 'analyse', 'contexte', 'bilan_complet', 'mon_pronostic',
        )

    def get_analyse(self, obj):
        try:
            return AnalyseSerializer(obj.analyse, context=self.context).data
        except Analyse.DoesNotExist:
            return None

    def get_contexte(self, obj):
        try:
            return ContexteSerializer(obj.contexte).data
        except Contexte.DoesNotExist:
            return None

    def get_bilan_complet(self, obj):
        from paris.bilan_acces import peut_bilan_complet
        if obj.statut != 'termine':
            return True
        return peut_bilan_complet(_user_request(self.context.get('request')))

    def get_mon_pronostic(self, obj):
        request = self.context.get('request')
        user = _user_request(request)
        if not user or not getattr(user, 'is_authenticated', False):
            return None
        prono = (
            PronosticPremium.objects
            .filter(match=obj, user=user)
            .first()
        )
        if not prono:
            return None
        return {
            'choix': prono.choix,
            'points': prono.points,
            'gagne': prono.gagne,
        }


class ResultatSerializer(serializers.Serializer):
    buts_dom = serializers.IntegerField(min_value=0, max_value=30)
    buts_ext = serializers.IntegerField(min_value=0, max_value=30)
    buts_dom_mt = serializers.IntegerField(
        min_value=0, max_value=30, required=False, allow_null=True,
    )
    buts_ext_mt = serializers.IntegerField(
        min_value=0, max_value=30, required=False, allow_null=True,
    )

    def validate(self, data):
        bd_mt, be_mt = data.get('buts_dom_mt'), data.get('buts_ext_mt')
        if (bd_mt is None) ^ (be_mt is None):
            raise serializers.ValidationError(
                'Les deux scores mi-temps doivent être fournis ensemble.'
            )
        if bd_mt is not None and be_mt is not None:
            if bd_mt > data['buts_dom'] or be_mt > data['buts_ext']:
                raise serializers.ValidationError(
                    'Le score mi-temps ne peut pas dépasser le score final.'
                )
        return data


class AuthSerializer(serializers.Serializer):
    """Inscription — mot de passe ≥ 8 caractères."""
    username = serializers.CharField(max_length=150, min_length=3)
    password = serializers.CharField(write_only=True, min_length=8)
    email = serializers.EmailField(required=False, allow_blank=True)


class LoginSerializer(serializers.Serializer):
    """Connexion — n’impose pas la longueur MDP (comptes legacy)."""
    username = serializers.CharField(max_length=150, min_length=1)
    password = serializers.CharField(write_only=True, allow_blank=False)

class PropositionSerializer(serializers.ModelSerializer):
    auteur = serializers.CharField(source='auteur.username', read_only=True)
    likes = serializers.IntegerField(read_only=True)
    dislikes = serializers.IntegerField(read_only=True)
    mon_vote = serializers.SerializerMethodField()
    pct_likes = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()

    class Meta:
        model = PropositionParis
        fields = (
            'id', 'libelle', 'type', 'confiance', 'auteur', 'created_at',
            'likes', 'dislikes', 'pct_likes', 'mon_vote',
        )
        read_only_fields = ('id', 'auteur', 'created_at')

    def get_type(self, obj):
        for code, label in TYPES_PROPOSITION.items():
            if obj.libelle == label:
                return code
        return None

    def get_mon_vote(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        v = obj.votes.filter(user=request.user).first()
        return v.choix if v else None

    def get_pct_likes(self, obj):
        total = obj.likes + obj.dislikes
        if total == 0:
            return None
        return round(100 * obj.likes / total)


TYPES_PROPOSITION = {
    'vainqueur_dom': 'Vainqueur domicile',
    'nul': 'Match nul',
    'vainqueur_ext': 'Vainqueur extérieur',
    'plus_25': 'Plus de 2,5 buts',
    'moins_25': 'Moins de 2,5 buts',
}


class PropositionCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=list(TYPES_PROPOSITION.keys()))
    confiance = serializers.IntegerField(min_value=1, max_value=99, default=50)

    def to_libelle(self):
        return TYPES_PROPOSITION[self.validated_data['type']]


class VoteSerializer(serializers.Serializer):
    choix = serializers.ChoiceField(choices=['like', 'dislike'])


class MessageChatSerializer(serializers.ModelSerializer):
    auteur = serializers.CharField(source='auteur.username', read_only=True)
    est_moi = serializers.SerializerMethodField()
    initiale = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    piece_kind = serializers.SerializerMethodField()
    piece_nom = serializers.SerializerMethodField()

    class Meta:
        model = MessageChat
        fields = (
            'id', 'auteur', 'texte', 'image_url',
            'piece_kind', 'piece_nom', 'systeme',
            'created_at', 'est_moi', 'initiale',
        )

    def get_est_moi(self, obj):
        request = self.context.get('request')
        return bool(
            request and request.user.is_authenticated and obj.auteur_id == request.user.id
        )

    def get_initiale(self, obj):
        nom = (obj.auteur.username or '?').strip()
        return (nom[0] if nom else '?').upper()

    def get_image_url(self, obj):
        if not obj.image:
            return None
        # URL relative (/media/...) : même origine, fiable en local et sur PA.
        return obj.image.url

    def _piece_name(self, obj) -> str:
        try:
            return (obj.image.name or '').rsplit('/', 1)[-1]
        except Exception:  # noqa: BLE001
            return ''

    def get_piece_kind(self, obj):
        if not obj.image:
            return None
        nom = self._piece_name(obj).lower()
        if nom.endswith('.pdf'):
            return 'pdf'
        return 'image'

    def get_piece_nom(self, obj):
        if not obj.image:
            return None
        return self._piece_name(obj) or None


class MessageCreateSerializer(serializers.Serializer):
    texte = serializers.CharField(required=False, allow_blank=True, max_length=400)
    image = serializers.FileField(required=False, allow_null=True)

    _IMAGE_TYPES = frozenset({
        'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif',
    })
    _PDF_TYPES = frozenset({'application/pdf'})
    _IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
    _PDF_EXT = ('.pdf',)
    _FILE_MAX = 5 * 1024 * 1024

    def validate_texte(self, value):
        return ' '.join((value or '').split())

    def validate_image(self, value):
        if not value:
            return None
        if getattr(value, 'size', 0) > self._FILE_MAX:
            raise serializers.ValidationError('Fichier trop lourd (5 Mo max).')
        name = (getattr(value, 'name', '') or '').lower()
        ctype = (getattr(value, 'content_type', '') or '').lower()
        if name.endswith(self._PDF_EXT) or ctype in self._PDF_TYPES:
            if ctype and ctype not in self._PDF_TYPES:
                raise serializers.ValidationError('PDF invalide.')
            return value
        if not name.endswith(self._IMAGE_EXT):
            raise serializers.ValidationError('Formats : JPG, PNG, WEBP, GIF, PDF.')
        if ctype and ctype not in self._IMAGE_TYPES:
            raise serializers.ValidationError('Fichier image invalide.')
        return value

    def validate(self, attrs):
        texte = attrs.get('texte') or ''
        image = attrs.get('image')
        if not texte and not image:
            raise serializers.ValidationError({'texte': 'Message vide.'})
        if len(texte) > 400:
            raise serializers.ValidationError({'texte': 'Message trop long (400 car. max).'})
        attrs['texte'] = texte
        return attrs


class PronosticCreateSerializer(serializers.Serializer):
    choix = serializers.ChoiceField(choices=['1', 'N', '2'])
