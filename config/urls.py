from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, JsonResponse
from django.urls import include, path, re_path

from paris import views
from paris.admin_auth import CaseInsensitiveAdminAuthForm

admin.site.site_header = 'Zanalyze'
admin.site.site_title = 'Zanalyze'
admin.site.index_title = 'Saisie et consultation'
admin.site.login_form = CaseInsensitiveAdminAuthForm


def health(_request):
    """Sonde Docker / load-balancer (pas d’auth)."""
    return JsonResponse({'status': 'ok', 'app': 'zanalyze'})


def service_worker(request):
    chemin = Path(settings.BASE_DIR) / 'static' / 'sw.js'
    resp = FileResponse(chemin.open('rb'), content_type='application/javascript')
    resp['Service-Worker-Allowed'] = '/'
    resp['Cache-Control'] = 'no-cache'
    return resp


def manifest(request):
    chemin = Path(settings.BASE_DIR) / 'static' / 'manifest.webmanifest'
    return FileResponse(chemin.open('rb'), content_type='application/manifest+json')


urlpatterns = [
    path('health/', health, name='health'),
    path('admin/', admin.site.urls),
    path('api/v1/', include('paris.urls')),
    path('sw.js', service_worker),
    path('manifest.webmanifest', manifest),
    path('', views.app, name='app'),
    re_path(r'^(?:matchs/\d+|historique|verification|salon|chat|reglages|jour)/?$', views.app),
]

# Media uploads (salon VIP, etc.) — requis en prod si le reverse-proxy
# ne mappe pas /media/ (ex. PythonAnywhere sans entrée « Static files »).
from django.views.static import serve as _media_serve

_media_prefix = (settings.MEDIA_URL or '/media/').lstrip('/')
urlpatterns += [
    re_path(
        rf'^{_media_prefix}(?P<path>.*)$',
        _media_serve,
        {'document_root': str(settings.MEDIA_ROOT)},
    ),
]
