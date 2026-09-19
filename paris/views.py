from datetime import datetime, time as dt_time, timezone as dt_timezone
import hashlib

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.cache import patch_cache_control
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from paris.models import (
    Competition, Equipe, Match, MessageChat, Option, Profil, PronosticPremium,
    PropositionParis, ReglageSite, Vote, VoteOption,
)
from paris.moteur import VERSION_MOTEUR
from paris.reglement import regler_match
from paris.chat import messages_actifs, purger_messages_expires
from paris.roles import est_vip, payload_auth
from paris.serializers import (
    AuthSerializer,
    CompetitionSerializer,
    LoginSerializer,
    MatchDetailSerializer,
    MatchListeSerializer,
    MessageChatSerializer,
    MessageCreateSerializer,
    NIVEAUX_COMPOS,
    PronosticCreateSerializer,
    PropositionCreateSerializer,
    PropositionSerializer,
    ResultatSerializer,
    TYPES_PROPOSITION,
    VoteSerializer,
)
from paris.presence import compter_en_ligne, marquer_en_ligne

MIN_ECHANTILLON = 20


def _payload_auth(user):
    return payload_auth(user)


def _payload_vip_public():
    cfg = ReglageSite.get_solo()
    return {
        'whatsapp_vip_url': cfg.lien_whatsapp_vip(),
        'vip_tarif_libelle': cfg.vip_tarif_libelle or 'Premium Zanalyze',
    }


class Pagination30(PageNumberPagination):
    page_size = 30
    page_size_query_param = 'page_size'
    max_page_size = 120


class CacheETagMixin:
    """Cache HTTP court pour GET anonymes. Pas d’ETag partagé si session auth
    (évite de servir mon_vote d’un user à un autre via proxy)."""
    cache_seconds = 300

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if hasattr(response, 'render') and callable(response.render):
            response.render()
        if request.method == 'GET' and 200 <= response.status_code < 300:
            response['Vary'] = 'Cookie'
            if getattr(request, 'user', None) and request.user.is_authenticated:
                patch_cache_control(response, private=True, max_age=0, no_store=True)
            else:
                patch_cache_control(response, max_age=self.cache_seconds, public=True)
                body = response.content
                if body:
                    response['ETag'] = '"' + hashlib.md5(body).hexdigest() + '"'
        return response


def _fenetre_jour(d):
    """Borne [début, fin] d’un jour civil dans le fuseau Django (Europe/Paris)."""
    tz = timezone.get_current_timezone()
    debut = timezone.make_aware(datetime.combine(d, dt_time.min), tz)
    fin = timezone.make_aware(datetime.combine(d, dt_time.max), tz)
    return debut, fin


def _matchs_qs():
    # Uniquement matchs issus d’une source externe (ids snapshot / ESPN).
    # Les JSON de démo (sans sofascore_id) ne doivent jamais apparaître en prod.
    return (
        Match.objects
        .filter(sofascore_id__isnull=False)
        .select_related('competition', 'domicile', 'exterieur', 'analyse', 'contexte')
        .prefetch_related(
            Prefetch(
                'analyse__options',
                queryset=Option.objects.filter(niveau__in=NIVEAUX_COMPOS).prefetch_related(
                    'votes_consensus',
                ),
            ),
        )
    )


def _match_detail_qs():
    return (
        Match.objects
        .filter(sofascore_id__isnull=False)
        .select_related(
            'competition', 'domicile', 'exterieur', 'analyse', 'contexte',
        )
        .prefetch_related('analyse__options__votes_consensus')
    )


def _filtrer_matchs(qs, params):
    code = params.get('competition')
    if code:
        qs = qs.filter(competition__code=code)
    pays = (params.get('pays') or '').strip()
    if pays:
        qs = qs.filter(competition__pays__iexact=pays)
    statut = params.get('statut')
    if statut:
        vals = [s.strip() for s in statut.split(',') if s.strip()]
        if len(vals) == 1:
            qs = qs.filter(statut=vals[0])
        elif vals:
            qs = qs.filter(statut__in=vals)
    depuis = params.get('depuis')
    if depuis:
        d = parse_date(depuis)
        if d:
            debut, _ = _fenetre_jour(d)
            qs = qs.filter(coup_denvoi__gte=debut)
    jusqu_a = params.get('jusqu_a')
    if jusqu_a:
        d = parse_date(jusqu_a)
        if d:
            _, fin = _fenetre_jour(d)
            qs = qs.filter(coup_denvoi__lte=fin)
    return qs


class CompetitionList(CacheETagMixin, APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        # Garantit les filtres Europe (UCL / UEL) même avant le prochain import.
        for code, nom, ordre in (
            ('UCL', 'Ligue des champions', 10),
            ('UEL', 'Ligue Europa', 11),
        ):
            Competition.objects.get_or_create(
                code=code,
                defaults={
                    'nom': nom,
                    'pays': 'Europe',
                    'ordre': ordre,
                    'actif': True,
                },
            )
        qs = Competition.objects.filter(actif=True)
        return Response(CompetitionSerializer(qs, many=True).data)


class MatchList(CacheETagMixin, APIView):
    permission_classes = [AllowAny]
    pagination_class = Pagination30
    cache_seconds = 60

    def get(self, request):
        from paris.engine_sync import declencher_refresh_async
        declencher_refresh_async()
        qs = _filtrer_matchs(_matchs_qs(), request.query_params)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        ser = MatchListeSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(ser.data)


class MatchDetail(CacheETagMixin, APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        match = get_object_or_404(_match_detail_qs(), pk=pk)
        return Response(MatchDetailSerializer(match, context={'request': request}).data)


class MatchResultat(APIView):
    """Saisie de score réservée au staff (évite falsification anonyme des tips)."""
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        match = get_object_or_404(Match, pk=pk)
        ser = ResultatSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        match.buts_dom = data['buts_dom']
        match.buts_ext = data['buts_ext']
        match.buts_dom_mt = data.get('buts_dom_mt')
        match.buts_ext_mt = data.get('buts_ext_mt')
        match.statut = 'termine'
        match.save()
        regler_match(match)
        match = Match.objects.select_related(
            'competition', 'domicile', 'exterieur', 'analyse', 'contexte',
        ).prefetch_related('analyse__options__votes_consensus').get(pk=match.pk)
        return Response(MatchDetailSerializer(match, context={'request': request}).data)


def _bloc_stats(options):
    n = len(options)
    gagnes = sum(1 for o in options if o.resultat == 'gagne')
    attendu = sum(o.probabilite for o in options) / n if n else None
    return {
        'n': n,
        'gagnes': gagnes,
        'taux': None if n < MIN_ECHANTILLON else (gagnes / n if n else None),
        'attendu': attendu,
        'echantillon_trop_petit': n < MIN_ECHANTILLON,
    }


def _options_reglees(params):
    qs = (
        Option.objects
        .filter(resultat__in=('gagne', 'perdu'))
        .select_related(
            'analyse__match__competition',
            'analyse__match__domicile',
            'analyse__match__exterieur',
        )
    )
    code = params.get('competition')
    if code:
        qs = qs.filter(analyse__match__competition__code=code)
    depuis = params.get('depuis')
    if depuis:
        d = parse_date(depuis)
        if d:
            debut, _ = _fenetre_jour(d)
            qs = qs.filter(analyse__match__coup_denvoi__gte=debut)
    jusqu_a = params.get('jusqu_a')
    if jusqu_a:
        d = parse_date(jusqu_a)
        if d:
            _, fin = _fenetre_jour(d)
            qs = qs.filter(analyse__match__coup_denvoi__lte=fin)
    niveau = params.get('niveau')
    if niveau:
        qs = qs.filter(niveau=niveau)
    return qs


class Verification(CacheETagMixin, APIView):
    permission_classes = [AllowAny]
    cache_seconds = 60

    def get(self, request):
        options = list(_options_reglees(request.query_params).exclude(
            niveau='detail',
        ))
        par_niveau = {}
        for niv in NIVEAUX_COMPOS:
            par_niveau[niv] = _bloc_stats([o for o in options if o.niveau == niv])
        familles = sorted({o.famille for o in options})
        par_famille = {
            fam: _bloc_stats([o for o in options if o.famille == fam])
            for fam in familles
        }
        return Response({
            'par_niveau': par_niveau,
            'par_famille': par_famille,
            'total_reglees': len(options),
        })


class VerificationDetail(CacheETagMixin, APIView):
    permission_classes = [AllowAny]
    cache_seconds = 60

    def get(self, request):
        qs = _options_reglees(request.query_params)
        niveau = request.query_params.get('niveau')
        if niveau:
            qs = qs.filter(niveau=niveau)
        else:
            qs = qs.filter(niveau__in=NIVEAUX_COMPOS)
        qs = qs.order_by('-analyse__match__coup_denvoi', 'niveau')
        lignes = []
        for o in qs[:400]:
            m = o.analyse.match
            lignes.append({
                'match_id': m.id,
                'libelle_match': f'{m.domicile.nom_court} – {m.exterieur.nom_court}',
                'competition': m.competition.code,
                'coup_denvoi': m.coup_denvoi,
                'option': o.libelle,
                'code': o.code,
                'famille': o.famille,
                'niveau': o.niveau,
                'probabilite': o.probabilite,
                'resultat': o.resultat,
            })
        return Response({'results': lignes})


class Info(CacheETagMixin, APIView):
    permission_classes = [AllowAny]
    cache_seconds = 30

    def get(self, request):
        from paris.engine_sync import declencher_refresh_async, etat_sync
        declencher_refresh_async()
        return Response({
            'version_moteur': VERSION_MOTEUR,
            'engine': etat_sync(),
            **_payload_auth(request.user),
            **_payload_vip_public(),
        })


class SyncEngine(APIView):
    """Tire le snapshot Engine (scores / statuts / bilans) vers la PWA."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        from paris.engine_sync import etat_sync
        return Response(etat_sync())

    def post(self, request):
        from paris.engine_sync import declencher_refresh_async, etat_sync, importer_engine
        force = str(request.data.get('force', '')).lower() in ('1', 'true', 'yes', 'on')
        # Auto : import en arrière-plan pour ne pas bloquer le premier paint PWA.
        if not force:
            declencher_refresh_async(force=False)
            return Response({
                'ok': True,
                'skipped': True,
                'reason': 'async',
                **etat_sync(),
            })
        result = importer_engine(force=True)
        status = 200 if result.get('ok') else 502
        return Response(result, status=status)


class Register(APIView):
    permission_classes = [AllowAny]
    # Pas de SessionAuthentication ici : évite un 403 CSRF au premier login PWA.
    authentication_classes = []

    def post(self, request):
        ser = AuthSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if User.objects.filter(username__iexact=data['username']).exists():
            return Response({'detail': 'Ce pseudo est déjà pris.'}, status=400)
        user = User(username=data['username'].strip(), email=data.get('email') or '')
        try:
            validate_password(data['password'], user=user)
        except DjangoValidationError as e:
            return Response({'detail': ' '.join(e.messages)}, status=400)
        user = User.objects.create_user(
            username=user.username,
            password=data['password'],
            email=data.get('email') or '',
        )
        Profil.objects.get_or_create(user=user, defaults={'categorie': 'membre'})
        login(request, user)
        from paris.analytics import enregistrer_trace
        enregistrer_trace('inscription', f'Nouveau compte · {user.username}', user=user, path='/api/v1/auth/register/')
        return Response(_payload_auth(user))


class Login(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        # Login insensible à la casse du pseudo.
        existing = User.objects.filter(username__iexact=data['username'].strip()).first()
        user = authenticate(
            request,
            username=existing.username if existing else data['username'].strip(),
            password=data['password'],
        )
        if user is None:
            return Response({'detail': 'Identifiants incorrects.'}, status=400)
        if not user.is_active:
            return Response({'detail': 'Compte désactivé.'}, status=400)
        login(request, user)
        from paris.analytics import enregistrer_trace
        enregistrer_trace('connexion', f'Connexion · {user.username}', user=user, path='/api/v1/auth/login/')
        return Response(_payload_auth(user))


class Logout(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        logout(request)
        return Response({'authentifie': False, 'username': None, 'categorie': 'visiteur', 'est_vip': False, 'est_premium': False, 'est_admin': False})


class ChatListCreate(APIView):
    """Salon Premium : réservé aux comptes Premium, purge 24 h."""
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        if not est_vip(request.user):
            return Response(
                {'detail': 'Salon Premium réservé aux comptes Premium.', 'code': 'vip_required'},
                status=403,
            )
        purger_messages_expires()
        qs = messages_actifs()
        since = request.query_params.get('since')
        if since:
            try:
                ts = datetime.fromisoformat(since.replace('Z', '+00:00'))
                if timezone.is_naive(ts):
                    ts = timezone.make_aware(ts, dt_timezone.utc)
                qs = qs.filter(created_at__gt=ts)
            except (TypeError, ValueError):
                pass
        msgs = list(qs.order_by('created_at')[:200])
        marquer_en_ligne(request.user.id)
        return Response({
            'results': MessageChatSerializer(msgs, many=True, context={'request': request}).data,
            'retention_heures': 24,
            'en_ligne': compter_en_ligne(),
            'server_time': timezone.now().isoformat(),
        })

    def post(self, request):
        if not est_vip(request.user):
            return Response(
                {'detail': 'Salon Premium réservé aux comptes Premium.', 'code': 'vip_required'},
                status=403,
            )
        purger_messages_expires()
        ser = MessageCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        msg = MessageChat.objects.create(
            auteur=request.user,
            texte=ser.validated_data.get('texte') or '',
            image=ser.validated_data.get('image'),
        )
        marquer_en_ligne(request.user.id)
        from paris.analytics import enregistrer_trace
        enregistrer_trace(
            'chat',
            f'Message salon · {request.user.username}',
            user=request.user,
            detail=(msg.texte or '[média]')[:120],
            path='/api/v1/salon/',
        )
        return Response(
            MessageChatSerializer(msg, context={'request': request}).data,
            status=201,
        )


class SalonAccueil(APIView):
    """Consomme le flag d’atterrissage Salon après activation Premium."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from paris.salon_welcome import consommer_accueil_salon
        return Response({'ok': True, 'consomme': consommer_accueil_salon(request.user)})


def _propositions_qs(match):
    return (
        PropositionParis.objects
        .filter(match=match)
        .select_related('auteur')
        .annotate(
            likes=Count('votes', filter=Q(votes__choix='like')),
            dislikes=Count('votes', filter=Q(votes__choix='dislike')),
        )
    )


def _consensus_propositions(match) -> dict:
    """Répartition des propositions utilisateurs par type d’option."""
    props = list(_propositions_qs(match))
    buckets = {
        code: {
            'type': code,
            'libelle': label,
            'n': 0,
            'confiance_sum': 0,
            'likes': 0,
            'dislikes': 0,
        }
        for code, label in TYPES_PROPOSITION.items()
    }
    for p in props:
        code = next(
            (c for c, label in TYPES_PROPOSITION.items() if p.libelle == label),
            None,
        )
        if not code:
            continue
        b = buckets[code]
        b['n'] += 1
        b['confiance_sum'] += int(p.confiance or 0)
        b['likes'] += int(getattr(p, 'likes', 0) or 0)
        b['dislikes'] += int(getattr(p, 'dislikes', 0) or 0)
    total = sum(b['n'] for b in buckets.values())
    par_option = []
    for b in buckets.values():
        if b['n'] == 0:
            continue
        votes = b['likes'] + b['dislikes']
        par_option.append({
            'type': b['type'],
            'libelle': b['libelle'],
            'n': b['n'],
            'pct': round(100 * b['n'] / total) if total else 0,
            'confiance_moy': round(b['confiance_sum'] / b['n']),
            'pct_likes': round(100 * b['likes'] / votes) if votes else None,
        })
    par_option.sort(key=lambda x: (-x['n'], -x['confiance_moy']))
    return {'total': total, 'par_option': par_option}


class PropositionListCreate(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request, pk):
        match = get_object_or_404(Match, pk=pk)
        qs = _propositions_qs(match)
        return Response({
            'results': PropositionSerializer(
                qs, many=True, context={'request': request},
            ).data,
            'consensus': _consensus_propositions(match),
        })

    def post(self, request, pk):
        match = get_object_or_404(Match, pk=pk)
        if match.statut not in ('a_venir', 'en_cours'):
            return Response(
                {'detail': 'Proposition possible uniquement avant la fin du match.'},
                status=400,
            )
        ser = PropositionCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        prop, created = PropositionParis.objects.update_or_create(
            match=match,
            auteur=request.user,
            defaults={
                'libelle': ser.to_libelle(),
                'confiance': ser.validated_data.get('confiance', 50),
            },
        )
        points_gagnes = 0
        if created:
            from paris.gamification import crediter_proposition
            points_gagnes = crediter_proposition(request.user)
            from paris.analytics import enregistrer_trace
            enregistrer_trace(
                'proposition',
                f'Proposition · {request.user.username}',
                user=request.user,
                detail=prop.libelle[:120],
                path=f'/api/v1/matchs/{pk}/propositions/',
            )
        prop = _propositions_qs(match).get(pk=prop.pk)
        return Response(
            {
                **PropositionSerializer(prop, context={'request': request}).data,
                'consensus': _consensus_propositions(match),
                'points_gagnes': points_gagnes,
            },
            status=201,
        )


class PropositionVote(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, prop_id):
        match = get_object_or_404(Match, pk=pk)
        prop = get_object_or_404(PropositionParis, pk=prop_id, match=match)
        ser = VoteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        Vote.objects.update_or_create(
            proposition=prop,
            user=request.user,
            defaults={'choix': ser.validated_data['choix']},
        )
        prop = _propositions_qs(match).get(pk=prop.pk)
        return Response(PropositionSerializer(prop, context={'request': request}).data)


class OptionVote(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, opt_id):
        match = get_object_or_404(Match, pk=pk)
        option = get_object_or_404(Option, pk=opt_id, analyse__match=match)
        ser = VoteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        VoteOption.objects.update_or_create(
            option=option,
            user=request.user,
            defaults={'choix': ser.validated_data['choix']},
        )
        option = Option.objects.prefetch_related('votes_consensus').get(pk=option.pk)
        from paris.serializers import OptionDetailSerializer
        return Response(OptionDetailSerializer(option, context={'request': request}).data)


def _tsdb_id(eq: Equipe) -> int | None:
    """Id TheSportsDB (secours logos / fiche club)."""
    from paris import thesportsdb as tsdb

    if eq.thesportsdb_id:
        return eq.thesportsdb_id
    found = tsdb.resoudre_id(eq.nom, eq.nom_court)
    if not found:
        return None
    if not Equipe.objects.filter(thesportsdb_id=found).exclude(pk=eq.pk).exists():
        eq.thesportsdb_id = found
        eq.save(update_fields=['thesportsdb_id'])
    return found


def _logo_bytes_externe(url: str) -> tuple[bytes, str] | None:
    """Télécharge un logo CDN déjà connu (ESPN, etc.)."""
    import urllib.error
    import urllib.request

    url = (url or '').strip()
    if not url.startswith(('http://', 'https://')):
        return None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Zanalyze/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read()
            ctype = (resp.headers.get('Content-Type') or 'image/png').split(';')[0]
            if body:
                return body, ctype
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    return None


def _infos_equipe_locale(eq: Equipe) -> dict:
    from paris.clubs import infos_equipe_locale
    return infos_equipe_locale(eq)


class EquipeLogo(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        from django.core.cache import cache
        from django.http import HttpResponse
        from paris import thesportsdb as tsdb
        from paris.clubs import logo_svg_placeholder

        eq = get_object_or_404(Equipe, pk=pk)
        cache_key = f'logo:v3:{eq.pk}'
        cached = cache.get(cache_key)
        if cached:
            body, ctype = cached
            resp = HttpResponse(body, content_type=ctype)
            resp['Cache-Control'] = 'public, max-age=86400'
            return resp

        body = None
        ctype = 'image/png'
        fetched = _logo_bytes_externe(eq.logo_externe or '')
        if fetched:
            body, ctype = fetched
        if body is None:
            tid = _tsdb_id(eq)
            if tid:
                try:
                    body, ctype = tsdb.logo_bytes(tid)
                except tsdb.SportsDbErreur:
                    body = None
        if body is None:
            body = logo_svg_placeholder(eq.nom, eq.nom_court)
            ctype = 'image/svg+xml'
            cache.set(cache_key, (body, ctype), 60 * 30)
        else:
            cache.set(cache_key, (body, ctype), 60 * 60 * 24)

        resp = HttpResponse(body, content_type=ctype)
        resp['Cache-Control'] = 'public, max-age=86400'
        return resp


class EquipeInfos(APIView):
    permission_classes = [AllowAny]
    cache_seconds = 600

    def get(self, request, pk):
        from django.conf import settings
        from paris import thesportsdb as tsdb

        eq = get_object_or_404(Equipe, pk=pk)
        local = _infos_equipe_locale(eq)
        data = None
        cached = dict(eq.fiche_club or {})
        # Sur hébergeurs sans egress : servir d’abord la fiche embarquée au snapshot.
        if cached.get('forme') or cached.get('recents') or cached.get('classement'):
            data = cached

        m = (
            Match.objects.filter(Q(domicile=eq) | Q(exterieur=eq))
            .select_related('competition')
            .order_by('-coup_denvoi')
            .first()
        )
        league_code = m.competition.code if m and m.competition_id else None
        sync_live = str(getattr(settings, 'ZANALYZ_SYNC_LIVE', '1')).lower() in (
            '1', 'true', 'yes', 'on',
        )

        # Enrichissement live optionnel (TheSportsDB) — jamais bloquant.
        # Les ids externes du snapshot sont ESPN (colonne legacy sofascore_id).
        live = None
        if sync_live:
            try:
                tsid = _tsdb_id(eq)
                if tsid:
                    live = tsdb.infos_equipe(tsid, league_code=league_code)
            except Exception:  # noqa: BLE001
                live = None
        if live is not None:
            data = live
            fiche = {
                k: live.get(k) for k in (
                    'nom', 'nom_court', 'pays', 'forme', 'position',
                    'classement', 'recents', 'note_moyenne',
                )
                if live.get(k) is not None
            }
            fiche['nom'] = eq.nom
            fiche['nom_court'] = eq.nom_court
            eq.fiche_club = fiche
            badge = (live.get('badge_url') or '').strip()
            updates = ['fiche_club']
            if badge and not eq.logo_externe:
                eq.logo_externe = badge
                updates.append('logo_externe')
            try:
                eq.save(update_fields=updates)
            except Exception:  # noqa: BLE001
                pass

        if data is None:
            data = local
        else:
            if len(data.get('recents') or []) < len(local.get('recents') or []):
                data['recents'] = local['recents']
                if len(data.get('forme') or []) < len(local.get('forme') or []):
                    data['forme'] = local['forme']
            if not data.get('pays') and local.get('pays'):
                data['pays'] = local['pays']

        data = dict(data or {})
        data.pop('source', None)
        data.pop('badge_url', None)
        data['equipe_id'] = eq.id
        data['nom_court'] = eq.nom_court or data.get('nom_court') or ''
        data['nom'] = eq.nom or data.get('nom') or ''
        data.setdefault('forme', [])
        data.setdefault('recents', [])
        data.setdefault('pays', local.get('pays'))
        return Response(data)


class PronosticMatch(APIView):
    """Pronostic 1X2 — tout compte connecté (pas les visiteurs)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        match = get_object_or_404(Match, pk=pk)
        if match.statut != 'a_venir':
            return Response({'detail': 'Pronostic possible uniquement avant le match.'}, status=400)
        if match.coup_denvoi and match.coup_denvoi <= timezone.now():
            return Response({'detail': 'Coup d’envoi déjà passé.'}, status=400)
        ser = PronosticCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        prono, _created = PronosticPremium.objects.update_or_create(
            match=match,
            user=request.user,
            defaults={'choix': ser.validated_data['choix'], 'points': None, 'gagne': None},
        )
        if _created:
            from paris.analytics import enregistrer_trace
            enregistrer_trace(
                'pronostic',
                f'Pronostic · {request.user.username}',
                user=request.user,
                detail=f'{match} → {prono.choix}',
                path=f'/api/v1/matchs/{pk}/pronostic/',
            )
        from paris.gamification import progression_utilisateur
        return Response({
            'choix': prono.choix,
            'points': prono.points,
            'gagne': prono.gagne,
            'progression': progression_utilisateur(request.user),
        })


class ClassementPremium(APIView):
    """Classement points — même catégorie (membre / premium) + progression."""
    permission_classes = [AllowAny]

    def get(self, request):
        from datetime import timedelta

        from django.db.models import Q
        from django.utils import timezone

        from paris.gamification import (
            appliquer_decay,
            categorie_classement,
            grade_pour,
            libelle_grade,
            progression_utilisateur,
        )

        now = timezone.now()
        cutoff = now - timedelta(days=1)
        stale = (
            Profil.objects
            .filter(points_premium__gt=0)
            .filter(Q(points_decay_le__isnull=True) | Q(points_decay_le__lte=cutoff))
            .select_related('user')
        )
        for profil in stale.iterator():
            appliquer_decay(profil)

        if request.user and request.user.is_authenticated:
            cat = categorie_classement(request.user)
        else:
            cat = 'membre'

        premium_q = (
            Q(user__is_staff=True)
            | Q(user__is_superuser=True)
            | (
                Q(categorie__in=['premium', 'vip'])
                & (Q(vip_expire_le__isnull=True) | Q(vip_expire_le__gt=now))
            )
        )
        qs = Profil.objects.filter(points_premium__gt=0).select_related('user')
        if cat == 'premium':
            qs = qs.filter(premium_q)
        else:
            qs = qs.exclude(premium_q)

        rows = qs.order_by('-points_premium', 'user__username')[:40]
        results = []
        for i, p in enumerate(rows, start=1):
            code = grade_pour(int(p.points_premium or 0))
            results.append({
                'rang': i,
                'username': p.user.username,
                'points': int(p.points_premium or 0),
                'grade': code,
                'grade_libelle': libelle_grade(code),
                'categorie': cat,
            })
        moi = None
        if request.user and request.user.is_authenticated:
            prog = progression_utilisateur(request.user)
            rang = next(
                (r['rang'] for r in results if r['username'] == request.user.username),
                None,
            )
            if rang is None and int(prog.get('points') or 0) >= 0:
                # Hors top 40 ou 0 pts : calcule le rang réel dans la catégorie.
                meilleurs = qs.filter(
                    points_premium__gt=int(prog.get('points') or 0),
                ).count()
                egaux = qs.filter(
                    points_premium=int(prog.get('points') or 0),
                    user__username__lt=request.user.username,
                ).count()
                rang = meilleurs + egaux + 1
            moi = {
                **prog,
                'username': request.user.username,
                'rang': rang,
                'est_premium': est_vip(request.user),
                'categorie_classement': cat,
                'libelle_categorie': 'Premium' if cat == 'premium' else 'Membres',
            }
        return Response({
            'results': results,
            'moi': moi,
            'categorie': cat,
            'libelle_categorie': 'Premium' if cat == 'premium' else 'Membres',
        })


@ensure_csrf_cookie
def app(request, *args, **kwargs):
    return render(request, 'app.html', {
        'version_moteur': VERSION_MOTEUR,
        'annee': datetime.now().year,
    })
