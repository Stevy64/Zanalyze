const PEU_FIABLES = new Set(['BTTS', 'Une équipe marque']);
const LS_FILTRE = 'zanalyz.filtre';
const LS_MASQUEES = 'zanalyz.masquees';
const LS_REFRESH = 'zanalyz.refresh';
const LS_DATE = 'zanalyz.filtreDate';
const LS_SALON_READ = 'zanalyz.salon.lastReadAt';
const LS_MATCHS = 'zanalyz.matchs.cache';
const LS_FICHE_PREFIX = 'zanalyz.fiche.';
const SS_SCROLL = 'zanalyz.scroll';
const TZ_APP = 'Europe/Paris';

function csrf() {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

/** Date civile YYYY-MM-DD dans le fuseau de l’app (évite le décalage UTC). */
function dateLocaleISO(isoOrDate) {
  const d = isoOrDate instanceof Date ? isoOrDate : new Date(isoOrDate);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('en-CA', { timeZone: TZ_APP });
}

function fmtApiError(data, fallback) {
  if (!data) return fallback || 'Échec.';
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map(String).join(' ');
  const parts = [];
  Object.keys(data).forEach((k) => {
    const v = data[k];
    if (Array.isArray(v)) parts.push(v.join(' '));
    else if (typeof v === 'string') parts.push(v);
  });
  return parts.filter(Boolean).join(' ') || fallback || 'Échec.';
}

/** PDF texte multi-pages (Helvetica) — sans dépendance externe. */
function texteVersPdfBlob(titre, blocs) {
  const pdfSafe = (s) => String(s)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[\u2019\u2018]/g, "'")
    .replace(/[\u2013\u2014]/g, '-')
    .replace(/[^\x20-\x7E]/g, '?');
  const escapePdf = (s) => pdfSafe(s)
    .replace(/\\/g, '\\\\')
    .replace(/\(/g, '\\(')
    .replace(/\)/g, '\\)');
  const maxLen = 72;
  const wrap = (s) => {
    const out = [];
    let rest = pdfSafe(s);
    while (rest.length > maxLen) {
      let cut = rest.lastIndexOf(' ', maxLen);
      if (cut < 36) cut = maxLen;
      out.push(rest.slice(0, cut));
      rest = rest.slice(cut).trimStart();
    }
    if (rest) out.push(rest);
    return out.length ? out : [''];
  };

  const rows = [];
  const push = (line, style) => {
    wrap(line).forEach((w) => rows.push({ text: w, style: style || 'body' }));
  };
  push(titre, 'title');
  push('Prudent + Recommande + Securite', 'sub');
  push('------------------------------------------------', 'rule');
  blocs.forEach((b) => {
    push(b.header, 'match');
    (b.lines || []).forEach((l) => push('  ' + l, 'opt'));
    push('', 'gap');
  });
  push('Zanalyze', 'foot');

  const pageW = 595;
  const pageH = 842;
  const marginX = 48;
  const marginTop = 52;
  const marginBottom = 48;
  const lineH = {
    title: 20, sub: 14, rule: 12, match: 16, opt: 14, body: 13, gap: 8, foot: 12,
  };
  const fontSize = {
    title: 15, sub: 10, rule: 9, match: 11, opt: 10, body: 10, gap: 8, foot: 9,
  };

  const pages = [];
  let cur = [];
  let y = pageH - marginTop;
  rows.forEach((row) => {
    const h = lineH[row.style] || 13;
    if (y - h < marginBottom && cur.length) {
      pages.push(cur);
      cur = [];
      y = pageH - marginTop;
    }
    cur.push({ ...row, y });
    y -= h;
  });
  if (cur.length) pages.push(cur);

  const objects = [];
  objects.push(null);
  objects.push(null);
  const pageObjIds = [];
  const fontBoldId = 3;
  const fontRegId = 4;
  objects.push('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>');
  objects.push('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>');

  pages.forEach((pageRows) => {
    const ops = ['BT'];
    let prevY = null;
    pageRows.forEach((row) => {
      if (prevY == null) ops.push(`${marginX} ${row.y} Td`);
      else ops.push(`0 -${prevY - row.y} Td`);
      prevY = row.y;
      const size = fontSize[row.style] || 10;
      const font = (row.style === 'title' || row.style === 'match') ? '/F1' : '/F2';
      ops.push(`${font} ${size} Tf`);
      ops.push(`(${escapePdf(row.text)}) Tj`);
    });
    ops.push('ET');
    const stream = ops.join('\n');
    const contentId = objects.length + 1;
    objects.push(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
    const pageId = objects.length + 1;
    pageObjIds.push(pageId);
    objects.push(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageW} ${pageH}] `
      + `/Contents ${contentId} 0 R /Resources << /Font << /F1 ${fontBoldId} 0 R /F2 ${fontRegId} 0 R >> >> >>`,
    );
  });

  objects[0] = '<< /Type /Catalog /Pages 2 0 R >>';
  objects[1] = `<< /Type /Pages /Kids [${pageObjIds.map((id) => id + ' 0 R').join(' ')}] /Count ${pageObjIds.length} >>`;

  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  objects.forEach((body) => {
    offsets.push(pdf.length);
    pdf += `${offsets.length - 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n`;
  pdf += '0000000000 65535 f \n';
  for (let i = 1; i < offsets.length; i += 1) {
    pdf += `${String(offsets[i]).padStart(10, '0')} 00000 n \n`;
  }
  pdf += `trailer<< /Size ${objects.length + 1} /Root 1 0 R >>\n`;
  pdf += `startxref\n${xref}\n%%EOF`;
  return new Blob([pdf], { type: 'application/pdf' });
}

function fmtJour(iso) {
  return new Date(iso).toLocaleDateString('fr-FR', {
    weekday: 'long', day: 'numeric', month: 'long', timeZone: TZ_APP,
  });
}

function fmtCache(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', timeZone: TZ_APP })
    + ' à '
    + d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', timeZone: TZ_APP });
}

const ICON_PATHS = {
  home: '<path d="M4 10.5 12 3l8 7.5"/><path d="M6.5 9.5V20h11V9.5"/>',
  history: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  settings: '<path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"/><path d="M19.4 13a7.6 7.6 0 0 0 .05-1 7.6 7.6 0 0 0-.05-1l2.11-1.65a.5.5 0 0 0 .12-.64l-2-3.46a.5.5 0 0 0-.6-.22l-2.49 1a7.3 7.3 0 0 0-1.73-1L14.5 2.5a.5.5 0 0 0-.5-.5h-4a.5.5 0 0 0-.5.5l-.38 2.53a7.3 7.3 0 0 0-1.73 1l-2.49-1a.5.5 0 0 0-.6.22l-2 3.46a.5.5 0 0 0 .12.64L4.6 11a7.6 7.6 0 0 0-.05 1 7.6 7.6 0 0 0 .05 1l-2.11 1.65a.5.5 0 0 0-.12.64l2 3.46a.5.5 0 0 0 .6.22l2.49-1a7.3 7.3 0 0 0 1.73 1l.38 2.53a.5.5 0 0 0 .5.5h4a.5.5 0 0 0 .5-.5l.38-2.53a7.3 7.3 0 0 0 1.73-1l2.49 1a.5.5 0 0 0 .6-.22l2-3.46a.5.5 0 0 0-.12-.64L19.4 13z"/>',
  'thumbs-up': '<path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/>',
  'thumbs-down': '<path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"/>',
  arrow: '<path d="M5 12h12"/><path d="m13 6 6 6-6 6"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  check: '<path d="M5 12.5 9.5 17 19 7"/>',
  x: '<path d="M7 7l10 10M17 7 7 17"/>',
  trophy: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4z"/><path d="M7 6H5a2 2 0 0 0 0 4h2M17 6h2a2 2 0 0 1 0 4h-2"/>',
  shield: '<path d="M12 3 5 6v6c0 5 3.5 8.5 7 9.5 3.5-1 7-4.5 7-9.5V6l-7-3z"/>',
  crosshair: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1.6"/><path d="M19.5 4.5 14 10M19.5 4.5l-3.2.7M19.5 4.5l.7 3.2"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  'chevron-up': '<path d="m6 15 6-6 6 6"/>',
  layers: '<path d="m12 3 9 4.5-9 4.5L3 7.5 12 3z"/><path d="m3 12 9 4.5L21 12"/><path d="m3 16.5 9 4.5 9-4.5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 10v6M12 7h.01"/>',
  share: '<path d="M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7"/><path d="M16 6l-4-4-4 4"/><path d="M12 2v14"/>',
  download: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  'eye-off': '<path d="M3 3l18 18"/><path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"/><path d="M9.9 5.1A10.5 10.5 0 0 1 12 5c6.5 0 10 7 10 7a17.5 17.5 0 0 1-3.2 4.1"/><path d="M6.1 6.1C3.7 7.8 2 12 2 12a17.7 17.7 0 0 0 6.2 5.6"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  'badge-check': '<path d="M9 12.5 11 14.5 15.5 10"/><path d="M12 3 14.2 5.1l2.9-.4.9 2.8 2.6 1.4-1.4 2.6.4 2.9L16.9 15.5 15.5 18.4l-2.6-1.4L10.5 18.4 9.1 15.5 6.2 15.9l.4-2.9L5.2 10.4l2.6-1.4.9-2.8 2.9.4z"/>',
  crown: '<path d="M3 8l3.5 3L12 4l5.5 7L21 8v10H3V8z"/><path d="M3 18h18"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="3"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a3 3 0 0 1 0 5.74"/>',
  activity: '<path d="M3 12h3l2.5-6 4 12L16 9l2 3h3"/>',
  swords: '<path d="M14.5 17.5 3 6V3h3l11.5 11.5"/><path d="M13 19l6-6"/><path d="M16 16l3 3 2-2-3-3"/><path d="M9.5 6.5 21 18v3h-3L6.5 9.5"/><path d="M11 5 5 11"/><path d="M8 8 5 5 3 7l3 3"/>',
  'user-x': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="3"/><path d="m17 8 5 5M22 8l-5 5"/>',
  trending: '<path d="M3 17 9 11l4 4 8-8"/><path d="M14 7h7v7"/>',
  cloud: '<path d="M7 18h10a4 4 0 0 0 0-8 6 6 0 0 0-11.3-2A4.5 4.5 0 0 0 7 18z"/>',
  message: '<path d="M21 12a8 8 0 0 1-8 8H7l-4 3V12a8 8 0 1 1 18 0z"/>',
  send: '<path d="M4 12 20 4l-6 16-2-6-6-2z"/>',
  image: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10.5" r="1.5"/><path d="m21 15-5-5L5 21"/>',
  'log-out': '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>',
  flame: '<path d="M12 3c2 3 1 5-1 7 3 0 6 2 6 6a5 5 0 0 1-10 0c0-3 2-5 3-7-2 1-3 3-3 5a7 7 0 0 0 14 0c0-5-4-8-9-11z"/>',
  zap: '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z"/>',
  percent: '<circle cx="7.5" cy="7.5" r="2.5"/><circle cx="16.5" cy="16.5" r="2.5"/><path d="M18 6 6 18"/>',
  sparkles: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="m6.5 6.5 2.5 2.5M15 15l2.5 2.5M17.5 6.5 15 9M9 15l-2.5 2.5"/>',
};

function icon(name, cls) {
  const body = ICON_PATHS[name] || '';
  return (
    '<svg class="' + (cls || 'icon') + '" viewBox="0 0 24 24" fill="none" '
    + 'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" '
    + 'stroke-linejoin="round" aria-hidden="true">' + body + '</svg>'
  );
}

/** Drapeaux SVG (hors ligne) — code ligue ou pays. */
const FLAG_BY_CODE = {
  UCL: 'eu', UEL: 'uel',
  PL: 'gb', FAC: 'gb', EFL: 'gb',
  LIGA: 'es', CDR: 'es',
  BL: 'de', DFB: 'de',
  L1: 'fr', CDF: 'fr',
  SA: 'it', CI: 'it',
  LP: 'pt', TDP: 'pt',
};
const FLAG_BY_PAYS = {
  Europe: 'eu', Angleterre: 'gb', Espagne: 'es', Allemagne: 'de',
  France: 'fr', Italie: 'it', Portugal: 'pt',
};
const FLAG_SVG = {
  eu: (() => {
    const star = (a) => {
      const r = 7.4;
      const x = 18 + r * Math.cos((a - 90) * Math.PI / 180);
      const y = 18 + r * Math.sin((a - 90) * Math.PI / 180);
      return `<path fill="#FFCC00" transform="translate(${x.toFixed(2)} ${y.toFixed(2)}) scale(0.32)" d="M0-7.2 1.6-2.3h5.2l-4.2 3 1.6 4.9L0 2.6l-4.2 3 1.6-4.9-4.2-3h5.2z"/>`;
    };
    let stars = '';
    for (let i = 0; i < 12; i += 1) stars += star(i * 30);
    return '<rect width="36" height="36" fill="#003399"/>' + stars;
  })(),
  // Ligue Europa — orange (distinct de l’UCL bleue)
  uel: (() => {
    const star = (a) => {
      const r = 7.4;
      const x = 18 + r * Math.cos((a - 90) * Math.PI / 180);
      const y = 18 + r * Math.sin((a - 90) * Math.PI / 180);
      return `<path fill="#FFF8F0" transform="translate(${x.toFixed(2)} ${y.toFixed(2)}) scale(0.32)" d="M0-7.2 1.6-2.3h5.2l-4.2 3 1.6 4.9L0 2.6l-4.2 3 1.6-4.9-4.2-3h5.2z"/>`;
    };
    let stars = '';
    for (let i = 0; i < 12; i += 1) stars += star(i * 30);
    return '<rect width="36" height="36" fill="#E87722"/>' + stars;
  })(),
  gb: '<rect width="36" height="36" fill="#012169"/>'
    + '<path d="M0 0l36 36M36 0L0 36" stroke="#fff" stroke-width="7.2"/>'
    + '<path d="M0 0l36 36M36 0L0 36" stroke="#C8102E" stroke-width="4"/>'
    + '<path d="M18 0v36M0 18h36" stroke="#fff" stroke-width="12"/>'
    + '<path d="M18 0v36M0 18h36" stroke="#C8102E" stroke-width="7"/>',
  es: '<rect width="36" height="36" fill="#AA151B"/>'
    + '<rect y="9" width="36" height="18" fill="#F1BF00"/>'
    + '<rect x="8" y="13.5" width="5" height="9" rx=".6" fill="#AA151B" opacity=".85"/>',
  de: '<rect width="36" height="12" fill="#000"/>'
    + '<rect y="12" width="36" height="12" fill="#DD0000"/>'
    + '<rect y="24" width="36" height="12" fill="#FFCE00"/>',
  fr: '<rect width="12" height="36" fill="#002395"/>'
    + '<rect x="12" width="12" height="36" fill="#fff"/>'
    + '<rect x="24" width="12" height="36" fill="#ED2939"/>',
  it: '<rect width="12" height="36" fill="#009246"/>'
    + '<rect x="12" width="12" height="36" fill="#fff"/>'
    + '<rect x="24" width="12" height="36" fill="#CE2B37"/>',
  pt: '<rect width="36" height="36" fill="#FF0000"/>'
    + '<rect width="14.4" height="36" fill="#006600"/>'
    + '<circle cx="14.4" cy="18" r="5.2" fill="#FFCC00"/>'
    + '<circle cx="14.4" cy="18" r="3.2" fill="#FF0000"/>',
};

function flagKeyForComp(comp) {
  if (!comp) return '';
  const byCode = FLAG_BY_CODE[String(comp.code || '').toUpperCase()];
  if (byCode) return byCode;
  return FLAG_BY_PAYS[comp.pays] || '';
}

function drapeauComp(comp, cls) {
  const key = flagKeyForComp(comp);
  const body = FLAG_SVG[key];
  if (!body) {
    return '<span class="' + (cls || 'flag') + ' flag-empty" aria-hidden="true"></span>';
  }
  return (
    '<svg class="' + (cls || 'flag') + '" viewBox="0 0 36 36" role="img" '
    + 'aria-label="' + esc(comp.pays || comp.code || '') + '" focusable="false">'
    + body + '</svg>'
  );
}

function drapeauPays(pays, cls) {
  const key = FLAG_BY_PAYS[pays];
  const body = key ? FLAG_SVG[key] : '';
  if (!body) {
    return '<span class="' + (cls || 'flag') + ' flag-empty" aria-hidden="true"></span>';
  }
  return (
    '<svg class="' + (cls || 'flag') + '" viewBox="0 0 36 36" role="img" '
    + 'aria-label="' + esc(pays) + '" focusable="false">' + body + '</svg>'
  );
}

const ORDRE_PAYS_FILTRE = [
  'Angleterre', 'Espagne', 'Allemagne', 'France', 'Italie', 'Portugal',
];

function parseFiltre(filtre) {
  if (!filtre) return { mode: 'all' };
  if (String(filtre).startsWith('pays:')) {
    return { mode: 'pays', pays: filtre.slice(5) };
  }
  return { mode: 'comp', code: filtre };
}

function matchFiltreCompetition(m, filtre) {
  const f = parseFiltre(filtre);
  if (f.mode === 'all') return true;
  if (!m || !m.competition) return false;
  if (f.mode === 'comp') return m.competition.code === f.code;
  if (f.mode === 'pays') return m.competition.pays === f.pays;
  return true;
}

function estNavigateurHorsLigne() {
  return typeof navigator !== 'undefined' && navigator.onLine === false;
}

async function getJSON(url, { timeoutMs = 10000 } = {}) {
  const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timer = ctrl ? setTimeout(() => ctrl.abort(), timeoutMs) : null;
  try {
    const res = await fetch(url, {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
      signal: ctrl ? ctrl.signal : undefined,
    });
    if (timer) clearTimeout(timer);
    const fromCache = res.headers.get('X-SW-Cache') === '1';
    const data = await res.json().catch(() => null);
    return { data, fromCache, ok: res.ok, status: res.status, offline: false };
  } catch (err) {
    if (timer) clearTimeout(timer);
    // Timeout / 5xx SW / serveur lent ≠ hors ligne. Seulement navigator.onLine.
    return {
      data: null,
      fromCache: false,
      ok: false,
      status: 0,
      offline: estNavigateurHorsLigne(),
      aborted: !!(err && err.name === 'AbortError'),
    };
  }
}

function lireCacheMatchs(cle) {
  try {
    const raw = localStorage.getItem(LS_MATCHS);
    if (!raw) return null;
    const bag = JSON.parse(raw);
    const entry = bag && bag[cle];
    if (!entry || !Array.isArray(entry.results)) return null;
    return entry;
  } catch (_) {
    return null;
  }
}

/** Dernière liste matchs en cache (clé exacte ou plus récente). */
function lireCacheMatchsFlexible(cle) {
  const exact = lireCacheMatchs(cle);
  if (exact && exact.results && exact.results.length) return exact;
  try {
    const bag = JSON.parse(localStorage.getItem(LS_MATCHS) || '{}') || {};
    let best = null;
    for (const entry of Object.values(bag)) {
      if (!entry || !Array.isArray(entry.results) || !entry.results.length) continue;
      if (!best || String(entry.savedAt || '') > String(best.savedAt || '')) best = entry;
    }
    return best;
  } catch (_) {
    return null;
  }
}

function ecrireCacheMatchs(cle, results) {
  try {
    let bag = {};
    try { bag = JSON.parse(localStorage.getItem(LS_MATCHS) || '{}') || {}; } catch (_) { bag = {}; }
    bag[cle] = { results, savedAt: new Date().toISOString() };
    // Garde les 8 dernières clés pour limiter la taille.
    const keys = Object.keys(bag);
    if (keys.length > 8) {
      keys.sort((a, b) => String((bag[a] && bag[a].savedAt) || '').localeCompare(String((bag[b] && bag[b].savedAt) || '')));
      keys.slice(0, keys.length - 8).forEach((k) => { delete bag[k]; });
    }
    localStorage.setItem(LS_MATCHS, JSON.stringify(bag));
  } catch (_) { /* quota / private mode */ }
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

const CRESTS = {
  psg: ['#004170', '#DA291C'],
  bayern: ['#DC052D', '#0066B2'],
  'real-madrid': ['#FEBE10', '#00529F'],
  'man-city': ['#6CABDD', '#1C2C5B'],
  liverpool: ['#C8102E', '#00B2A9'],
  arsenal: ['#EF0107', '#063672'],
  'man-utd': ['#DA291C', '#FBE122'],
  everton: ['#003399', '#FFFFFF'],
  barcelone: ['#A50044', '#004D98'],
  girona: ['#CD2534', '#FFFFFF'],
  om: ['#2FAEE0', '#FFFFFF'],
  monaco: ['#E31C23', '#FFFFFF'],
  lille: ['#E01A22', '#1D1D1B'],
  nice: ['#ED1C24', '#000000'],
  inter: ['#010E80', '#000000'],
  napoli: ['#12A0D7', '#FFFFFF'],
  como: ['#1B3A6B', '#C9A227'],
  genoa: ['#AD1919', '#0B2C5F'],
};

function hashHue(s) {
  let h = 0;
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h % 360;
}

function crestSvg(eq, size = 42) {
  if (!eq) return '';
  const slug = eq.slug || '';
  const letters = esc((eq.nom_court || eq.nom || '?').slice(0, 3).toUpperCase());
  const pair = CRESTS[slug];
  const hue = hashHue(slug || letters);
  const a = pair ? pair[0] : `hsl(${hue} 58% 28%)`;
  const b = pair ? pair[1] : `hsl(${(hue + 42) % 360} 62% 40%)`;
  const fs = size < 50 ? 11 : 16;
  return `<svg class="crest" viewBox="0 0 64 64" width="${size}" height="${size}" role="img" aria-hidden="true">
    <path fill="${a}" stroke="#fff" stroke-width="2.5"
      d="M32 4 L54 12 V30 C54 46 44 56 32 60 C20 56 10 46 10 30 V12 Z"/>
    <circle cx="46" cy="16" r="7" fill="${b}" opacity="0.95"/>
    <text x="32" y="38" text-anchor="middle" fill="#fff" font-size="${fs}"
      font-weight="800" font-family="ui-rounded,Segoe UI,sans-serif">${letters}</text>
  </svg>`;
}

const TYPES_PROPOSITION = [
  { code: 'vainqueur_dom', label: 'Vainqueur domicile' },
  { code: 'nul', label: 'Match nul' },
  { code: 'vainqueur_ext', label: 'Vainqueur extérieur' },
  { code: 'plus_25', label: 'Plus de 2,5 buts' },
  { code: 'moins_25', label: 'Moins de 2,5 buts' },
];

function zanalyz() {
  return {
    page: 'matchs',
    titrePage: 'Matchs',
    get kickerPage() {
      return {
        fiche: 'Analyse',
        salon: 'Salon Premium',
        reglages: 'Compte',
      }[this.page] || '';
    },
    crestSvg,
    icon,
    drapeauComp,
    drapeauPays,
    fmtJour,
    TYPES_PROPOSITION,
    logoUrl(eq) {
      if (!eq) return '';
      // Préfère une URL CDN (navigateur) — le proxy serveur échoue souvent hors whitelist.
      if (eq.logo_url) return eq.logo_url;
      if (eq.id) return '/api/v1/equipes/' + eq.id + '/logo/';
      return '';
    },
    moteur: document.body.dataset.moteur,
    chargement: false,
    competitions: [],
    competitionsAll: [],
    matchs: [],
    matchsPasses: [],
    filtre: localStorage.getItem(LS_FILTRE) || '',
    filtreDate: (() => {
      const auj = dateLocaleISO(new Date());
      const saved = localStorage.getItem(LS_DATE) || '';
      // Garde les dates passées récentes (bilans) ; oublie seulement > 21 jours.
      if (saved && saved < auj) {
        const lim = new Date();
        lim.setDate(lim.getDate() - 21);
        const limIso = dateLocaleISO(lim);
        if (saved < limIso) {
          localStorage.removeItem(LS_DATE);
          return '';
        }
      }
      return saved;
    })(),
    masquees: JSON.parse(localStorage.getItem(LS_MASQUEES) || '[]'),
    navDir: 'forward',
    fiche: null,
    verif: null,
    verifDetail: [],
    vDepuis: '',
    vJusqua: '',
    vNiveau: '',
    vComp: '',
    chatMessages: [],
    chatDraft: '',
    chatBusy: false,
    chatChargement: false,
    chatErr: '',
    chatSince: null,
    chatImage: null,
    chatImagePreview: '',
    chatLightboxUrl: '',
    _chatPoll: null,
    _chatStickBottom: true,
    estVip: false,
    estAdmin: false,
    pointsPremium: 0,
    gradePremium: 'mougou',
    authShowPass: false,
    whatsappVipUrl: '',
    vipTarifLibelle: 'Premium Zanalyze',
    sheetVip: false,
    horsLigne: false,
    engineMeta: null,
    syncBusy: false,
    dernierRafraichissement: localStorage.getItem(LS_REFRESH) ? fmtCache(localStorage.getItem(LS_REFRESH)) : '',
    swWaiting: false,
    _swReg: null,
    _ptrY: null,
    cachePurge: false,
    _matchReq: 0,
    authentifie: false,
    username: null,
    categorie: 'visiteur',
    authUser: '',
    authPass: '',
    authMode: 'login',
    authErr: '',
    propositions: [],
    propConsensus: null,
    propType: 'plus_25',
    propConfiance: 60,
    propErr: '',
    voteErr: '',
    _voteBusy: null,
    optOuverte: null,
    chatEnLigne: 0,
    chatUnread: 0,
    _unreadPoll: null,
    panelChances: false,
    panelContexte: false,
    tabHidden: false,
    _lastScrollY: 0,
    sheetApercu: false,
    apercu: null,
    apercuChargement: false,
    apercuErr: '',
    sheetClub: false,
    clubInfos: null,
    clubChargement: false,
    clubEq: null,
    sheetAuth: false,
    authMotif: '',
    authPending: null,
    authBusy: false,
    sheetCompos: false,
    composExpanded: false,
    _composDragY: null,
    sheetJustif: false,
    justif: null,
    sheetCgu: false,
    authAcceptCgu: false,
    jourDate: '',
    predictionsJour: [],
    chargementJour: false,
    partageMsg: '',
    partageBusy: false,
    jourPasseCompos: false,
    classement: [],
    classementMoi: null,
    classementChargement: false,
    _progression: null,
    sheetClassement: false,
    salonOnglet: 'chat',
    pronoBusy: false,
    pronoMsg: '',
    peutInstaller: false,
    installePWA: false,
    installHint: '',
    installIOS: false,
    sheetInstall: false,
    _deferredInstall: null,

    async init() {
      this.lireRoute();
      if (!this.jourDate) this.jourDate = this.filtreDate || dateLocaleISO(new Date());
      window.addEventListener('popstate', () => this.lireRoute({ pop: true }));
      window.addEventListener('scroll', () => this.onScroll(), { passive: true });
      window.addEventListener('online', () => {
        this.horsLigne = false;
        this.rafraichirDonnees(false);
      });
      window.addEventListener('offline', () => {
        if (estNavigateurHorsLigne()) this.horsLigne = true;
      });
      // Corrige un faux « hors ligne » laissé par un ancien onglet / SW.
      if (!estNavigateurHorsLigne()) this.horsLigne = false;
      this.ecouterInstallPWA();
      this.enregistrerSW();
      await this.chargerInfo();
      // Import snapshot en arrière-plan : ne doit jamais bloquer le premier affichage.
      this.syncEngine(false).then((r) => {
        if (r && r.ok && !r.skipped && this.page === 'matchs') {
          this.chargerMatchs({ forceNetwork: true });
        }
      }).catch(() => {});
      await this.chargerCompetitions();
      await this.routeData();
      this.demarrerUnreadPoll();
      if (this._ouvrirComposAuDemarrage) {
        this._ouvrirComposAuDemarrage = false;
        await this.ouvrirCompos();
      }
    },

    onScroll() {
      const y = window.scrollY || 0;
      const dy = y - this._lastScrollY;
      if (y < 24) this.tabHidden = false;
      else if (dy > 8) this.tabHidden = true;
      else if (dy < -8) this.tabHidden = false;
      this._lastScrollY = y;
    },

    get estVisiteur() {
      return this.categorie === 'visiteur' || !this.authentifie;
    },
    get peutVoter() {
      return this.authentifie && (this.categorie === 'membre' || this.categorie === 'premium' || this.estVip);
    },
    get peutCompos() {
      return this.peutVip;
    },
    get peutVip() {
      return this.authentifie && (this.categorie === 'premium' || this.estVip);
    },
    get peutBilanComplet() {
      return !!this.estAdmin || !!this.peutVip;
    },
    get peutProno() {
      return this.authentifie && !this.estVisiteur;
    },
    get progression() {
      return this.classementMoi || this._progression || null;
    },
    get libCategorie() {
      return {
        visiteur: 'Visiteur',
        membre: 'Membre',
        premium: 'Premium',
        vip: 'Premium',
      }[this.categorie] || 'Visiteur';
    },
    iconCategorie(cat) {
      const c = cat || this.categorie || 'visiteur';
      const name = { visiteur: 'eye', membre: 'badge-check', vip: 'crown', premium: 'crown' }[c] || 'eye';
      return icon(name, 'icon icon-sm');
    },
    iconGrade(code) {
      const name = {
        mougou: 'eye',
        zanalyste: 'badge-check',
        ndoss: 'zap',
        boss: 'crown',
        rookie: 'eye',
        analyste: 'badge-check',
        stratege: 'zap',
        oracle: 'crown',
      }[code || this.gradePremium] || 'badge-check';
      return icon(name, 'icon icon-sm');
    },

    async chargerInfo() {
      try {
        const { data, offline, ok } = await getJSON('/api/v1/info/', { timeoutMs: 10000 });
        if (offline && estNavigateurHorsLigne()) {
          this.horsLigne = true;
          return;
        }
        if (!ok || !data) return;
        this.horsLigne = false;
        this.authentifie = !!(data && data.authentifie);
        this.username = data && data.username;
        this.categorie = (data && data.categorie) || (this.authentifie ? 'membre' : 'visiteur');
        this.estVip = !!(data && (data.est_premium || data.est_vip)) || this.categorie === 'premium';
        this.estAdmin = !!(data && data.est_admin);
        this.pointsPremium = (data && data.points_premium) || 0;
        this.gradePremium = (data && data.grade_premium) || 'mougou';
        this._progression = (data && data.progression) || null;
        if (this._progression) this.classementMoi = this._progression;
        this.whatsappVipUrl = (data && data.whatsapp_vip_url) || '';
        this.vipTarifLibelle = (data && data.vip_tarif_libelle) || 'Premium Zanalyze';
        if (data && data.version_moteur) this.moteur = data.version_moteur;
        if (data && data.engine) this.engineMeta = data.engine;
        this.demarrerUnreadPoll();
      } catch (_) { /* hors ligne */ }
    },

    async syncEngine(force = false) {
      if (this.syncBusy || estNavigateurHorsLigne()) {
        return { ok: false, skipped: true };
      }
      this.syncBusy = true;
      const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
      // force : un peu plus long ; sinon court pour ne pas figer l’UI.
      const timeoutMs = force ? 20000 : 8000;
      const timer = ctrl ? setTimeout(() => ctrl.abort(), timeoutMs) : null;
      try {
        const res = await fetch('/api/v1/sync/engine/', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
            'X-CSRFToken': csrf(),
          },
          body: JSON.stringify({ force: !!force }),
          signal: ctrl ? ctrl.signal : undefined,
        });
        if (timer) clearTimeout(timer);
        const data = await res.json().catch(() => ({}));
        if (data && (data.exporte_le || data.importe_le)) this.engineMeta = data;
        return data || { ok: res.ok };
      } catch (_) {
        if (timer) clearTimeout(timer);
        // Timeout / réseau : ne pas forcer le mode hors-ligne (les matchs peuvent déjà être là).
        return { ok: false, reason: 'offline' };
      } finally {
        this.syncBusy = false;
      }
    },

    async rafraichirDonnees(force = true) {
      await this.syncEngine(force);
      if (this.page === 'matchs') await this.chargerMatchs({ forceNetwork: true });
      else if (this.page === 'fiche' && this._matchId) await this.chargerFiche(this._matchId);
      else await this.routeData();
    },

    lireRoute(opts = {}) {
      if (opts.pop) this.navDir = 'back';
      const path = location.pathname.replace(/\/$/, '') || '/';
      const m = path.match(/^\/matchs\/(\d+)$/);
      this.stopChatPoll();
      if (m) {
        this.page = 'fiche';
        this.titrePage = 'Match';
        this._matchId = m[1];
      } else if (path === '/historique' || path === '/verification') {
        this.page = 'salon';
        this.titrePage = 'Salon';
        history.replaceState({}, '', '/salon');
      } else if (path === '/salon' || path === '/chat') {
        this.page = 'salon';
        this.titrePage = 'Salon';
        if (path === '/chat') history.replaceState({}, '', '/salon');
      } else if (path === '/jour') {
        // Ancienne route → accueil + sheet compos
        this.page = 'matchs';
        this.titrePage = 'Matchs';
        history.replaceState({}, '', '/');
        this._ouvrirComposAuDemarrage = true;
      } else if (path === '/reglages') {
        this.page = 'reglages';
        this.titrePage = 'Réglages';
      } else {
        this.page = 'matchs';
        this.titrePage = 'Matchs';
      }
      if (opts.pop) this.routeData();
    },

    go(path) {
      this.navDir = 'forward';
      if (this.page === 'matchs') {
        sessionStorage.setItem(SS_SCROLL, String(window.scrollY));
      }
      history.pushState({}, '', path);
      this.lireRoute();
      this.routeData();
    },

    retourListe() {
      this.navDir = 'back';
      if (history.length > 1) history.back();
      else this.go('/');
    },

    ouvrirMatch(id) {
      this.sheetClub = false;
      this.sheetApercu = false;
      this.sheetAuth = false;
      this.sheetCompos = false;
      this.sheetInstall = false;
      this.sheetJustif = false;
      this.sheetVip = false;
      this.justif = null;
      this.authPending = null;
      this.apercu = null;
      this.clubInfos = null;
      this.clubEq = null;
      document.body.classList.remove('sheet-open');
      this.go('/matchs/' + id);
    },

    async ouvrirApercu(id) {
      this.sheetClub = false;
      this.sheetCompos = false;
      this.sheetApercu = true;
      this.apercu = null;
      this.apercuErr = '';
      this.apercuChargement = true;
      document.body.classList.add('sheet-open');
      const { data, ok } = await getJSON('/api/v1/matchs/' + id + '/');
      this.apercuChargement = false;
      if (ok) this.apercu = data;
      else this.apercuErr = 'Détails indisponibles pour le moment. Réessaie.';
    },

    ouvrirApercuFromCard(id, ev) {
      if (ev && ev.target && ev.target.closest('button, a, .vote-row, .no-apercu, .carte-pied, .crest-btn')) return;
      this.ouvrirApercu(id);
    },

    fermerSheets() {
      if (this.chatLightboxUrl) {
        this.fermerChatImage();
        return;
      }
      if (this.sheetCgu) {
        this.fermerCgu();
        return;
      }
      if (this.sheetVip) {
        this.fermerVipGate();
        return;
      }
      if (this.sheetJustif) {
        this.fermerJustif();
        return;
      }
      if (this.sheetInstall) {
        this.sheetInstall = false;
        if (!this.sheetApercu && !this.sheetAuth && !this.sheetClub && !this.sheetCompos && !this.sheetCgu) {
          document.body.classList.remove('sheet-open');
        }
        return;
      }
      if (this.sheetAuth) {
        this.sheetAuth = false;
        this.authPending = null;
        this.authErr = '';
        if (!this.sheetApercu && !this.sheetClub && !this.sheetCompos && !this.sheetInstall && !this.sheetCgu) {
          document.body.classList.remove('sheet-open');
        }
        return;
      }
      if (this.sheetClub) {
        this.sheetClub = false;
        this.clubInfos = null;
        this.clubEq = null;
        if (!this.sheetApercu && !this.sheetAuth && !this.sheetCompos && !this.sheetInstall && !this.sheetCgu) {
          document.body.classList.remove('sheet-open');
        }
        return;
      }
      if (this.sheetCompos) {
        this.sheetCompos = false;
        this.composExpanded = false;
        this.partageMsg = '';
        this.sheetJustif = false;
        this.justif = null;
        if (!this.sheetApercu && !this.sheetAuth && !this.sheetClub && !this.sheetInstall && !this.sheetCgu && !this.sheetClassement) {
          document.body.classList.remove('sheet-open');
        }
        return;
      }
      if (this.sheetClassement) {
        this.sheetClassement = false;
        if (!this.sheetApercu && !this.sheetAuth && !this.sheetClub && !this.sheetCompos && !this.sheetInstall && !this.sheetCgu) {
          document.body.classList.remove('sheet-open');
        }
        return;
      }
      this.sheetApercu = false;
      this.apercu = null;
      this.apercuErr = '';
      document.body.classList.remove('sheet-open');
    },

    ouvrirJustif(bloc, option) {
      if (!option) return;
      if (!this.peutVip) {
        this.ouvrirVipGate('justif');
        return;
      }
      const j = option.justification || {};
      if (!j.accroche && !(j.arguments && j.arguments.length) && !(j.points && j.points.length)) {
        this.ouvrirVipGate('justif');
        return;
      }
      const args = Array.isArray(j.arguments) && j.arguments.length
        ? j.arguments
        : (Array.isArray(j.points) ? j.points.map((texte, i) => ({
          cle: 'p' + i,
          titre: 'Point clé',
          texte,
          icon: 'info',
        })) : []);
      this.justif = {
        titre: j.titre || ((option.niveau || '') + ' · ' + (option.libelle || '')),
        libelle: j.libelle || option.libelle || '',
        accroche: j.accroche || '',
        arguments: args,
        points: Array.isArray(j.points) ? j.points : args.map((a) => a.texte),
        matchLabel: bloc
          ? ((bloc.domicile && bloc.domicile.nom_court) || '') +
            ' – ' +
            ((bloc.exterieur && bloc.exterieur.nom_court) || '')
          : '',
        niveau: option.niveau || j.niveau,
        probabilite: option.probabilite != null ? option.probabilite : j.probabilite,
        domicile: bloc && bloc.domicile,
        exterieur: bloc && bloc.exterieur,
      };
      this.sheetJustif = true;
      document.body.classList.add('sheet-open');
    },

    ouvrirVipGate(motif) {
      if (!this.authentifie) {
        this.ouvrirAuth(
          'Connecte-toi ou crée un compte pour demander Premium via WhatsApp.',
          () => this.ouvrirVipGate(motif),
        );
        return;
      }
      this.sheetVip = true;
      document.body.classList.add('sheet-open');
      if (!this.whatsappVipUrl) this.chargerInfo();
    },

    fermerVipGate() {
      this.sheetVip = false;
      if (!this.sheetCompos && !this.sheetApercu && !this.sheetAuth && !this.sheetClub && !this.sheetInstall && !this.sheetJustif && !this.sheetCgu) {
        document.body.classList.remove('sheet-open');
      }
    },

    fermerJustif() {
      this.sheetJustif = false;
      this.justif = null;
      if (!this.sheetCompos && !this.sheetApercu && !this.sheetAuth && !this.sheetClub && !this.sheetInstall && !this.sheetCgu) {
        document.body.classList.remove('sheet-open');
      }
    },

    ouvrirCgu() {
      this.sheetCgu = true;
      document.body.classList.add('sheet-open');
    },

    fermerCgu() {
      this.sheetCgu = false;
      if (!this.sheetJustif && !this.sheetCompos && !this.sheetApercu && !this.sheetAuth && !this.sheetClub && !this.sheetInstall && !this.sheetVip) {
        document.body.classList.remove('sheet-open');
      }
    },

    ouvrirAuth(motif, pending) {
      this.authMotif = motif || 'Connecte-toi pour continuer.';
      this.authPending = typeof pending === 'function' ? pending : null;
      this.authErr = '';
      this.authMode = 'login';
      this.sheetAuth = true;
      this.voteErr = '';
      document.body.classList.add('sheet-open');
    },

    exigerAuth(motif, pending) {
      if (this.authentifie) return true;
      this.ouvrirAuth(motif, pending);
      return false;
    },

    async ouvrirClub(eq, ev) {
      if (ev) ev.stopPropagation();
      if (!eq || !eq.id) return;
      this.clubEq = eq;
      this.sheetClub = true;
      this.clubInfos = {
        equipe_id: eq.id,
        nom: eq.nom || eq.nom_court || '',
        nom_court: eq.nom_court || '',
        forme: [],
        recents: [],
      };
      this.clubChargement = true;
      document.body.classList.add('sheet-open');
      try {
        const { data, ok } = await getJSON('/api/v1/equipes/' + eq.id + '/infos/');
        if (ok && data) this.clubInfos = data;
      } catch (_) { /* garde le squelette local */ }
      this.clubChargement = false;
    },

    sheetDragStart(ev) {
      const t = ev.touches && ev.touches[0];
      if (!t) return;
      const sheet = ev.currentTarget && ev.currentTarget.closest
        ? ev.currentTarget.closest('.bottom-sheet')
        : null;
      this._sheetDrag = { y0: t.clientY, dy: 0, sheet };
    },

    sheetDragMove(ev) {
      if (!this._sheetDrag) return;
      const t = ev.touches && ev.touches[0];
      if (!t) return;
      const dy = Math.max(0, t.clientY - this._sheetDrag.y0);
      this._sheetDrag.dy = dy;
      const el = this._sheetDrag.sheet;
      if (el && dy > 0) {
        el.style.transition = 'none';
        el.style.transform = 'translateY(' + dy + 'px)';
      }
    },

    sheetDragEnd() {
      if (!this._sheetDrag) return;
      const { dy, sheet } = this._sheetDrag;
      this._sheetDrag = null;
      if (sheet) {
        sheet.style.transition = '';
        sheet.style.transform = '';
      }
      if (dy > 72) this.fermerSheets();
    },

    estMatchPasse(m) {
      if (!m) return false;
      if (m.statut === 'termine') return true;
      const auj = this.dateAujourdhui();
      return dateLocaleISO(m.coup_denvoi) < auj;
    },

    libResultatTip(o) {
      if (!o) return '';
      if (o.resultat === 'gagne') return 'OK';
      if (o.resultat === 'perdu') return 'KO';
      if (o.resultat === 'annule') return 'Annulé';
      return 'En attente';
    },

    bilanResume(fiche) {
      const opts = this.optionsApercu(fiche);
      if (!opts.length) return null;
      let ok = 0;
      let ko = 0;
      let attente = 0;
      for (const o of opts) {
        if (o.resultat === 'gagne') ok += 1;
        else if (o.resultat === 'perdu') ko += 1;
        else attente += 1;
      }
      return { ok, ko, attente, total: opts.length };
    },

    optionsApercu(fiche) {
      if (!fiche || !fiche.analyse) return [];
      const ordre = { prudente: 0, recommandee: 1, equilibree: 2, audacieuse: 3, filet: 4 };
      let opts = (fiche.analyse.options || []).filter((o) => o.niveau in ordre);
      if (fiche.statut === 'termine' && !this.peutBilanComplet) {
        opts = opts.filter((o) => o.niveau === 'prudente' || o.niveau === 'filet');
      }
      return opts.sort((a, b) => ordre[a.niveau] - ordre[b.niveau]);
    },

    onLogoError(ev) {
      const img = ev.target;
      if (!img || img.dataset.fallback === '1') return;
      img.dataset.fallback = '1';
      img.style.display = 'none';
      const fallback = img.nextElementSibling;
      if (fallback) {
        fallback.style.display = 'grid';
        fallback.classList.add('show');
      }
    },

    async routeData() {
      if (this.page === 'matchs') {
        await this.chargerMatchs();
        this.$nextTick(() => {
          const y = sessionStorage.getItem(SS_SCROLL);
          if (y) window.scrollTo(0, parseInt(y, 10) || 0);
        });
      } else if (this.page === 'fiche') {
        window.scrollTo(0, 0);
        await this.chargerFiche(this._matchId);
        await this.chargerPropositions(this._matchId);
        this.optOuverte = null;
        this.panelChances = false;
        this.panelContexte = false;
        this.voteErr = '';
        this.propType = 'plus_25';
        this.propErr = '';
      } else if (this.page === 'salon') {
        await this.ouvrirSalon();
      } else if (this.page === 'reglages') {
        await this.chargerInfo();
        if (this.authentifie) await this.chargerClassement();
      }
    },

    noterCache(fromCache) {
      if (!fromCache) {
        const now = new Date().toISOString();
        localStorage.setItem(LS_REFRESH, now);
        this.dernierRafraichissement = fmtCache(now);
      }
    },

    async chargerCompetitions() {
      const { data } = await getJSON('/api/v1/competitions/');
      const list = (data || []).slice().sort((a, b) => {
        const oa = Number(a.ordre ?? 100);
        const ob = Number(b.ordre ?? 100);
        if (oa !== ob) return oa - ob;
        return String(a.nom || '').localeCompare(String(b.nom || ''), 'fr');
      });
      this.competitionsAll = list;
      this.competitions = list.filter((c) => !this.masquees.includes(c.code));
    },

    async chargerMatchs(opts = {}) {
      const token = ++this._matchReq;
      const filtreActif = this.filtre;
      const garderListe = this.matchs && this.matchs.length;
      const q = new URLSearchParams();
      const auj = this.dateAujourdhui();
      const dateCible = this.filtreDate || auj;
      const jourUnique = !!this.filtreDate;
      const inclureTermines = dateCible <= auj;
      q.set(
        'statut',
        inclureTermines ? 'termine,en_cours,a_venir,reporte' : 'a_venir,en_cours',
      );
      // Assez large pour une journée complète (bilans + à venir) ou un pays.
      q.set('page_size', '100');
      const apiComp = this.filtreApiCompetition();
      if (apiComp) q.set('competition', apiComp);
      const apiPays = this.filtreApiPays();
      if (apiPays) q.set('pays', apiPays);
      q.set('depuis', dateCible);
      if (jourUnique) q.set('jusqu_a', this.filtreDate);
      const cacheKey = q.toString() + '|f=' + (filtreActif || '');

      const cachedExact = lireCacheMatchs(cacheKey);
      if (cachedExact && cachedExact.results.length) {
        this.matchs = cachedExact.results;
        this.chargement = false;
      } else {
        this.chargement = !garderListe;
      }

      try {
        const { data, fromCache, offline, ok } = await getJSON(
          '/api/v1/matchs/?' + q.toString(),
          { timeoutMs: 12000 },
        );
        if (token !== this._matchReq) return;
        if (offline || !ok || !data) {
          if (offline && estNavigateurHorsLigne()) this.horsLigne = true;
          // Jamais de cache « flexible » si une date est choisie (évite Hier ≠ matchs affichés).
          const cached = this.filtreDate
            ? lireCacheMatchs(cacheKey)
            : (lireCacheMatchs(cacheKey) || lireCacheMatchsFlexible(cacheKey));
          if (cached && cached.results.length) {
            this.matchs = cached.results;
          } else if (!garderListe && !(this.matchs && this.matchs.length)) {
            this.matchs = [];
          }
          return;
        }
        this.horsLigne = false;
        this.noterCache(fromCache);
        let list = (data && data.results) || [];
        if (filtreActif) {
          list = list.filter((m) => matchFiltreCompetition(m, filtreActif));
        }
        if (this.filtreDate) {
          list = list.filter((m) => dateLocaleISO(m.coup_denvoi) === this.filtreDate);
        } else {
          list = list.filter((m) => {
            const d = dateLocaleISO(m.coup_denvoi);
            if (m.statut === 'termine') return d === auj;
            if (m.statut === 'a_venir' || m.statut === 'en_cours') return d >= auj;
            return false;
          });
        }
        list.sort((a, b) => new Date(a.coup_denvoi) - new Date(b.coup_denvoi));
        this.matchs = list;
        ecrireCacheMatchs(cacheKey, list);
      } catch (_) {
        if (token !== this._matchReq) return;
        if (!garderListe && !(this.matchs && this.matchs.length)) this.matchs = [];
      } finally {
        if (token === this._matchReq) this.chargement = false;
      }
    },

    async chargerMatchsPasses() {
      const q = new URLSearchParams();
      q.set('statut', 'termine');
      q.set('page_size', '60');
      if (this.vComp) q.set('competition', this.vComp);
      if (this.vDepuis) q.set('depuis', this.vDepuis);
      if (this.vJusqua) q.set('jusqu_a', this.vJusqua);
      const { data } = await getJSON('/api/v1/matchs/?' + q.toString());
      let list = (data && data.results) || [];
      list = list.filter((m) => m.statut === 'termine' && this.tipsHisto(m).length);
      list.sort((a, b) => new Date(b.coup_denvoi) - new Date(a.coup_denvoi));
      this.matchsPasses = list;
    },

    tipsHisto(m) {
      const ordre = { prudente: 0, recommandee: 1, filet: 2, equilibree: 3, audacieuse: 4 };
      const raw = (m.options && m.options.length)
        ? m.options
        : ((m.analyse && m.analyse.options) || []);
      let opts = raw.filter((o) => o.niveau in ordre);
      // Non-admin : uniquement prudent + sécurité sur les matchs passés.
      if (m.statut === 'termine' && !this.peutBilanComplet) {
        opts = opts.filter((o) => o.niveau === 'prudente' || o.niveau === 'filet');
      }
      return opts.sort((a, b) => (ordre[a.niveau] ?? 9) - (ordre[b.niveau] ?? 9));
    },

    get matchsHistoFiltres() {
      if (!this.vNiveau) return this.matchsPasses;
      return this.matchsPasses.filter((m) =>
        this.tipsHisto(m).some((o) => o.niveau === this.vNiveau)
      );
    },

    async chargerFiche(id) {
      this.chargement = !this.fiche;
      try {
        const { data, fromCache, offline, ok } = await getJSON('/api/v1/matchs/' + id + '/');
        if (offline || !ok || !data) {
          if (offline && estNavigateurHorsLigne()) this.horsLigne = true;
          try {
            const raw = localStorage.getItem(LS_FICHE_PREFIX + id);
            if (raw) {
              this.fiche = JSON.parse(raw);
            }
          } catch (_) { /* ignore */ }
          return;
        }
        this.horsLigne = false;
        this.noterCache(fromCache);
        this.fiche = data;
        try {
          localStorage.setItem(LS_FICHE_PREFIX + id, JSON.stringify(data));
        } catch (_) { /* quota */ }
      } finally {
        this.chargement = false;
      }
    },

    async chargerVerif() {
      this.chargement = true;
      const q = new URLSearchParams();
      if (this.vDepuis) q.set('depuis', this.vDepuis);
      if (this.vJusqua) q.set('jusqu_a', this.vJusqua);
      if (this.vComp) q.set('competition', this.vComp);
      const { data } = await getJSON('/api/v1/historique/?' + q.toString());
      this.verif = data;
      this.chargement = false;
    },

    async chargerVerifDetail() {
      const q = new URLSearchParams();
      if (this.vDepuis) q.set('depuis', this.vDepuis);
      if (this.vJusqua) q.set('jusqu_a', this.vJusqua);
      if (this.vNiveau) q.set('niveau', this.vNiveau);
      if (this.vComp) q.set('competition', this.vComp);
      const { data } = await getJSON('/api/v1/historique/detail/?' + q.toString());
      this.verifDetail = (data && data.results) || [];
    },

    rechargerVerif() {
      this.chargerVerif();
      this.chargerMatchsPasses();
    },

    setVerifComp(code) {
      this.vComp = code;
      this.rechargerVerif();
    },

    setVerifNiv(niv) {
      this.vNiveau = niv;
    },

    setFiltre(code) {
      this.filtre = code || '';
      localStorage.setItem(LS_FILTRE, this.filtre);
      this.matchs = [];
      this.chargerMatchs();
    },

    setFiltrePays(pays) {
      const cle = 'pays:' + pays;
      if (this.filtre === cle) this.setFiltre('');
      else this.setFiltre(cle);
    },

    filtreApiCompetition() {
      const f = parseFiltre(this.filtre);
      return f.mode === 'comp' ? f.code : '';
    },

    filtreApiPays() {
      const f = parseFiltre(this.filtre);
      return f.mode === 'pays' ? f.pays : '';
    },

    filtrePaysSelectionne() {
      const f = parseFiltre(this.filtre);
      if (f.mode === 'pays') return f.pays;
      if (f.mode === 'comp') {
        const c = this.competitions.find((x) => x.code === f.code);
        return (c && c.pays) || '';
      }
      return '';
    },

    isFiltrePaysActif(pays) {
      return this.filtrePaysSelectionne() === pays;
    },

    get filtresPrincipaux() {
      const comps = this.competitions || [];
      const out = [];
      const europeCodes = ['UCL', 'UEL'];
      for (const code of europeCodes) {
        const comp = comps.find((c) => c.code === code);
        if (comp) out.push({ kind: 'europe', comp });
      }
      const byPays = new Map();
      for (const c of comps) {
        if (europeCodes.includes(c.code)) continue;
        const pays = c.pays || 'Autre';
        if (!byPays.has(pays)) byPays.set(pays, []);
        byPays.get(pays).push(c);
      }
      const sortedPays = [...byPays.keys()].sort((a, b) => {
        const ia = ORDRE_PAYS_FILTRE.indexOf(a);
        const ib = ORDRE_PAYS_FILTRE.indexOf(b);
        if (ia >= 0 && ib >= 0) return ia - ib;
        if (ia >= 0) return -1;
        if (ib >= 0) return 1;
        return String(a).localeCompare(String(b), 'fr');
      });
      for (const pays of sortedPays) {
        const list = byPays.get(pays).slice().sort(
          (a, b) => (Number(a.ordre) || 100) - (Number(b.ordre) || 100),
        );
        out.push({ kind: 'pays', pays, comps: list });
      }
      return out;
    },

    get sousFiltresComp() {
      const pays = this.filtrePaysSelectionne();
      if (!pays) return [];
      return this.competitions.filter((c) => c.pays === pays);
    },

    setFiltreDate(val) {
      this.filtreDate = val || '';
      if (this.filtreDate) localStorage.setItem(LS_DATE, this.filtreDate);
      else localStorage.removeItem(LS_DATE);
      this.matchs = [];
      this.chargerMatchs();
    },

    dateAujourdhui() {
      return dateLocaleISO(new Date());
    },

    dateHier() {
      const auj = this.dateAujourdhui();
      const parts = auj.split('-').map(Number);
      if (parts.length !== 3 || parts.some((n) => Number.isNaN(n))) return auj;
      const [y, m, d] = parts;
      const utc = new Date(Date.UTC(y, m - 1, d));
      utc.setUTCDate(utc.getUTCDate() - 1);
      return utc.toISOString().slice(0, 10);
    },

    allerAccueil() {
      this.go('/');
    },

    sortirSalon() {
      this.stopChatPoll();
      this.go('/');
    },

    libSalonEnLigne() {
      const n = Math.max(1, Number(this.chatEnLigne) || 1);
      if (n <= 1) return 'Vous êtes seul en ligne';
      return 'Vous êtes ' + n + ' en ligne';
    },

    toggleComp(code) {
      const i = this.masquees.indexOf(code);
      if (i >= 0) this.masquees.splice(i, 1);
      else this.masquees.push(code);
      localStorage.setItem(LS_MASQUEES, JSON.stringify(this.masquees));
      this.competitions = this.competitionsAll.filter((c) => !this.masquees.includes(c.code));
    },

    get competitionsParPays() {
      const map = new Map();
      for (const c of this.competitionsAll) {
        const pays = c.pays || 'Autre';
        if (!map.has(pays)) map.set(pays, []);
        map.get(pays).push(c);
      }
      return [...map.entries()].map(([pays, comps]) => ({
        pays,
        comps,
        flagHtml: drapeauComp(comps[0]),
      }));
    },

    get groupes() {
      const map = new Map();
      for (const m of this.matchs) {
        const cle = dateLocaleISO(m.coup_denvoi);
        if (!cle) continue;
        if (!map.has(cle)) map.set(cle, { cle, label: fmtJour(m.coup_denvoi), matchs: [] });
        map.get(cle).matchs.push(m);
      }
      return [...map.values()];
    },

    prudente(m) {
      return (m.options || []).find((o) => o.niveau === 'prudente');
    },

    get recoFiche() {
      if (!this.fiche || !this.fiche.analyse) return [];
      const ordre = { prudente: 0, recommandee: 1, equilibree: 2, audacieuse: 3, filet: 4 };
      let opts = this.fiche.analyse.options.filter((o) => o.niveau in ordre);
      if (this.fiche.statut === 'termine' && !this.peutBilanComplet && this.fiche.bilan_complet === false) {
        opts = opts.filter((o) => o.niveau === 'prudente' || o.niveau === 'filet');
      }
      return opts.sort((a, b) => ordre[a.niveau] - ordre[b.niveau]);
    },

    get filetFiche() {
      if (!this.fiche || !this.fiche.analyse) return null;
      return this.fiche.analyse.options.find((o) => o.niveau === 'filet') || null;
    },

    get sectionsChances() {
      if (!this.fiche || !this.fiche.analyse) return [];
      const opts = this.fiche.analyse.options;
      const qui = ['1X2', 'Double chance', 'Handicap'];
      const buts = ['Total buts', 'BTTS', 'Une équipe marque'];
      const ht = ['Mi-temps'];
      const pick = (fams) => opts.filter((o) => fams.includes(o.famille));
      return [
        { titre: 'Qui gagne', items: pick(qui) },
        { titre: 'Les buts', items: pick(buts) },
        { titre: 'La mi-temps', items: pick(ht) },
      ];
    },

    peuFiable(fam) { return PEU_FIABLES.has(fam); },
    initiales(nom) {
      const p = String(nom || '').trim().split(/\s+/);
      if (!p[0]) return '?';
      if (p.length === 1) return p[0].slice(0, 2).toUpperCase();
      return (p[0][0] + p[1][0]).toUpperCase();
    },
    heure(iso) {
      return new Date(iso).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
    },
    jourCourt(iso) {
      return new Date(iso).toLocaleDateString('fr-FR', {
        weekday: 'short', day: 'numeric', month: 'short',
      });
    },
    dateHeure(iso) {
      return fmtJour(iso) + ' · ' + this.heure(iso);
    },
    sur100(p) { return Math.round(Number(p) * 100); },
    fmtPct(p) {
      if (p == null || Number.isNaN(Number(p))) return '—';
      return Math.round(Number(p) * 100) + ' %';
    },
    fmtCote(c) { return Number(c).toFixed(2).replace('.', ','); },
    libNiveau(n) {
      return {
        prudente: 'Prudent',
        recommandee: 'Recommandé',
        equilibree: 'Équilibrée',
        audacieuse: 'Audacieuse',
        filet: 'Sécurité',
      }[n] || n;
    },
    libProfil(p) {
      return { equilibre: 'équilibré', moyen: 'moyen', desequilibre: 'déséquilibré' }[p] || p;
    },
    iconeResultat(r) {
      if (r === 'gagne') return '✓';
      if (r === 'perdu') return '✕';
      return '·';
    },
    iconResultat(r) {
      if (r === 'gagne') return icon('check', 'icon icon-sm');
      if (r === 'perdu') return icon('x', 'icon icon-sm');
      return '';
    },
    motResultat(r) {
      return { gagne: 'Gagné', perdu: 'Perdu', attente: 'En attente', annule: 'Annulé' }[r] || r;
    },
    libGrade(code) {
      return {
        mougou: 'Mougou',
        zanalyste: 'Zanalyste',
        ndoss: 'Ndoss',
        boss: 'Boss',
        // anciens codes (compat affichage)
        rookie: 'Mougou',
        analyste: 'Zanalyste',
        stratege: 'Ndoss',
        oracle: 'Boss',
      }[code] || 'Mougou';
    },
    async poserPronostic(choix) {
      if (!this.fiche || this.fiche.statut !== 'a_venir') return;
      if (!this.peutProno) {
        this.ouvrirAuth('Crée un compte pour poser ton pronostic 1X2 et gagner des points.');
        return;
      }
      this.pronoBusy = true;
      this.pronoMsg = '';
      try {
        const res = await fetch('/api/v1/matchs/' + this.fiche.id + '/pronostic/', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
            'X-CSRFToken': csrf(),
          },
          body: JSON.stringify({ choix }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
          this.fiche.mon_pronostic = data;
          if (data.progression) {
            this._progression = data.progression;
            this.classementMoi = data.progression;
            this.pointsPremium = data.progression.points;
            this.gradePremium = data.progression.grade;
          }
          this.pronoMsg = 'Pronostic enregistré — +'
            + ((data.progression && data.progression.gains && data.progression.gains.prono_ko) || 2)
            + ' à +'
            + ((data.progression && data.progression.gains && data.progression.gains.prono_ok) || 12)
            + ' pts après le match.';
        } else {
          this.pronoMsg = data.detail || 'Impossible d’enregistrer le pronostic.';
        }
      } finally {
        this.pronoBusy = false;
      }
    },
    async chargerClassement() {
      this.classementChargement = true;
      const { data, ok } = await getJSON('/api/v1/classement/');
      this.classementChargement = false;
      if (!ok) return;
      this.classement = (data && data.results) || [];
      this.classementMoi = (data && data.moi) || null;
      if (this.classementMoi) {
        this._progression = this.classementMoi;
        this.pointsPremium = this.classementMoi.points;
        this.gradePremium = this.classementMoi.grade;
      }
    },
    async ouvrirClassement() {
      if (!this.authentifie) {
        this.ouvrirAuth('Connecte-toi pour voir ton challenge et le classement.');
        return;
      }
      this.sheetApercu = false;
      this.sheetClub = false;
      this.sheetCompos = false;
      this.sheetClassement = true;
      document.body.classList.add('sheet-open');
      await this.chargerClassement();
    },
    fmtConsensus(o) {
      if (!o || o.pct_likes == null) return '—';
      return o.pct_likes + ' %';
    },
    toneProb(p) {
      const n = Number(p) * 100;
      if (Number.isNaN(n)) return '';
      if (n >= 70) return 'tone-ok';
      if (n >= 55) return 'tone-mid';
      return 'tone-hot';
    },
    toneConsensus(o) {
      if (!o || o.pct_likes == null) return '';
      const pred = Math.round(Number(o.probabilite) * 100);
      const diff = Math.abs(o.pct_likes - pred);
      if (diff <= 10) return 'tone-ok';
      if (diff <= 25) return 'tone-mid';
      return 'tone-hot';
    },
    expliquerNiveau(n) {
      return {
        prudente: 'Niveau Prudent : forte probabilité (70–90 %). Priorité à la stabilité.',
        recommandee: 'Niveau Recommandé : même famille que le tip prudent, probabilité la plus élevée hors tip principale.',
        equilibree: 'Niveau Équilibrée : double chance 1X ou X2, selon la probabilité la plus élevée.',
        audacieuse: 'Niveau Audacieuse : plus risqué (28–50 %). À manier avec une mise réduite.',
        filet: 'Niveau Sécurité : repli sûr si le tip principal rate.',
      }[n] || '';
    },
    toggleOpt(id) {
      this.optOuverte = this.optOuverte === id ? null : id;
      this.voteErr = '';
    },
    fmtTaux(bloc) {
      if (!bloc || !bloc.n) return '—';
      const t = bloc.taux != null ? bloc.taux : (bloc.gagnes / bloc.n);
      return Math.round(t * 100) + ' %';
    },
    largeurJauge(bloc) {
      if (!bloc || !bloc.n) return 0;
      const t = bloc.taux != null ? bloc.taux : (bloc.gagnes / bloc.n);
      return Math.round(t * 100);
    },
    get famillesVerif() {
      return this.verif ? Object.keys(this.verif.par_famille) : [];
    },

    ptrStart(e) { this._ptrY = e.touches[0].clientY; },
    ptrEnd(e) {
      if (this._ptrY == null) return;
      const dy = e.changedTouches[0].clientY - this._ptrY;
      this._ptrY = null;
      if (window.scrollY < 8 && dy > 60) this.rafraichirDonnees(true);
    },

    async chargerPropositions(id) {
      const { data } = await getJSON('/api/v1/matchs/' + id + '/propositions/');
      this.propositions = (data && data.results) || [];
      this.propConsensus = (data && data.consensus) || null;
    },

    async proposerParis() {
      this.propErr = '';
      if (!this.exigerAuth('Connecte-toi pour proposer un pari.', () => this.proposerParis())) {
        return;
      }
      if (!this.propType) {
        this.propErr = 'Choisis un type de pari.';
        return;
      }
      const res = await fetch('/api/v1/matchs/' + this.fiche.id + '/propositions/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'X-CSRFToken': csrf(),
        },
        body: JSON.stringify({
          type: this.propType,
          confiance: this.propConfiance,
        }),
      });
      if (res.ok) {
        const data = await res.json().catch(() => ({}));
        await this.chargerPropositions(this.fiche.id);
        this.propErr = '';
        if (data.points_gagnes) {
          await this.chargerInfo();
          this.propErr = '';
          this.pronoMsg = '+' + data.points_gagnes + ' pts pour ta proposition !';
        }
      } else {
        const err = await res.json().catch(() => ({}));
        this.propErr = fmtApiError(err, 'Publication impossible.');
      }
    },

    async voter(propId, choix) {
      if (!this.exigerAuth('Connecte-toi pour voter sur cette proposition.', () => this.voter(propId, choix))) {
        return;
      }
      const res = await fetch(
        '/api/v1/matchs/' + this.fiche.id + '/propositions/' + propId + '/vote/',
        {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
            'X-CSRFToken': csrf(),
          },
          body: JSON.stringify({ choix }),
        },
      );
      if (res.ok) {
        const updated = await res.json();
        this.propositions = this.propositions.map((p) => (
          p.id === updated.id ? updated : p
        ));
        await this.chargerPropositions(this.fiche.id);
      }
    },

    appliquerVoteOption(matchId, updated) {
      const patchOpts = (opts) => {
        if (!opts) return;
        const o = opts.find((x) => x.id === updated.id);
        if (!o) return;
        o.likes = updated.likes;
        o.dislikes = updated.dislikes;
        o.pct_likes = updated.pct_likes;
        o.mon_vote = updated.mon_vote;
      };
      const m = this.matchs.find((x) => x.id === matchId);
      if (m) patchOpts(m.options);
      if (this.fiche && this.fiche.id === matchId && this.fiche.analyse) {
        patchOpts(this.fiche.analyse.options);
      }
      if (this.apercu && this.apercu.id === matchId && this.apercu.analyse) {
        patchOpts(this.apercu.analyse.options);
      }
    },

    async voterOption(matchId, optId, choix, ev) {
      if (ev) ev.stopPropagation();
      if (!matchId || !optId) return;
      const lock = matchId + ':' + optId;
      if (this._voteBusy === lock) return;
      this.voteErr = '';
      if (!this.exigerAuth(
        'Connecte-toi pour voter sur cette prédiction.',
        () => this.voterOption(matchId, optId, choix),
      )) {
        return;
      }
      this._voteBusy = lock;
      // Optimistic : bascule immédiate, rollback si l’API échoue.
      const prev = this._snapshotVote(matchId, optId);
      this._optimisticVote(matchId, optId, choix);
      try {
        const res = await fetch(
          '/api/v1/matchs/' + matchId + '/options/' + optId + '/vote/',
          {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrf(),
            },
            body: JSON.stringify({ choix }),
          },
        );
        if (res.ok) {
          const updated = await res.json();
          this.appliquerVoteOption(matchId, updated);
        } else {
          if (prev) this.appliquerVoteOption(matchId, prev);
          this.voteErr = res.status === 403
            ? 'Connecte-toi pour voter.'
            : 'Vote impossible.';
        }
      } catch (_) {
        if (prev) this.appliquerVoteOption(matchId, prev);
        this.voteErr = 'Réseau indisponible.';
      } finally {
        if (this._voteBusy === lock) this._voteBusy = null;
      }
    },

    _findOption(matchId, optId) {
      const from = (opts) => (opts || []).find((o) => o.id === optId) || null;
      if (this.fiche && this.fiche.id === matchId && this.fiche.analyse) {
        const o = from(this.fiche.analyse.options);
        if (o) return o;
      }
      if (this.apercu && this.apercu.id === matchId && this.apercu.analyse) {
        const o = from(this.apercu.analyse.options);
        if (o) return o;
      }
      const m = this.matchs.find((x) => x.id === matchId);
      return m ? from(m.options) : null;
    },

    _snapshotVote(matchId, optId) {
      const o = this._findOption(matchId, optId);
      if (!o) return null;
      return {
        id: o.id,
        likes: o.likes,
        dislikes: o.dislikes,
        pct_likes: o.pct_likes,
        mon_vote: o.mon_vote,
      };
    },

    _optimisticVote(matchId, optId, choix) {
      const o = this._findOption(matchId, optId);
      if (!o) return;
      let likes = Number(o.likes) || 0;
      let dislikes = Number(o.dislikes) || 0;
      if (o.mon_vote === 'like') likes = Math.max(0, likes - 1);
      if (o.mon_vote === 'dislike') dislikes = Math.max(0, dislikes - 1);
      if (choix === 'like') likes += 1;
      else if (choix === 'dislike') dislikes += 1;
      const total = likes + dislikes;
      this.appliquerVoteOption(matchId, {
        id: optId,
        likes,
        dislikes,
        pct_likes: total ? Math.round(100 * likes / total) : null,
        mon_vote: choix,
      });
    },

    async authSubmit() {
      this.authErr = '';
      const user = (this.authUser || '').trim();
      const pass = this.authPass || '';
      if (user.length < 3) {
        this.authErr = 'Pseudo trop court (3 caractères min.).';
        return;
      }
      if (pass.length < 8) {
        this.authErr = 'Mot de passe trop court (8 caractères min.).';
        return;
      }
      if (this.authMode === 'register' && !this.authAcceptCgu) {
        this.authErr = 'Tu dois accepter les conditions d’utilisation pour créer un compte.';
        return;
      }
      this.authBusy = true;
      const url = this.authMode === 'register'
        ? '/api/v1/auth/register/'
        : '/api/v1/auth/login/';
      try {
        const res = await fetch(url, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
            'X-CSRFToken': csrf(),
          },
          body: JSON.stringify({ username: user, password: pass }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
          this.authentifie = true;
          this.username = data.username;
          this.categorie = data.categorie || 'membre';
          this.estVip = !!(data.est_premium || data.est_vip) || this.categorie === 'premium';
          this.estAdmin = !!(data.est_admin);
          this.authPass = '';
          this.authErr = '';
          this.authAcceptCgu = false;
          const pending = this.authPending;
          this.sheetAuth = false;
          this.authPending = null;
          if (!this.sheetApercu && !this.sheetClub && !this.sheetCompos) {
            document.body.classList.remove('sheet-open');
          }
          await this.chargerInfo();
          this.demarrerUnreadPoll();
          if (typeof pending === 'function') await pending();
        } else {
          this.authErr = fmtApiError(data, res.status === 403
            ? 'Session expirée — recharge la page puis réessaie.'
            : 'Échec de connexion.');
        }
      } catch (_) {
        this.authErr = 'Réseau indisponible. Réessaie.';
      } finally {
        this.authBusy = false;
      }
    },

    async authLogout() {
      await fetch('/api/v1/auth/logout/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': csrf() },
      });
      this.authentifie = false;
      this.username = null;
      this.categorie = 'visiteur';
      this.estVip = false;
      this.chatUnread = 0;
      this.stopChatPoll();
      this.stopUnreadPoll();
    },

    setJourDate(val) {
      this.jourDate = val || dateLocaleISO(new Date());
      this.partageMsg = '';
      this.chargerPredictionsJour();
    },

    async ouvrirCompos() {
      if (!this.authentifie) {
        this.ouvrirAuth(
          'Connecte-toi pour ouvrir Nos Zanalyze.',
          () => this.ouvrirCompos(),
        );
        return;
      }
      if (!this.peutVip) {
        this.ouvrirVipGate('analyse');
        return;
      }
      this.sheetApercu = false;
      this.sheetClub = false;
      this.sheetAuth = false;
      this.apercu = null;
      this.partageMsg = '';
      this.composExpanded = false;
      // Aligner sur le filtre date de la liste (bilans du jour passé inclus).
      this.jourDate = this.filtreDate || dateLocaleISO(new Date());
      this.sheetCompos = true;
      document.body.classList.add('sheet-open');
      await this.chargerPredictionsJour();
    },

    optCompos(bloc, niveau) {
      if (!bloc) return null;
      if (niveau === 'prudente') return bloc.prudente || null;
      if (niveau === 'recommandee') return bloc.recommandee || null;
      if (niveau === 'filet') return bloc.filet || null;
      if (!bloc.options) return null;
      return bloc.options.find((o) => o.niveau === niveau) || null;
    },

    composDragStart(ev) {
      const t = ev.touches && ev.touches[0];
      if (!t) return;
      this._composDragY = t.clientY;
    },

    composDragMove(ev) {
      if (this._composDragY == null) return;
      const t = ev.touches && ev.touches[0];
      if (!t) return;
      const dy = this._composDragY - t.clientY;
      this._composLastDy = -dy; // positif = tire vers le bas
      if (dy > 36) this.composExpanded = true;
      if (dy < -36) this.composExpanded = false;
    },

    composDragEnd() {
      if (this._composDragY == null) return;
      // Si on a baissé fort depuis le départ, fermer la feuille.
      // (dy négatif stocké via _composLastDy)
      const last = this._composLastDy || 0;
      this._composDragY = null;
      this._composLastDy = null;
      if (last < -90) this.fermerSheets();
    },

    async chargerPredictionsJour() {
      const jour = this.jourDate || dateLocaleISO(new Date());
      this.jourDate = jour;
      this.chargementJour = true;
      this.predictionsJour = [];
      const auj = this.dateAujourdhui();
      const passe = jour < auj;
      this.jourPasseCompos = passe;
      const q = new URLSearchParams();
      // Aujourd'hui : garder les terminés (bilans) + à venir.
      q.set('statut', passe ? 'termine' : 'termine,a_venir,en_cours');
      q.set('page_size', '80');
      q.set('depuis', jour);
      q.set('jusqu_a', jour);
      const { data, ok } = await getJSON('/api/v1/matchs/?' + q.toString());
      this.chargementJour = false;
      if (!ok) return;
      const ordre = { prudente: 0, recommandee: 1, filet: 2 };
      const list = (data && data.results) || [];
      this.predictionsJour = list
        .map((m) => {
          const termine = m.statut === 'termine';
          let options = (m.options || [])
            .filter((o) => (
              o.niveau === 'prudente'
              || o.niveau === 'recommandee'
              || o.niveau === 'filet'
            ))
            .sort((a, b) => ordre[a.niveau] - ordre[b.niveau]);
          if (termine && !this.peutBilanComplet) {
            options = options.filter((o) => o.niveau === 'prudente' || o.niveau === 'filet');
          }
          const prudente = options.find((o) => o.niveau === 'prudente') || null;
          const recommandee = options.find((o) => o.niveau === 'recommandee') || null;
          const filet = options.find((o) => o.niveau === 'filet') || null;
          return {
            id: m.id,
            competition: m.competition,
            domicile: m.domicile,
            exterieur: m.exterieur,
            coup_denvoi: m.coup_denvoi,
            statut: m.statut,
            score: m.score,
            options,
            prudente,
            recommandee,
            filet,
            termine,
          };
        })
        .filter((b) => b.prudente || b.recommandee || b.filet);
    },

    textePredictionsJour() {
      const lignes = [];
      this.predictionsJour.forEach((m) => {
        lignes.push(
          (m.competition && m.competition.code ? m.competition.code + ' · ' : '')
          + m.domicile.nom_court + ' – ' + m.exterieur.nom_court
          + (m.score ? ' (' + m.score + ')' : ''),
        );
        m.options.forEach((o) => {
          if (m.termine || this.jourPasseCompos) {
            lignes.push(
              '  ' + this.libNiveau(o.niveau) + ' : ' + o.libelle
              + ' → ' + this.libResultatTip(o),
            );
          } else {
            lignes.push(
              '  ' + this.libNiveau(o.niveau) + ' : ' + o.libelle
              + ' (' + this.fmtPct(o.probabilite) + ')',
            );
          }
        });
        lignes.push('');
      });
      lignes.push('Zanalyze');
      return lignes;
    },

    blocsPdfCompos() {
      return this.predictionsJour.map((m) => ({
        header: (m.competition && m.competition.code ? m.competition.code + ' | ' : '')
          + m.domicile.nom_court + ' - ' + m.exterieur.nom_court
          + (m.score ? '  ' + m.score : '')
          + '  (' + this.dateHeure(m.coup_denvoi) + ')',
        lines: [
          m.prudente
            ? ('Prudent : ' + m.prudente.libelle + (this.jourPasseCompos
              ? '  → ' + this.libResultatTip(m.prudente)
              : '  ·  ' + this.fmtPct(m.prudente.probabilite)))
            : null,
          m.recommandee
            ? ('Recommande : ' + m.recommandee.libelle + (this.jourPasseCompos
              ? '  → ' + this.libResultatTip(m.recommandee)
              : '  ·  ' + this.fmtPct(m.recommandee.probabilite)))
            : null,
          m.filet
            ? ('Securite : ' + m.filet.libelle + (this.jourPasseCompos
              ? '  → ' + this.libResultatTip(m.filet)
              : '  ·  ' + this.fmtPct(m.filet.probabilite)))
            : null,
        ].filter(Boolean),
      }));
    },

    async partagerPredictionsJour() {
      this.partageMsg = '';
      this.partageBusy = true;
      const titre = this.jourPasseCompos
        ? ('Zanalyze — Bilans · ' + fmtJour(this.jourDate + 'T12:00:00'))
        : ('Zanalyze — Nos Zanalyze · ' + fmtJour(this.jourDate + 'T12:00:00'));
      const text = [
        titre,
        'Voici notre sélection du jour, tirée de notre moteur de prédiction Zanalyze',
        '',
        ...this.textePredictionsJour(),
      ].join('\n');
      try {
        if (navigator.share) {
          await navigator.share({ title: 'Nos Zanalyze', text });
          this.partageMsg = 'Partage envoyé.';
          return;
        }
        await navigator.clipboard.writeText(text);
        this.partageMsg = 'Liste copiée dans le presse-papiers.';
      } catch (e) {
        if (e && e.name === 'AbortError') return;
        try {
          await navigator.clipboard.writeText(text);
          this.partageMsg = 'Liste copiée dans le presse-papiers.';
        } catch (_) {
          this.partageMsg = 'Impossible de partager automatiquement.';
        }
      } finally {
        this.partageBusy = false;
      }
    },

    imprimerCompos() {
      this.partageMsg = '';
      if (!this.predictionsJour.length) return;
      this.composExpanded = true;
      document.body.classList.add('print-compos');
      const cleanup = () => {
        document.body.classList.remove('print-compos');
        window.removeEventListener('afterprint', cleanup);
      };
      window.addEventListener('afterprint', cleanup);
      // Laisse le temps aux logos / styles de peindre avant l’aperçu PDF.
      this.$nextTick(() => {
        window.setTimeout(() => window.print(), 250);
      });
    },

    telechargerPdfCompos() {
      this.imprimerCompos();
    },

    ecouterInstallPWA() {
      const standalone = window.matchMedia('(display-mode: standalone)').matches
        || window.navigator.standalone === true;
      this.installePWA = !!standalone;
      if (standalone) {
        this.peutInstaller = false;
        this.sheetInstall = false;
        return;
      }
      const ua = navigator.userAgent || '';
      this.installIOS = /iPad|iPhone|iPod/.test(ua)
        || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
      if (this.installIOS) {
        this.installHint = 'Sur iPhone / iPad : Partager → Sur l’écran d’accueil.';
      } else {
        this.installHint = 'Clique « Installer », ou utilise le menu du navigateur « Installer l’application ».';
      }
      window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault();
        this._deferredInstall = e;
        this.peutInstaller = true;
      });
      window.addEventListener('appinstalled', () => {
        this.peutInstaller = false;
        this.installePWA = true;
        this.sheetInstall = false;
        this._deferredInstall = null;
        document.body.classList.remove('sheet-open');
      });
    },

    async installerPWA() {
      if (this._deferredInstall) {
        this._deferredInstall.prompt();
        const choice = await this._deferredInstall.userChoice;
        this._deferredInstall = null;
        this.peutInstaller = false;
        if (choice && choice.outcome === 'accepted') {
          this.installePWA = true;
          this.sheetInstall = false;
          document.body.classList.remove('sheet-open');
        }
        return;
      }
      this.sheetInstall = true;
      document.body.classList.add('sheet-open');
    },

    async purgerCache() {
      if (!('caches' in window)) return;
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
      this.cachePurge = true;
    },

    ouvrirChatImage(url) {
      if (!url) return;
      this.chatLightboxUrl = url;
      document.body.classList.add('sheet-open');
    },

    fermerChatImage() {
      this.chatLightboxUrl = '';
      if (!this.sheetCompos && !this.sheetApercu && !this.sheetAuth && !this.sheetClub
        && !this.sheetInstall && !this.sheetJustif && !this.sheetCgu && !this.sheetVip) {
        document.body.classList.remove('sheet-open');
      }
    },

    stopChatPoll() {
      if (this._chatPoll) {
        clearInterval(this._chatPoll);
        this._chatPoll = null;
      }
    },

    stopUnreadPoll() {
      if (this._unreadPoll) {
        clearInterval(this._unreadPoll);
        this._unreadPoll = null;
      }
    },

    demarrerUnreadPoll() {
      this.stopUnreadPoll();
      if (!this.peutVip) {
        this.chatUnread = 0;
        return;
      }
      this.rafraichirSalonUnread();
      this._unreadPoll = setInterval(() => this.rafraichirSalonUnread(), 20000);
    },

    salonLastReadAt() {
      return localStorage.getItem(LS_SALON_READ) || '';
    },

    marquerSalonLu() {
      let stamp = '';
      if (this.chatMessages.length) {
        stamp = this.chatMessages[this.chatMessages.length - 1].created_at || '';
      }
      if (!stamp) stamp = new Date().toISOString();
      localStorage.setItem(LS_SALON_READ, stamp);
      this.chatUnread = 0;
    },

    async rafraichirSalonUnread() {
      if (!this.peutVip) {
        this.chatUnread = 0;
        return;
      }
      if (this.page === 'salon') {
        this.chatUnread = 0;
        return;
      }
      let since = this.salonLastReadAt();
      if (!since) {
        // Première visite VIP : ne pas exploser le badge avec tout l’historique.
        localStorage.setItem(LS_SALON_READ, new Date().toISOString());
        this.chatUnread = 0;
        return;
      }
      try {
        const q = new URLSearchParams();
        q.set('since', since);
        const { data, ok, status } = await getJSON('/api/v1/salon/?' + q.toString());
        if (status === 401 || status === 403 || !ok || !data) {
          if (status === 401 || status === 403) this.chatUnread = 0;
          return;
        }
        if (typeof data.en_ligne === 'number') this.chatEnLigne = data.en_ligne;
        const incoming = data.results || [];
        this.chatUnread = incoming.filter((m) => m && !m.est_moi).length;
      } catch (_) { /* hors ligne */ }
    },

    async ouvrirSalon() {
      this.stopChatPoll();
      if (!this.peutVip) {
        this.chatMessages = [];
        this.chatUnread = 0;
        return;
      }
      this.chatErr = '';
      this.chatSince = null;
      this._chatStickBottom = true;
      await this.chargerChat({ reset: true });
      this.marquerSalonLu();
      this._chatPoll = setInterval(() => {
        if (this.page === 'salon' && this.peutVip) this.chargerChat({ silent: true });
      }, 3500);
    },

    chatShowMeta(msg, idx) {
      if (!msg || msg.est_moi) return false;
      if (idx === 0) return true;
      const prev = this.chatMessages[idx - 1];
      return !prev || prev.auteur !== msg.auteur || prev.est_moi;
    },

    fmtChatHeure(iso) {
      if (!iso) return '';
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return '';
      return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
    },

    onSalonScroll() {
      const el = this.$refs.salonFeed;
      if (!el) return;
      const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
      this._chatStickBottom = dist < 72;
    },

    scrollSalonBas(force) {
      this.$nextTick(() => {
        const el = this.$refs.salonFeed;
        if (!el) return;
        if (force || this._chatStickBottom) {
          el.scrollTop = el.scrollHeight;
          this._chatStickBottom = true;
        }
      });
    },

    async chargerChat(opts = {}) {
      if (!this.peutVip) return;
      if (opts.reset) this.chatChargement = true;
      const q = new URLSearchParams();
      if (!opts.reset && this.chatSince) q.set('since', this.chatSince);
      const url = '/api/v1/salon/' + (q.toString() ? '?' + q.toString() : '');
      try {
        const { data, ok, status } = await getJSON(url);
        if (status === 401 || status === 403) {
          if (data && data.code === 'vip_required') {
            this.chatErr = 'Salon Premium réservé aux comptes Premium.';
          }
          this.stopChatPoll();
          return;
        }
        if (!ok || !data) return;
        if (typeof data.en_ligne === 'number') this.chatEnLigne = data.en_ligne;
        const incoming = data.results || [];
        if (opts.reset || !this.chatSince) {
          this.chatMessages = incoming;
        } else if (incoming.length) {
          const seen = new Set(this.chatMessages.map((m) => m.id));
          const fresh = incoming.filter((m) => !seen.has(m.id));
          if (fresh.length) this.chatMessages = this.chatMessages.concat(fresh);
        }
        if (this.chatMessages.length) {
          this.chatSince = this.chatMessages[this.chatMessages.length - 1].created_at;
        }
        if (this.page === 'salon') this.marquerSalonLu();
        this.scrollSalonBas(!!opts.reset);
      } finally {
        this.chatChargement = false;
      }
    },

    async envoyerChat() {
      const texte = (this.chatDraft || '').trim();
      const image = this.chatImage;
      if ((!texte && !image) || this.chatBusy) return;
      if (!this.peutVip) {
        this.ouvrirVipGate('salon');
        return;
      }
      this.chatBusy = true;
      this.chatErr = '';
      try {
        let res;
        if (image) {
          const fd = new FormData();
          if (texte) fd.append('texte', texte);
          fd.append('image', image, image.name || 'screenshot.png');
          res = await fetch('/api/v1/salon/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
              Accept: 'application/json',
              'X-CSRFToken': csrf(),
            },
            body: fd,
          });
        } else {
          res = await fetch('/api/v1/salon/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
              'Content-Type': 'application/json',
              Accept: 'application/json',
              'X-CSRFToken': csrf(),
            },
            body: JSON.stringify({ texte }),
          });
        }
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          this.chatErr = (data && data.detail)
            || (data.texte && data.texte[0])
            || (data.image && data.image[0])
            || 'Envoi impossible.';
          return;
        }
        this.chatDraft = '';
        this.clearChatImage();
        const seen = new Set(this.chatMessages.map((m) => m.id));
        if (!seen.has(data.id)) this.chatMessages.push(data);
        this.chatSince = data.created_at;
        this._chatStickBottom = true;
        this.scrollSalonBas(true);
      } catch (_) {
        this.chatErr = 'Réseau indisponible.';
      } finally {
        this.chatBusy = false;
      }
    },

    onChatImagePick(ev) {
      const file = ev.target && ev.target.files && ev.target.files[0];
      if (this.$refs.salonImageInput) this.$refs.salonImageInput.value = '';
      if (!file) return;
      if (!/^image\/(jpeg|jpg|png|webp|gif)$/i.test(file.type || '')) {
        this.chatErr = 'Formats acceptés : JPG, PNG, WEBP, GIF.';
        return;
      }
      if (file.size > 5 * 1024 * 1024) {
        this.chatErr = 'Image trop lourde (5 Mo max).';
        return;
      }
      this.chatErr = '';
      if (this.chatImagePreview) URL.revokeObjectURL(this.chatImagePreview);
      this.chatImage = file;
      this.chatImagePreview = URL.createObjectURL(file);
    },

    clearChatImage() {
      if (this.chatImagePreview) URL.revokeObjectURL(this.chatImagePreview);
      this.chatImage = null;
      this.chatImagePreview = '';
    },

    enregistrerSW() {
      if (!('serviceWorker' in navigator)) return;
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).then((reg) => {
        this._swReg = reg;
        if (reg.waiting) this.swWaiting = true;
        reg.addEventListener('updatefound', () => {
          const w = reg.installing;
          if (!w) return;
          w.addEventListener('statechange', () => {
            if (w.state === 'installed' && navigator.serviceWorker.controller) {
              this.swWaiting = true;
            }
          });
        });
      }).catch(() => {});
    },

    appliquerMaj() {
      const w = this._swReg && this._swReg.waiting;
      if (w) {
        w.postMessage({ type: 'SKIP_WAITING' });
        navigator.serviceWorker.addEventListener('controllerchange', () => location.reload(), { once: true });
        return;
      }
      location.reload();
    },
  };
}

window.c2b = c2b;
document.addEventListener('alpine:init', () => {
  Alpine.data('c2b', c2b);
});
