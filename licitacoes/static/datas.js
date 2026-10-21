// Campos de data sempre no padrão brasileiro (dd/mm/aaaa e dd/mm/aaaa hh:mm), seja qual
// for o idioma do navegador. O campo nativo continua no formulário, escondido, com o mesmo
// nome e id: é ele que vai para o servidor e que os outros scripts leem.
(function () {
  function paraTexto(valor, comHora) {
    if (!valor) return '';
    var d = valor.slice(0, 10).split('-');
    var texto = d[2] + '/' + d[1] + '/' + d[0];
    if (comHora && valor.length >= 16) texto += ' ' + valor.slice(11, 16);
    return texto;
  }

  function paraIso(texto, comHora) {
    var m = texto.match(/^(\d{2})\/(\d{2})\/(\d{4})(?: (\d{2}):(\d{2}))?$/);
    if (!m || (comHora && !m[4])) return null;
    var dia = +m[1], mes = +m[2], ano = +m[3];
    var data = new Date(Date.UTC(ano, mes - 1, dia));
    if (data.getUTCDate() !== dia || data.getUTCMonth() !== mes - 1) return null;
    if (comHora && (+m[4] > 23 || +m[5] > 59)) return null;
    return m[3] + '-' + m[2] + '-' + m[1] + (comHora ? 'T' + m[4] + ':' + m[5] : '');
  }

  // Digita só números: as barras, o espaço e os dois-pontos entram sozinhos.
  function mascara(texto, comHora) {
    var n = texto.replace(/\D/g, '').slice(0, comHora ? 12 : 8), saida = '';
    for (var i = 0; i < n.length; i++) {
      if (i === 2 || i === 4) saida += '/';
      if (i === 8) saida += ' ';
      if (i === 10) saida += ':';
      saida += n[i];
    }
    return saida;
  }

  function preparar(nativo) {
    var comHora = nativo.type === 'datetime-local';
    var formato = comHora ? 'dd/mm/aaaa hh:mm' : 'dd/mm/aaaa';
    var caixa = document.createElement('span');
    caixa.className = 'campo-data';
    var texto = document.createElement('input');
    texto.type = 'text';
    texto.inputMode = 'numeric';
    texto.autocomplete = 'off';
    texto.placeholder = formato;
    texto.value = paraTexto(nativo.value, comHora);
    texto.required = nativo.required;
    var botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'botao-calendario';
    botao.setAttribute('aria-label', 'Abrir calendário');
    botao.title = 'Abrir calendário';

    nativo.parentNode.insertBefore(caixa, nativo);
    caixa.appendChild(texto);
    caixa.appendChild(botao);
    caixa.appendChild(nativo);
    nativo.required = false;
    nativo.tabIndex = -1;
    nativo.classList.add('data-nativa');
    nativo.setAttribute('aria-hidden', 'true');

    function avisar() { nativo.dispatchEvent(new Event('change', { bubbles: true })); }

    texto.addEventListener('input', function () {
      texto.value = mascara(texto.value, comHora);
      var iso = paraIso(texto.value, comHora);
      if (iso) {
        texto.setCustomValidity('');
        if (nativo.value !== iso) { nativo.value = iso; avisar(); }
      } else {
        texto.setCustomValidity(texto.value ? 'Use o formato ' + formato + '.' : '');
        if (nativo.value) { nativo.value = ''; avisar(); }
      }
    });
    nativo.addEventListener('change', function () {
      var atual = paraTexto(nativo.value, comHora);
      if (atual !== texto.value) { texto.value = atual; texto.setCustomValidity(''); }
    });
    botao.addEventListener('click', function () {
      try { nativo.showPicker(); } catch (e) { texto.focus(); }
    });
  }

  document.querySelectorAll('input[type=date], input[type=datetime-local]').forEach(preparar);
})();
