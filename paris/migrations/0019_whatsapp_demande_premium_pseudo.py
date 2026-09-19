# Message WhatsApp Premium : branding Zanalyze + placeholder {pseudo}
# + nettoyage de l’ancien whatsapp_url figé (Cleared2Bet).

from django.db import migrations, models
import re

MSG_DEMANDE_PREMIUM = (
    'Bonjour, je suis {pseudo}, Zanalyste sur Zanalyze. '
    'Je souhaite devenir Premium.'
)


def _extraire_telephone(url, phone_actuel=''):
    phone = re.sub(r'\D', '', phone_actuel or '')
    if phone:
        return phone
    url = (url or '').strip()
    if not url:
        return ''
    m = re.search(r'(?:wa\.me|api\.whatsapp\.com/send\?phone=)/?(\d+)', url)
    if m:
        return m.group(1)
    m = re.search(r'phone=(\d+)', url)
    return m.group(1) if m else ''


def actualiser_reglage_whatsapp(apps, schema_editor):
    ReglageSite = apps.get_model('paris', 'ReglageSite')
    for r in ReglageSite.objects.all():
        champs = []

        msg = (r.whatsapp_message or '').strip()
        bas = msg.lower()
        if not msg or 'cleared2bet' in bas or '{pseudo}' not in msg:
            r.whatsapp_message = MSG_DEMANDE_PREMIUM
            champs.append('whatsapp_message')
        elif 'ZanalyZ' in msg:
            r.whatsapp_message = msg.replace('ZanalyZ', 'Zanalyze')
            champs.append('whatsapp_message')

        url = (r.whatsapp_url or '').strip()
        phone = _extraire_telephone(url, r.whatsapp_phone)
        if phone and not re.sub(r'\D', '', r.whatsapp_phone or ''):
            r.whatsapp_phone = phone
            champs.append('whatsapp_phone')

        # Ancien lien figé Cleared2Bet / texte embarqué → lien propre sans text=
        # (le message dynamique avec {pseudo} est reconstruit à la volée).
        if url:
            url_bas = url.lower()
            if 'cleared2bet' in url_bas or 'text=' in url_bas:
                r.whatsapp_url = f'https://wa.me/{phone}' if phone else ''
                champs.append('whatsapp_url')

        if champs:
            r.save(update_fields=list(dict.fromkeys(champs)))


class Migration(migrations.Migration):

    dependencies = [
        ('paris', '0018_accueil_salon'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reglagesite',
            name='whatsapp_message',
            field=models.CharField(
                blank=True,
                default=MSG_DEMANDE_PREMIUM,
                help_text=(
                    'Message prérempli WhatsApp. Utilise {pseudo} pour le nom du Zanalyste '
                    '(indispensable pour l’identifier en admin).'
                ),
                max_length=300,
            ),
        ),
        migrations.AlterField(
            model_name='reglagesite',
            name='whatsapp_url',
            field=models.URLField(
                blank=True,
                help_text=(
                    'Lien WhatsApp de secours (wa.me/NUMERO uniquement, sans text=). '
                    'Le message avec le pseudo du Zanalyste est reconstruit automatiquement.'
                ),
            ),
        ),
        migrations.RunPython(actualiser_reglage_whatsapp, migrations.RunPython.noop),
    ]
