/* Zanalyze Admin — listes compactes + popup détail */
(function () {
  'use strict';

  function textOf(el) {
    return (el && el.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function iconFor(label, value) {
    var l = (label || '').toLowerCase();
    var v = (value || '').toLowerCase();
    if (l.indexOf('mail') !== -1 || l.indexOf('électron') !== -1) return '✉';
    if (l.indexOf('statut') !== -1 || l.indexOf('premium') !== -1 || v.indexOf('premium') !== -1) return '◆';
    if (l.indexOf('point') !== -1) return '★';
    if (l.indexOf('expire') !== -1 || l.indexOf('date') !== -1 || l.indexOf('updated') !== -1 || l.indexOf('jour') !== -1) return '◷';
    if (l.indexOf('visite') !== -1) return '◎';
    if (l.indexOf('page') !== -1) return '▢';
    if (l.indexOf('whatsapp') !== -1 || l.indexOf('phone') !== -1) return '☎';
    if (l.indexOf('tarif') !== -1) return '💶';
    if (l.indexOf('note') !== -1) return '✎';
    if (l.indexOf('match') !== -1) return '⚽';
    if (l.indexOf('auteur') !== -1 || l.indexOf('user') !== -1 || l.indexOf('nom') !== -1) return '👤';
    return '•';
  }

  function enhanceLists() {
    document.querySelectorAll('#result_list').forEach(function (table) {
      table.classList.add('zyz-smart-list');
      var headers = Array.prototype.map.call(
        table.querySelectorAll('thead th'),
        function (th) { return textOf(th); }
      );
      table.querySelectorAll('tbody tr').forEach(function (tr) {
        tr.classList.add('zyz-row-card', 'zyz-list-item');
        var cells = [];
        Array.prototype.forEach.call(tr.children, function (td, i) {
          if (td.classList.contains('action-checkbox')) return;
          var label = headers[i] || '';
          var value = textOf(td);
          td.setAttribute('data-label', label);
          if (!value || value === '—' || value === '-') {
            td.classList.add('zyz-empty-cell');
            return;
          }
          cells.push({ label: label, value: value, html: td.innerHTML, href: (td.querySelector('a') || {}).href || '' });
        });

        var primary = cells[0] || { label: '', value: '—', html: '—', href: '' };
        var link = tr.querySelector('th a, td a');
        var href = (link && link.href) || primary.href || '';
        var initiale = (primary.value || '?').replace(/[^0-9a-zA-ZÀ-ÿ]/g, '').charAt(0).toUpperCase() || '?';

        var meta = document.createElement('div');
        meta.className = 'zyz-list-meta';
        cells.slice(1, 4).forEach(function (c) {
          var chip = document.createElement('span');
          chip.className = 'zyz-list-chip';
          chip.innerHTML = '<i aria-hidden="true">' + iconFor(c.label, c.value) + '</i> ' +
            '<em>' + c.label + '</em> <strong></strong>';
          chip.querySelector('strong').textContent = c.value.length > 28 ? c.value.slice(0, 26) + '…' : c.value;
          meta.appendChild(chip);
        });

        var main = document.createElement('button');
        main.type = 'button';
        main.className = 'zyz-list-mainbtn';
        main.innerHTML =
          '<span class="zyz-list-avatar" aria-hidden="true">' + initiale + '</span>' +
          '<span class="zyz-list-copy">' +
            '<span class="zyz-list-title"></span>' +
            '<span class="zyz-list-sub"></span>' +
          '</span>' +
          '<span class="zyz-list-chevron" aria-hidden="true">›</span>';
        main.querySelector('.zyz-list-title').textContent = primary.value;
        main.querySelector('.zyz-list-sub').textContent = cells[1] ? (cells[1].label + ' · ' + cells[1].value) : 'Voir le détail';

        var shell = document.createElement('div');
        shell.className = 'zyz-list-shell';
        shell.appendChild(main);
        if (meta.childNodes.length) shell.appendChild(meta);

        // Cache raw cells for popup; hide original field cells visually via CSS
        tr._zyzCells = cells;
        tr._zyzHref = href;
        tr._zyzTitle = primary.value;
        tr._zyzInitiale = initiale;

        var anchor = tr.querySelector('td.action-checkbox') || tr.firstElementChild;
        if (anchor && anchor.nextSibling) {
          tr.insertBefore(shell, anchor.nextSibling);
        } else {
          tr.appendChild(shell);
        }

        main.addEventListener('click', function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          openModal(tr);
        });
      });
    });
  }

  function openModal(tr) {
    var modal = document.getElementById('zyz-detail-modal');
    if (!modal) return;
    var cells = tr._zyzCells || [];
    document.getElementById('zyz-modal-title').textContent = tr._zyzTitle || 'Détail';
    document.getElementById('zyz-modal-avatar').textContent = tr._zyzInitiale || '?';
    document.getElementById('zyz-modal-kicker').textContent =
      (document.querySelector('.zyz-page-title') || {}).textContent || 'Fiche';
    var fields = document.getElementById('zyz-modal-fields');
    fields.innerHTML = '';
    cells.forEach(function (c) {
      var li = document.createElement('li');
      li.innerHTML =
        '<span class="zyz-modal-ico" aria-hidden="true">' + iconFor(c.label, c.value) + '</span>' +
        '<div><em></em><strong></strong></div>';
      li.querySelector('em').textContent = c.label || 'Info';
      li.querySelector('strong').textContent = c.value;
      fields.appendChild(li);
    });
    var edit = document.getElementById('zyz-modal-edit');
    if (tr._zyzHref) {
      edit.href = tr._zyzHref;
      edit.hidden = false;
    } else {
      edit.hidden = true;
    }
    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('zyz-modal-open');
  }

  function closeModal() {
    var modal = document.getElementById('zyz-detail-modal');
    if (!modal) return;
    modal.hidden = true;
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('zyz-modal-open');
  }

  function wireModal() {
    var modal = document.getElementById('zyz-detail-modal');
    if (!modal) return;
    modal.querySelectorAll('[data-zyz-close]').forEach(function (el) {
      el.addEventListener('click', closeModal);
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') closeModal();
    });
  }

  function polishDatetimeWidgets() {
    document.querySelectorAll('.form-row .datetime').forEach(function (wrap) {
      if (wrap.classList.contains('zyz-datetime')) return;
      wrap.classList.add('zyz-datetime');
      var lines = [];
      var current = { label: '', input: null, shortcuts: null };

      function pushLine() {
        if (!current.input) {
          current = { label: '', input: null, shortcuts: null };
          return;
        }
        var line = document.createElement('div');
        line.className = 'zyz-dt-line';
        if (current.label) {
          var lab = document.createElement('span');
          lab.className = 'zyz-dt-label';
          lab.textContent = current.label.replace(/:\s*$/, '').trim();
          line.appendChild(lab);
        }
        line.appendChild(current.input);
        if (current.shortcuts) line.appendChild(current.shortcuts);
        lines.push(line);
        current = { label: '', input: null, shortcuts: null };
      }

      Array.prototype.slice.call(wrap.childNodes).forEach(function (node) {
        if (node.nodeType === 3) {
          var t = String(node.textContent || '').replace(/\s+/g, ' ').trim();
          if (t) current.label += (current.label ? ' ' : '') + t;
          return;
        }
        if (node.nodeType !== 1) return;
        if (node.tagName === 'BR') {
          pushLine();
          return;
        }
        if (
          node.tagName === 'INPUT'
          || node.classList.contains('vDateField')
          || node.classList.contains('vTimeField')
        ) {
          current.input = node;
          return;
        }
        if (node.classList.contains('datetimeshortcuts')) {
          current.shortcuts = node;
          pushLine();
        }
      });
      pushLine();
      while (wrap.firstChild) wrap.removeChild(wrap.firstChild);
      lines.forEach(function (line) { wrap.appendChild(line); });
    });
  }

  function polishChrome() {
    var toolbar = document.getElementById('toolbar');
    if (toolbar) toolbar.classList.add('zyz-toolbar');
    var actions = document.querySelector('.actions');
    if (actions) actions.classList.add('zyz-actions-bar');
    document.body.classList.add('zyz-admin');
    polishDatetimeWidgets();
    // Change form: compact secondary saves
    var submit = document.querySelector('.submit-row');
    if (submit) {
      submit.classList.add('zyz-submit-compact');
      document.body.classList.add('zyz-has-sticky-submit');
      var inputs = submit.querySelectorAll('input[type="submit"], a.deletelink');
      if (inputs.length > 2) {
        var more = document.createElement('details');
        more.className = 'zyz-submit-more';
        more.innerHTML = '<summary>Plus d’options</summary><div class="zyz-submit-more-panel"></div>';
        var panel = more.querySelector('.zyz-submit-more-panel');
        Array.prototype.forEach.call(inputs, function (inp, idx) {
          if (idx === 0) return; // keep primary Enregistrer
          if (inp.classList.contains('deletelink') || (inp.value || '').toLowerCase().indexOf('supprim') !== -1) {
            return; // keep delete visible
          }
          panel.appendChild(inp);
        });
        if (panel.childNodes.length) {
          var del = submit.querySelector('a.deletelink');
          if (del) submit.insertBefore(more, del);
          else submit.appendChild(more);
        }
      }
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    enhanceLists();
    wireModal();
    polishChrome();
  });
})();
