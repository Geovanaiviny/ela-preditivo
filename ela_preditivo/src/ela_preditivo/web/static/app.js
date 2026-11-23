/* EloSense — plataforma clínica (ela_preditivo). JavaScript puro, sem framework, sem build, sem recurso externo.
 * Regras: nenhum dado pessoal em URL (rotas por hash só com ids), nada guardado no navegador (todo o estado vive em
 * memória) e nenhum dado pessoal em mensagem de erro. A interface só reflete as permissões devolvidas por "quem sou eu";
 * a decisão de acesso é sempre do servidor. */
'use strict';
(function () {
  // ---------------------------------------------------------------------------------------------
  // Estado em memória
  // ---------------------------------------------------------------------------------------------
  const estado = { sistema: null, eu: null, csrf: null, analises: {}, nomesPacientes: {}, avisoPendente: null, opcoes: null };
  const ROTULO_SEXO = { M: 'Masculino', F: 'Feminino' };
  const UFS = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' ');
  const PAPEIS_GENITOR = ['MAE', 'PAI'];
  const ROTULO_SITUACAO_GENITOR = { vivo_assintomatico: 'vivo, sem sintomas', falecido_sem_ela: 'falecido sem ELA', afetado: 'teve ou tem ELA', desconhecido: 'situação desconhecida' };

  // ---------------------------------------------------------------------------------------------
  // Utilitários de DOM (sempre textContent: nunca HTML vindo de dados)
  // ---------------------------------------------------------------------------------------------
  function el(tag, attrs, ...filhos) {
    const no = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === 'class') no.className = v;
        else if (k === 'text') no.textContent = v;
        else if (k.startsWith('on') && typeof v === 'function') no.addEventListener(k.slice(2), v);
        else if (k === 'dataset') Object.assign(no.dataset, v);
        else no.setAttribute(k, v === true ? '' : v);
      }
    }
    for (const f of filhos.flat()) {
      if (f === null || f === undefined || f === false) continue;
      no.append(f instanceof Node ? f : document.createTextNode(String(f)));
    }
    return no;
  }
  function svgEl(tag, attrs, ...filhos) {
    const no = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) no.setAttribute(k, v);
    for (const f of filhos.flat()) if (f) no.append(f instanceof Node ? f : document.createTextNode(String(f)));
    return no;
  }
  function limpar(no) { while (no.firstChild) no.removeChild(no.firstChild); return no; }
  const main = () => document.getElementById('conteudo');

  // Ícones em SVG inline (decorativos; o texto ao lado dá o significado)
  const ICONES = {
    menu: 'M4 7h16M4 12h16M4 17h16',
    fechar: 'M6 6l12 12M18 6L6 18',
    pessoa: 'M12 12a4 4 0 100-8 4 4 0 000 8zM4 21c0-4 3.6-7 8-7s8 3 8 7',
    pacientes: 'M9 11.5a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM2.5 20c0-3.6 2.9-6.5 6.5-6.5s6.5 2.9 6.5 6.5M17 12a3 3 0 100-6 3 3 0 000 6zM15.5 14c3.3 0 6 2.7 6 6',
    frasco: 'M9 3h6M10 3v6l-5.5 9.5A2 2 0 006.2 21h11.6a2 2 0 001.7-2.5L14 9V3M7.5 15h9',
    prancheta: 'M8 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-1M9 3h6v3H9zM9 11h6M9 15h6',
    ajuda: 'M12 21a9 9 0 100-18 9 9 0 000 18zM9.5 9.5a2.5 2.5 0 015 0c0 1.5-2.5 2-2.5 3.5M12 17h.01',
    sair: 'M15 4h3a2 2 0 012 2v12a2 2 0 01-2 2h-3M10 17l5-5-5-5M15 12H3',
    baixar: 'M12 3v12M7 10l5 5 5-5M4 20h16',
    'seta-esq': 'M19 12H5M11 6l-6 6 6 6',
    'seta-dir': 'M5 12h14M13 6l6 6-6 6',
    info: 'M12 21a9 9 0 100-18 9 9 0 000 18zM12 11v5M12 8h.01',
    calendario: 'M3 7a2 2 0 012-2h14a2 2 0 012 2v12a2 2 0 01-2 2H5a2 2 0 01-2-2zM3 10h18M8 3v4M16 3v4',
    dna: 'M6 3c0 6 12 6 12 12M18 3c0 6-12 6-12 12M6 21c0-3 3-4.5 6-4.5s6 1.5 6 4.5M8 7h8M8 17h8',
    grafico: 'M3 20h18M4 16l5-6 4 3 7-8',
    degraus: 'M3 20h5v-5h5v-5h5V5h3',
    escudo: 'M12 3l8 3v6c0 5-3.5 8.5-8 9-4.5-.5-8-4-8-9V6l8-3zM9 12l2 2 4-4',
    email: 'M3 7a2 2 0 012-2h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2zM3 7l9 6 9-6',
    cadeado: 'M5 11h14a1 1 0 011 1v8a1 1 0 01-1 1H5a1 1 0 01-1-1v-8a1 1 0 011-1zM8 11V7a4 4 0 018 0v4',
    olho: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7zM12 15a3 3 0 100-6 3 3 0 000 6z',
    'olho-fechado': 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7zM12 15a3 3 0 100-6 3 3 0 000 6zM3 3l18 18',
    lupa: 'M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4',
    mais: 'M12 5v14M5 12h14',
    alerta: 'M12 3l10 18H2L12 3zM12 10v4M12 18h.01',
    check: 'M5 12l5 5L20 7',
    modelo: 'M4 6h8M16 6h4M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4',
    auditoria: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
    filtro: 'M3 5h18l-7 8v6l-4 2v-8L3 5z',
    arquivo: 'M6 3h8l5 5v13a1 1 0 01-1 1H6a1 1 0 01-1-1V4a1 1 0 011-1zM14 3v5h5',
    lixeira: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
    editar: 'M4 20h4l11-11-4-4L4 16v4zM13 7l4 4',
    relogio: 'M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3 2',
    casa: 'M3 11l9-8 9 8v9a1 1 0 01-1 1h-5v-6h-6v6H4a1 1 0 01-1-1v-9z',
    microscopio: 'M9 3h4v9a2 2 0 01-4 0V3zM6 19h12M9 15.5A6 6 0 0117 19M11 12v3',
    familia: 'M8 10a3 3 0 100-6 3 3 0 000 6zM16 10a3 3 0 100-6 3 3 0 000 6zM2 20c0-3.3 2.7-6 6-6M22 20c0-3.3-2.7-6-6-6M12 20a3 3 0 100-6 3 3 0 000 6z',
    casal: 'M8 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM16 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM1.5 21c0-3.6 2.9-6.5 6.5-6.5M22.5 21c0-3.6-2.9-6.5-6.5-6.5M9 17.5l3 3 3-3',
    transmissao: 'M4 6h5l3 6-3 6H4M15 12h5M17 9l3 3-3 3',
    upload: 'M12 15V3M7 8l5-5 5 5M4 20h16',
  };
  function icone(nome, classe) {
    const svg = svgEl('svg', { class: `icone ${classe || ''}`, viewBox: '0 0 24 24', 'aria-hidden': 'true', focusable: 'false' });
    svg.append(svgEl('path', { d: ICONES[nome] || ICONES.info, fill: 'none', stroke: 'currentColor', 'stroke-width': '1.8', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
    return svg;
  }

  function fmtNum(x, casas) {
    if (x === null || x === undefined || x === '' || Number.isNaN(Number(x))) return '—';
    const n = Number(x);
    if (casas === undefined) casas = Number.isInteger(n) ? 0 : 3;
    return n.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
  }
  function fmtPct(x, casas = 1) { return x === null || x === undefined || Number.isNaN(Number(x)) ? '—' : fmtNum(100 * Number(x), casas) + ' %'; }
  function fmtData(iso, soData) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return soData ? d.toLocaleDateString('pt-BR') : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
  }
  function fmtDataLocal(aaaammdd) { // "1996-03-12" → "12/03/1996", sem fuso
    if (!aaaammdd) return '—';
    const [a, m, d] = aaaammdd.split('-');
    return `${d}/${m}/${a}`;
  }
  function fmtMes(aaaamm) { if (!aaaamm) return '—'; const [a, m] = aaaamm.split('-'); return `${m}/${a}`; }
  function fmtBytes(n) { if (n === null || n === undefined) return '—'; return n > 1024 * 1024 ? `${fmtNum(n / 1024 / 1024, 1)} MB` : `${fmtNum(Math.round(n / 1024), 0)} kB`; }
  // Vírgula decimal na tela (o relatório e os CSV mantêm o ponto). Três pontos com milhar ficam como estão: "N = 10.000",
  // "3.250 sorteios" e qualquer grupo de exatamente três casas com parte inteira diferente de zero ("1.457 registros"),
  // que só é decimal quando vem logo antes de %, s ou ms.
  function localizarNumeros(texto) {
    return texto.replace(/(?:TCC |N = )\d+(?:\.\d+)+|\d+(?:\.\d{3})+(?= sorteios)|(?<![\p{L}\d.])(\d+)\.(\d+)([eE][+-]?\d+)?(?![\p{L}\d]|\.\d)/gu,
      (valor, inteiro, decimal, expoente, posicao, todo) => {
        if (inteiro === undefined) return valor;
        const milhar = !expoente && decimal.length === 3 && /^[1-9]/.test(inteiro);
        if (milhar && !/^\s?(?:%|m?s(?![\p{L}]))/u.test(todo.slice(posicao + valor.length))) return valor;
        return `${inteiro},${decimal}${expoente || ''}`;
      })
      .replace(/(\d)\s*%/g, '$1 %');
  }
  function fmtCelula(v) {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'number') return fmtNum(v, Number.isInteger(v) ? 0 : 4);
    if (typeof v === 'boolean') return v ? 'sim' : 'não';
    return localizarNumeros(String(v));
  }
  function iniciais(nome) { return (nome || '').split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('') || '?'; }

  function avisar(tipo, mensagem, opcoes = {}) {
    const caixa = document.getElementById('avisos');
    if (!opcoes.acumular) limpar(caixa);
    const alerta = el('div', { class: `alerta alerta-${tipo}`, role: tipo === 'erro' ? 'alert' : 'status' }, icone(tipo === 'erro' || tipo === 'aviso' ? 'alerta' : tipo === 'sucesso' ? 'check' : 'info'), el('p', { text: mensagem }));
    caixa.append(alerta);
    return alerta;
  }
  function limparAvisos() { limpar(document.getElementById('avisos')); }
  function definirTitulo(t) { document.title = `${t} — EloSense`; }

  // ---------------------------------------------------------------------------------------------
  // API
  // ---------------------------------------------------------------------------------------------
  async function api(metodo, caminho, opcoes = {}) {
    const init = { method: metodo, credentials: 'same-origin', headers: {} };
    if (opcoes.json !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(opcoes.json); }
    if (opcoes.form) init.body = opcoes.form;
    if (metodo !== 'GET' && estado.csrf) init.headers['X-CSRF-Token'] = estado.csrf;
    let resp;
    try { resp = await fetch(caminho, init); } catch (e) { const erro = new Error('Sem conexão com o servidor.'); erro.status = 0; erro.campos = {}; throw erro; }
    if (opcoes.bruto) return resp;
    let dados = null;
    try { dados = await resp.json(); } catch (e) { dados = null; }
    if (!resp.ok) {
      const erro = new Error((dados && dados.mensagem) || `Erro ${resp.status}.`);
      erro.status = resp.status; erro.codigo = dados && dados.erro; erro.campos = (dados && dados.campos) || {};
      if (resp.status === 401 && !opcoes.semRedirecionar) {
        const tinhaSessao = !!estado.eu;
        estado.eu = null; estado.csrf = null; renderizarCasca();
        estado.avisoPendente = tinhaSessao ? 'Sua sessão expirou ou foi encerrada. Entre novamente.' : 'Entre para continuar.';
        navegar('#/entrar');
      }
      throw erro;
    }
    return dados;
  }
  async function carregarSessao() {
    try { estado.sistema = await api('GET', '/api/sistema'); } catch (e) { estado.sistema = null; }
    try {
      const eu = await api('GET', '/api/contas/quem-sou-eu', { semRedirecionar: true });
      estado.eu = eu; estado.csrf = eu.csrf;
    } catch (e) { estado.eu = null; estado.csrf = null; }
  }
  async function opcoesPacientes() {
    if (!estado.opcoes) estado.opcoes = await api('GET', '/api/pacientes/opcoes');
    return estado.opcoes;
  }
  const permissoes = () => (estado.eu ? estado.eu.permissoes : []);
  const tem = (p) => permissoes().includes(p);

  // ---------------------------------------------------------------------------------------------
  // Casca: barra lateral, topo, trilha, gaveta no celular
  // ---------------------------------------------------------------------------------------------
  function itensMenu() {
    const itens = [];
    if (estado.eu && estado.eu.trocar_senha) return [['#/trocar-senha', 'Trocar a senha', 'cadeado']];
    if (estado.eu) {
      if (estado.eu.verificado) {
        itens.push(['#/inicio', 'Início', 'casa']);
        if (tem('pacientes.gerir')) itens.push(['#/pacientes', 'Pacientes', 'pacientes']);
        if (tem('analises.executar')) itens.push(['#/analises', 'Análises', 'frasco']);
        if (tem('pesquisa.casos')) itens.push(['#/pesquisa/casos', 'Registros de pesquisa', 'microscopio']);
        if (tem('modelo.ver')) itens.push(['#/modelo', 'Modelo e parâmetros', 'modelo']);
        if (tem('artefato.executar')) itens.push(['#/artefato', 'Artefato', 'grafico']);
        if (tem('base.ver')) itens.push(['#/base', 'Base de anotação', 'dna']);
        if (tem('usuarios.gerir')) { itens.push(['#/admin/pendentes', 'Cadastros pendentes', 'prancheta']); itens.push(['#/admin/usuarios', 'Usuários', 'pacientes']); }
        if (tem('auditoria.ver_tudo')) itens.push(['#/admin/auditoria', 'Auditoria', 'auditoria']);
        itens.push(['divisor']);
      }
      itens.push(['#/situacao', 'Situação do cadastro', 'prancheta']);
      if (tem('conta.gerir')) itens.push(['#/minha-conta', 'Minha conta', 'pessoa']);
    } else {
      if (primeiroAcessoPendente()) itens.push(['#/primeiro-acesso', 'Primeiro acesso', 'cadeado']);
      itens.push(['#/entrar', 'Entrar', 'sair'], ['#/criar-conta', 'Criar conta', 'mais'], ['#/ajuda', 'Ajuda', 'ajuda'], ['#/privacidade', 'Privacidade', 'escudo']);
    }
    return itens;
  }
  function renderizarCasca() {
    const sis = estado.sistema;
    const selo = document.getElementById('selo-demo');
    if (sis && sis.demonstracao) { selo.textContent = sis.selo_demonstracao; selo.hidden = false; } else selo.hidden = true;
    document.body.classList.toggle('publico', !estado.eu);
    const menu = limpar(document.getElementById('menu'));
    const rotaAtual = location.hash.split('?')[0];
    for (const item of itensMenu()) {
      if (item[0] === 'divisor') { menu.append(el('div', { class: 'divisor', role: 'separator' })); continue; }
      const [href, rotulo, ic] = item;
      const a = el('a', { href, title: rotulo }, icone(ic), el('span', { text: rotulo }));
      if (rotaAtual === href || (href === '#/pacientes' && rotaAtual.startsWith('#/pacientes')) || (href === '#/analises' && (rotaAtual.startsWith('#/analise') || rotaAtual.startsWith('#/resultado'))) || (href === '#/artefato' && rotaAtual.startsWith('#/artefato/'))) a.setAttribute('aria-current', 'page');
      menu.append(a);
    }
    const atual = limpar(document.getElementById('usuario-atual'));
    if (estado.eu) {
      const u = estado.eu.usuario;
      atual.append(el('div', { class: 'avatar', 'aria-hidden': 'true', title: u.nome, text: iniciais(u.nome) }), el('div', { class: 'texto-usuario' }, el('div', { class: 'nome', text: u.nome }), el('div', { class: 'papel', text: u.papel_rotulo })));
    }
    const acoes = limpar(document.getElementById('topo-acoes'));
    if (estado.eu) {
      acoes.append(el('a', { class: 'link-topo', href: '#/ajuda' }, icone('ajuda'), el('span', { class: 'texto-link', text: 'Ajuda' })), el('span', { class: 'separador', 'aria-hidden': 'true' }),
        el('button', { class: 'link-topo', type: 'button', onclick: sair }, icone('sair'), el('span', { class: 'texto-link', text: 'Sair' })));
    } else {
      acoes.append(el('a', { class: 'link-topo', href: '#/ajuda' }, icone('ajuda'), el('span', { class: 'texto-link', text: 'Ajuda' })), el('a', { class: 'link-topo', href: '#/entrar' }, icone('pessoa'), el('span', { text: 'Entrar' })));
    }
  }
  function definirTrilha(itens) { // [[rótulo, href?], ...]; o último é a tela atual
    const nav = limpar(document.getElementById('trilha'));
    itens.forEach(([rotulo, href], i) => {
      if (i > 0) nav.append(el('span', { class: 'sep', 'aria-hidden': 'true', text: '/' }));
      if (i === itens.length - 1) nav.append(el('span', { class: 'atual', 'aria-current': 'page', text: rotulo }));
      else if (href) nav.append(el('a', { href, text: rotulo }));
      else nav.append(el('span', { text: rotulo }));
    });
  }
  function areaDoPapel() {
    if (!estado.eu) return 'EloSense';
    if (tem('pacientes.gerir')) return 'Área clínica';
    if (tem('pesquisa.casos')) return 'Área de pesquisa';
    if (tem('usuarios.gerir')) return 'Administração';
    return 'Conta';
  }
  async function sair() {
    try { await api('POST', '/api/contas/logout'); } catch (e) { /* já sem sessão */ }
    estado.eu = null; estado.csrf = null; estado.analises = {}; estado.nomesPacientes = {}; estado.opcoes = null;
    renderizarCasca();
    estado.avisoPendente = 'Você saiu. Até logo.';
    navegar('#/entrar');
  }
  function abrirGaveta(aberta) {
    const lateral = document.getElementById('lateral');
    lateral.classList.toggle('aberta', aberta);
    document.getElementById('sobreposicao').hidden = !aberta;
    document.getElementById('botao-menu').setAttribute('aria-expanded', aberta ? 'true' : 'false');
    if (aberta) { const primeiro = lateral.querySelector('a'); if (primeiro) primeiro.focus(); } else document.getElementById('botao-menu').focus();
  }
  document.getElementById('botao-menu').addEventListener('click', () => abrirGaveta(!document.getElementById('lateral').classList.contains('aberta')));
  let recolhidaPeloUsuario = null; // null = automático pela largura da janela
  let ultimaLargura = window.innerWidth;
  function aplicarRecolhimento(ev) {
    if (ev && ev.type === 'resize' && window.innerWidth === ultimaLargura) return; // só a altura mudou
    ultimaLargura = window.innerWidth;
    if (window.innerWidth > 900 && document.getElementById('lateral').classList.contains('aberta')) abrirGavetaSilenciosa();
    const auto = window.innerWidth > 900 && window.innerWidth <= 1200;
    const recolhida = recolhidaPeloUsuario === null ? auto : recolhidaPeloUsuario;
    document.body.classList.toggle('lateral-recolhida', recolhida);
    const b = document.getElementById('botao-recolher');
    b.setAttribute('aria-pressed', recolhida ? 'true' : 'false');
    b.setAttribute('aria-label', recolhida ? 'Expandir menu lateral' : 'Recolher menu lateral');
    b.setAttribute('title', recolhida ? 'Expandir menu lateral' : 'Recolher menu lateral');
  }
  document.getElementById('botao-recolher').addEventListener('click', () => { recolhidaPeloUsuario = !document.body.classList.contains('lateral-recolhida'); aplicarRecolhimento(); });
  window.addEventListener('resize', aplicarRecolhimento);
  aplicarRecolhimento();
  document.getElementById('fechar-menu').addEventListener('click', () => abrirGaveta(false));
  document.getElementById('sobreposicao').addEventListener('click', () => abrirGaveta(false));
  document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && document.getElementById('lateral').classList.contains('aberta')) abrirGaveta(false); });

  // ---------------------------------------------------------------------------------------------
  // Componentes de formulário (rótulo em todo campo; erro associado por aria-describedby; aria-invalid)
  // ---------------------------------------------------------------------------------------------
  function campo(def) {
    const id = `c-${def.nome.replace(/\./g, '-')}`;
    const idErro = `${id}-erro`, idDica = `${id}-dica`;
    let input;
    if (def.tipo === 'select') {
      input = el('select', { id, name: def.nome });
      for (const [valor, rotulo] of def.opcoes) {
        const opcao = el('option', { value: valor, text: rotulo });
        opcao.disabled = def.placeholderVazio && valor === '';
        input.append(opcao);
      }
      if (def.valor !== undefined && def.valor !== null) input.value = def.valor;
    } else if (def.tipo === 'textarea') {
      input = el('textarea', { id, name: def.nome, rows: def.linhas || 4 });
      input.value = def.valor || '';
    } else {
      input = el('input', { id, name: def.nome, type: def.tipo || 'text' });
      if (def.valor !== undefined && def.valor !== null) input.value = def.valor;
    }
    if (def.atributos) for (const [k, v] of Object.entries(def.atributos)) input.setAttribute(k, v);
    if (def.obrigatorio) input.setAttribute('aria-required', 'true');
    if (def.somenteLeitura) { if (def.tipo === 'select') input.disabled = true; else input.setAttribute('readonly', ''); input.setAttribute('aria-readonly', 'true'); input.tabIndex = -1; }
    const descr = [def.dica ? idDica : null, idErro].filter(Boolean).join(' ');
    input.setAttribute('aria-describedby', descr);
    const rotulo = el('label', { for: id }, def.rotulo,
      def.obrigatorio ? [el('span', { class: 'obrig', 'aria-hidden': 'true', text: ' *' }), el('span', { class: 'sr-only', text: ' (obrigatório)' })] : null,
      def.opcional ? el('span', { class: 'opcional', text: ' (opcional)' }) : null);
    const erro = el('span', { id: idErro, class: 'erro' });
    let envoltorio = input;
    if (def.icone || def.mostrarSenha) {
      envoltorio = el('div', { class: `campo-com-icone ${def.mostrarSenha ? 'com-sufixo' : ''}` }, def.icone ? el('span', { class: 'icone-prefixo' }, icone(def.icone)) : null, input);
      if (def.mostrarSenha) {
        const alternar = el('button', { type: 'button', class: 'mostrar-senha', 'aria-label': 'Mostrar senha', 'aria-pressed': 'false' }, icone('olho'));
        alternar.addEventListener('click', () => {
          const mostrando = input.type === 'text';
          input.type = mostrando ? 'password' : 'text';
          alternar.setAttribute('aria-pressed', mostrando ? 'false' : 'true');
          alternar.setAttribute('aria-label', mostrando ? 'Mostrar senha' : 'Ocultar senha');
          limpar(alternar).append(icone(mostrando ? 'olho' : 'olho-fechado'));
        });
        envoltorio.append(alternar);
      }
    }
    const no = el('div', { class: `campo ${def.classe || ''} ${def.somenteLeitura ? 'somente-leitura' : ''}` }, rotulo, def.dica ? el('span', { id: idDica, class: 'dica', text: def.dica }) : null, envoltorio, erro);
    const obj = {
      no, input, nome: def.nome,
      valor() { return input.value; },
      setErro(msg) { erro.textContent = msg || ''; input.setAttribute('aria-invalid', msg ? 'true' : 'false'); },
    };
    input.addEventListener('input', () => obj.setErro(''));
    return obj;
  }
  function marcacao(def) { // checkbox ou radio: nunca pré-marcado quando é consentimento
    const id = `c-${def.nome.replace(/\./g, '-')}-${def.valor || 'x'}`;
    const input = el('input', { id, type: def.tipo || 'checkbox', name: def.nome, value: def.valor || 'on' });
    if (def.marcado) input.checked = true;
    const idErro = `${id}-erro`;
    input.setAttribute('aria-describedby', idErro);
    const erro = el('span', { id: idErro, class: 'erro' });
    const no = el('div', { class: `campo opcoes ${def.classe || ''}` }, el('label', { for: id }, input, el('span', {}, def.rotulo)), erro);
    const obj = { no, input, nome: def.nome, valor() { return input.checked; }, setErro(msg) { erro.textContent = msg || ''; input.setAttribute('aria-invalid', msg ? 'true' : 'false'); } };
    input.addEventListener('change', () => obj.setErro(''));
    return obj;
  }
  function cartoesOpcao(def) { // rádios apresentados como cartões: {nome, opcoes: [{valor, titulo, descricao, icone}], valor, onchange}
    const grupo = el('div', { class: 'cartoes-opcao', role: 'radiogroup', 'aria-label': def.rotulo });
    const inputs = [];
    for (const o of def.opcoes) {
      const id = `c-${def.nome}-${o.valor}`;
      const input = el('input', { id, type: 'radio', name: def.nome, value: o.valor });
      if (def.valor === o.valor) input.checked = true;
      inputs.push(input);
      const rotulo = el('label', { class: `cartao-opcao ${def.valor === o.valor ? 'selecionado' : ''}`, for: id }, input, el('span', { class: 'titulo-opcao' }, o.icone ? icone(o.icone) : null, ' ', o.titulo), el('span', { class: 'descricao-opcao', text: o.descricao }));
      input.addEventListener('change', () => { for (const l of grupo.querySelectorAll('.cartao-opcao')) l.classList.toggle('selecionado', l === rotulo && input.checked); if (input.checked && def.onchange) def.onchange(o.valor); });
      grupo.append(rotulo);
    }
    return { no: grupo, valor() { const m = inputs.find((i) => i.checked); return m ? m.value : null; } };
  }
  function aplicarErros(campos, erros, geral) {
    let primeiro = null;
    for (const c of Object.values(campos)) if (c && c.setErro) c.setErro('');
    for (const [nome, msg] of Object.entries(erros || {})) {
      const c = campos[nome];
      if (c && c.setErro) { c.setErro(msg); if (!primeiro) primeiro = c; }
      else geral = `${geral || ''} ${nome}: ${msg}`.trim();
    }
    if (geral) avisar('erro', geral);
    if (primeiro) primeiro.input.focus();
  }
  function botao(rotulo, opcoes = {}) {
    return el('button', { type: opcoes.tipo || 'button', class: `botao ${opcoes.classe || ''}`, onclick: opcoes.onclick, disabled: opcoes.desabilitado, 'aria-label': opcoes.ariaLabel }, opcoes.icone ? icone(opcoes.icone) : null, rotulo);
  }
  function linkBotao(rotulo, href, opcoes = {}) { return el('a', { class: `botao ${opcoes.classe || ''}`, href }, opcoes.icone ? icone(opcoes.icone) : null, rotulo); }
  function etapas(lista, atual) {
    const ol = el('ol', { class: 'etapas', 'aria-label': 'Etapas do formulário' });
    lista.forEach((t, i) => {
      if (i > 0) ol.append(el('li', { class: 'traco', 'aria-hidden': 'true' }));
      ol.append(el('li', { 'aria-current': i === atual ? 'step' : null, class: i < atual ? 'feita' : '' }, el('span', { class: 'num', 'aria-hidden': 'true', text: i < atual ? '✓' : String(i + 1) }), el('span', { text: `${i + 1}. ${t}` })));
    });
    return ol;
  }
  function mascararCpf(valor) {
    const d = valor.replace(/\D/g, '').slice(0, 11);
    return d.replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d{1,2})$/, '$1-$2');
  }
  function cpfValido(cpf) {
    const d = cpf.replace(/\D/g, '');
    if (d.length !== 11 || /^(\d)\1+$/.test(d)) return false;
    for (const i of [9, 10]) {
      let soma = 0;
      for (let j = 0; j < i; j++) soma += Number(d[j]) * ((i + 1) - j);
      let dv = (soma * 10) % 11; if (dv === 10) dv = 0;
      if (dv !== Number(d[i])) return false;
    }
    return true;
  }

  // ---------------------------------------------------------------------------------------------
  // Componentes de layout
  // ---------------------------------------------------------------------------------------------
  function chip(texto, classe, ic) { return el('span', { class: `chip ${classe || ''}` }, ic ? icone(ic) : null, texto); }
  function dica(texto) { return el('p', { class: 'dica-linha' }, icone('info'), el('span', { text: texto })); }
  function cabecalhoTela(def) { // {titulo, subtitulo, chips, acoes}
    const titulos = el('div', { class: 'titulos' }, el('h1', { text: def.titulo }), def.subtitulo ? el('p', { class: 'subtitulo', text: def.subtitulo }) : null, def.chips && def.chips.length ? el('div', { class: 'chips' }, def.chips) : null);
    return el('div', { class: 'cabecalho-tela' }, titulos, def.acoes && def.acoes.length ? el('div', { class: 'acoes' }, def.acoes) : null);
  }
  function secaoNumerada(num, titulo, ...filhos) {
    return el('section', { class: 'secao', 'aria-labelledby': `sec-${num}` }, el('h2', { class: 'secao-titulo', id: `sec-${num}` }, el('span', { class: 'secao-num', 'aria-hidden': 'true', text: String(num).padStart(2, '0') }), el('span', { class: 'sr-only', text: `Seção ${num}: ` }), titulo), el('div', { class: 'secao-corpo' }, filhos));
  }
  function cartaoApoio(titulo, linhas) { return el('aside', { class: 'cartao cartao-apoio', 'aria-label': titulo }, el('h2', { text: titulo }), el('div', { class: 'linhas-info' }, linhas.map((t) => dica(t)))); }
  function duasColunas(principal, lateral) { return el('div', { class: 'duas-colunas' }, el('div', { class: 'coluna-principal' }, principal), el('div', { class: 'coluna-lateral' }, lateral)); }
  function indicador(def) { // {icone, rotulo, valor, detalhe, destaque}
    return el('div', { class: `indicador ${def.destaque ? 'indicador-destaque' : ''}` }, el('div', { class: 'indicador-topo' }, el('span', { class: 'indicador-icone' }, icone(def.icone || 'info')), el('span', { class: 'indicador-rotulo', text: def.rotulo })), el('div', { class: 'indicador-valor', text: def.valor }), def.detalhe ? el('div', { class: 'indicador-detalhe', text: def.detalhe }) : null);
  }
  function chipTipo(p) { return chip(p.tipo_rotulo, 'chip-azul', p.tipo === 'CASAL' ? 'casal' : p.tipo === 'FAMILIA' ? 'familia' : 'pessoa'); }
  function chipPesquisa(p) {
    if (p.liberado_para_pesquisa) return chip('Liberado para pesquisa (pseudonimizado)', 'chip-ok', 'check');
    if (p.pesquisa_situacao === 'PENDENTE') return chip('Consentimentos pendentes', 'chip-aviso', 'relogio');
    return chip('Sem consentimento para pesquisa', 'chip-neutro');
  }
  function chipVcfs(p) {
    if (p.vcfs_completos) return chip('VCFs completos', 'chip-ok', 'dna');
    const inferidos = (p.genitores_inferidos || []).length;
    return chip(`VCFs ${p.vcfs_presentes}/2${inferidos ? ' · genitor inferido por parentes' : ''}`, inferidos ? 'chip-azul' : 'chip-aviso', 'dna');
  }
  function vazio(texto, ic) { return el('div', { class: 'cartao vazio' }, icone(ic || 'info'), el('p', { text: texto })); }

  // ---------------------------------------------------------------------------------------------
  // Tabelas, abas, gráficos
  // ---------------------------------------------------------------------------------------------
  function tabela(colunas, linhas, opcoes = {}) { // opcoes.blocos: no celular, cada linha vira um bloco rotulado
    const thead = el('thead', {}, el('tr', {}, colunas.map((c) => el('th', { scope: 'col', class: c.num ? 'num' : '' }, c.rotulo))));
    const tbody = el('tbody', {}, linhas.map((l) => el('tr', {}, colunas.map((c) => {
      const v = typeof c.valor === 'function' ? c.valor(l) : l[c.chave];
      const texto = v instanceof Node ? null : fmtCelula(v);
      return el('td', { class: `${c.num ? 'num' : ''} ${c.classe || ''} ${texto !== null && texto.length > 80 ? 'texto-longo' : ''}`.trim(), 'data-rotulo': c.rotulo }, texto === null ? v : texto);
    }))));
    const t = el('table', {}, opcoes.legenda ? el('caption', { text: opcoes.legenda }) : null, thead, tbody);
    return el('div', { class: `tabela-envoltorio ${opcoes.blocos ? 'tabela-blocos' : ''}` }, t);
  }
  // Rótulos das colunas mostradas na tela; os CSV e o relatório mantêm os nomes técnicos. Sufixos _q025/_q975 viram
  // "limite inferior/superior". Coluna fora do dicionário: primeira letra maiúscula e sem sublinhado.
  const ROTULOS_TABELA_CLINICA = {
    // identificação
    AMOSTRA: 'Amostra', GENE: 'Gene', CROMOSSOMO: 'Cromossomo', POSICAO: 'Posição', REF: 'Alelo de referência', ALT: 'Alelo alternativo',
    ID: 'Identificador', TIPO: 'Tipo de variante', DOSAGEM: 'Dosagem (cópias do alelo)', REPETICOES: 'Repetições', CLASSE: 'Classe',
    CLNSIG: 'Significado clínico (ClinVar)', ESTRELAS: 'Estrelas de revisão', NOME_CURTO: 'Variante', HERANCA: 'Herança',
    REGRA_QUALIFICADA: 'Aceita pela regra qualificada', FONTE_ANOTACAO: 'Fonte da anotação', VARIANTE: 'Variante', RS: 'Identificador rs',
    FONTE: 'Fonte', DESCARTADO: 'Descartado', OBSERVACAO: 'Observação', UNIDADE: 'Unidade', PARAMETRO: 'Parâmetro',
    // dosagem dos genitores e transmissão
    DOSAGEM_MAE: 'Dosagem da mãe', DOSAGEM_PAI: 'Dosagem do pai', REPETICOES_MAE: 'Repetições da mãe', REPETICOES_PAI: 'Repetições do pai',
    P_PORTADOR_EXATO: 'Probabilidade de ser portador (cálculo exato)', P_PORTADOR_MC: 'Probabilidade de ser portador (Monte Carlo)',
    P_PORTADOR_PYMC: 'Probabilidade de ser portador (PyMC)', P_PORTADOR_NUMPY: 'Probabilidade de ser portador (NumPy)',
    EP_PORTADOR: 'Erro padrão da probabilidade de ser portador', P_PORTADOR_CONDICIONAL: 'Probabilidade de ser portador, sem sintomas',
    ALELO_MATERNO: 'Alelo materno', ALELO_MATERNO_TRANSMITIDO: 'Alelo materno transmitido', CLASSE_MATERNO: 'Classe do alelo materno',
    ALELO_PATERNO: 'Alelo paterno', ALELO_PATERNO_TRANSMITIDO: 'Alelo paterno transmitido', CLASSE_PATERNO: 'Classe do alelo paterno',
    MAIOR_ALELO_DESCENDENTE: 'Maior alelo do descendente', CLASSE_DESCENDENTE: 'Classe do descendente', PROBABILIDADE: 'Probabilidade',
    // genitor inferido por parentes
    GENITOR_INFERIDO: 'Genitor inferido', PARENTES_E_DOSAGENS: 'Parentes e dosagens', PRIOR_DOS_AVOS_SEM_EXAME: 'Probabilidade a priori dos avós sem exame',
    SITUACAO_CLINICA: 'Situação clínica', P_DOSAGEM_0_GENOTIPOS: 'Probabilidade de dosagem 0 (só genótipos)',
    P_DOSAGEM_1_GENOTIPOS: 'Probabilidade de dosagem 1 (só genótipos)', P_DOSAGEM_2_GENOTIPOS: 'Probabilidade de dosagem 2 (só genótipos)',
    P_GENITOR_PORTADOR_GENOTIPOS: 'Probabilidade de o genitor ser portador (só genótipos)', P_DOSAGEM_0_CONDICIONADA: 'Probabilidade de dosagem 0 (com a situação clínica)',
    P_DOSAGEM_1_CONDICIONADA: 'Probabilidade de dosagem 1 (com a situação clínica)', P_DOSAGEM_2_CONDICIONADA: 'Probabilidade de dosagem 2 (com a situação clínica)',
    P_GENITOR_PORTADOR_CONDICIONADA: 'Probabilidade de o genitor ser portador (com a situação clínica)', PENETRANCIA_MEDIA_A_PRIORI: 'Penetrância média a priori',
    PENETRANCIA_MEDIA_A_POSTERIORI: 'Penetrância média a posteriori', P_DESCENDENTE_PORTADOR: 'Probabilidade de o descendente ser portador',
    // aderência entre os motores
    N: 'N (tamanho da amostra)', DESVIO_PORTADOR_PYMC_EM_EP: 'Desvio da probabilidade de portador, PyMC (em erros padrão)',
    DESVIO_PORTADOR_NUMPY_EM_EP: 'Desvio da probabilidade de portador, NumPy (em erros padrão)', P_MANIFESTA: 'Probabilidade de manifestar', P_MANIFESTA_EXATO: 'Probabilidade de manifestar (cálculo exato)',
    P_MANIFESTA_MC: 'Probabilidade de manifestar (Monte Carlo)', P_MANIFESTA_PYMC: 'Probabilidade de manifestar (PyMC)', P_MANIFESTA_NUMPY: 'Probabilidade de manifestar (NumPy)',
    EP_MANIFESTA: 'Erro padrão da probabilidade de manifestar', DESVIO_MANIFESTA_PYMC_EM_EP: 'Desvio da probabilidade de manifestar, PyMC (em erros padrão)',
    DESVIO_MANIFESTA_NUMPY_EM_EP: 'Desvio da probabilidade de manifestar, NumPy (em erros padrão)', QUI2_GENOTIPO_PYMC: 'Qui-quadrado do genótipo (PyMC)',
    VALOR_P_GENOTIPO_PYMC: 'Valor-p do genótipo (PyMC)', QUI2_GENOTIPO_NUMPY: 'Qui-quadrado do genótipo (NumPy)', VALOR_P_GENOTIPO_NUMPY: 'Valor-p do genótipo (NumPy)',
    IDADE_MEDIANA_EXATA: 'Idade mediana de início (cálculo exato)', IDADE_MEDIANA_MC: 'Idade mediana de início (Monte Carlo)', IDADE_MEDIANA_PYMC: 'Idade mediana de início (PyMC)',
    IDADE_MEDIANA_NUMPY: 'Idade mediana de início (NumPy)', IDADE_P10_MC: 'Idade de início, percentil 10 (Monte Carlo)', IDADE_P90_MC: 'Idade de início, percentil 90 (Monte Carlo)',
    PENETRANCIA_MEDIA: 'Penetrância média', PENETRANCIA: 'Penetrância',
    'FRAÇÃO QUE MANIFESTA EM ALGUM MOMENTO (SEM LIMITE DE IDADE)': 'Fração que manifesta em algum momento (sem limite de idade)',
    // risco condicional pela idade atual
    IDADE_ATUAL: 'Idade atual', RISCO_10_ANOS: 'Risco nos próximos 10 anos', RISCO_20_ANOS: 'Risco nos próximos 20 anos',
    RISCO_VITALICIO: 'Risco vitalício', RISCO_RESIDUAL: 'Risco a partir da idade atual', RISCO_RESIDUAL_KM: 'Risco a partir da idade atual (Kaplan-Meier)', RISCO_10_ANOS_KM: 'Risco nos próximos 10 anos (Kaplan-Meier)',
    RISCO_20_ANOS_KM: 'Risco nos próximos 20 anos (Kaplan-Meier)', RISCO_VITALICIO_KM: 'Risco vitalício (Kaplan-Meier)',
    // recuperação dos parâmetros (aba Verificações): nomes do modelo com explicação curta
    N_PORTADORES: 'Portadores simulados', EVENTOS: 'Eventos (manifestações)', PI_ENTRADA: 'Penetrância (π) de entrada', LAMBDA_ENTRADA: 'Escala da Weibull (λ) de entrada',
    RHO_ENTRADA: 'Forma da Weibull (ρ) de entrada', DELTA_SEXO: 'Efeito do sexo sobre a escala (δ)', PI_LIFELINES: 'Penetrância (π) recuperada (Lifelines)',
    LAMBDA_LIFELINES: 'Escala da Weibull (λ) recuperada (Lifelines)', RHO_LIFELINES: 'Forma da Weibull (ρ) recuperada (Lifelines)', ERRO_REL_PI: 'Erro relativo da penetrância (π)', ERRO_REL_LAMBDA: 'Erro relativo da escala (λ)',
    ERRO_REL_RHO: 'Erro relativo da forma (ρ)', WEIBULL_LAMBDA_MANIFESTANTES: 'Escala da Weibull (λ), só manifestantes', WEIBULL_RHO_MANIFESTANTES: 'Forma da Weibull (ρ), só manifestantes',
    MEDIANA_WEIBULL_MANIFESTANTES: 'Idade mediana da Weibull, só manifestantes',
    // Kaplan-Meier, Cox e tornado
    MEDIANA_SOBREVIVENCIA: 'Idade mediana de sobrevivência', IDADE_90PCT_DO_RISCO: 'Idade em que 90 % do risco se acumula', COX: 'Modelo de Cox',
    CONCORDANCIA: 'Concordância', LOG_VEROSSIMILHANCA_PARCIAL: 'Log-verossimilhança parcial', FRACAO_CURA_LIFELINES: 'Fração de cura (Lifelines)',
    DIF_MAX_COX_CURA_MISTA: 'Diferença máxima entre Cox e cura mista', DIF_MAX_COX_KM: 'Diferença máxima entre Cox e Kaplan-Meier',
    VALOR_BASE: 'Valor base', VALOR_BAIXO: 'Valor baixo', VALOR_ALTO: 'Valor alto', RISCO_BASE: 'Risco no valor base', RISCO_BAIXO: 'Risco no valor baixo',
    RISCO_ALTO: 'Risco no valor alto', VARIACAO_RISCO: 'Variação do risco', MEDIANA_BASE: 'Idade mediana no valor base', MEDIANA_BAIXA: 'Idade mediana no valor baixo',
    MEDIANA_ALTA: 'Idade mediana no valor alto', VARIACAO_MEDIANA_ANOS: 'Variação da idade mediana (anos)', PROVISORIO: 'Valor provisório',
  };
  function rotuloTabelaClinica(coluna) {
    const nome = coluna.toUpperCase();
    const limite = nome.match(/_Q(025|975)$/);
    if (limite) return `${rotuloTabelaClinica(coluna.slice(0, -5))}, limite ${limite[1] === '025' ? 'inferior' : 'superior'}`;
    if (ROTULOS_TABELA_CLINICA[nome]) return ROTULOS_TABELA_CLINICA[nome];
    // colunas S(40), IC95 S(40), S_cox(50), HR[...]: já legíveis; só ganham explicação quando o prefixo é conhecido
    const sobrev = coluna.match(/^(IC95 )?S(?:_(cox|cura_mista|km|analitico))?\((\d+|horizonte)\)$/);
    if (sobrev) {
      const metodo = { cox: ' (Cox)', cura_mista: ' (cura mista)', km: ' (Kaplan-Meier)', analitico: ' (analítico)' }[sobrev[2]] || '';
      return `${sobrev[1] ? 'Intervalo de 95 % da sobrevivência' : 'Sobrevivência'}${metodo} ${sobrev[3] === 'horizonte' ? 'no horizonte' : `aos ${sobrev[3]} anos`}`;
    }
    const covariavel = coluna.match(/^(IC95 HR|HR|p_riscos_proporcionais|p)\[(.+)\]$/); // modelo de Cox: uma coluna por covariável
    if (covariavel) {
      const base = { 'IC95 HR': 'Intervalo de 95 % da razão de risco (HR)', HR: 'Razão de risco (HR)', p_riscos_proporcionais: 'Valor-p da proporcionalidade dos riscos', p: 'Valor-p' }[covariavel[1]];
      return `${base}, ${covariavel[2]}`;
    }
    if (!/[_]/.test(coluna) && !/^[A-Z0-9 ]+$/.test(coluna) && /^[A-ZÁÉÍÓÚÂÊÔÃÕÇ]/.test(coluna)) return coluna;
    const texto = coluna.toLowerCase().replaceAll('_', ' ');
    return texto[0].toUpperCase() + texto.slice(1);
  }
  // A citação ao texto do TCC fica no relatório e na Ajuda; nas abas clínicas ela sai do corpo mostrado.
  function semCitacaoTCC(texto) {
    return texto.replace(/\s*\(TCC [\d.]+\)/g, '').replace(/\(TCC [\d.]+;\s*/g, '(').replace(/ do TCC [\d.]+/g, ' do modelo').replace(/\s*TCC [\d.]+/g, '');
  }
  function tituloClinico(titulo) { return semCitacaoTCC(titulo); }
  function tabelaRegistros(t, clinica = false) { // tabela vinda do pipeline: {nome, legenda, nota, colunas, linhas}
    const colunas = t.colunas.map((c) => ({ rotulo: rotuloTabelaClinica(c), chave: c, num: t.linhas.length > 0 && typeof t.linhas[0][c] === 'number' }));
    return el('div', {}, tabela(colunas, t.linhas, { legenda: clinica ? tituloClinico(t.legenda) : t.legenda }), t.nota ? el('p', { class: 'pequeno texto-suave', text: localizarNumeros(clinica ? semCitacaoTCC(t.nota) : t.nota) }) : null);
  }
  function abas(lista, idBase, opcoes = {}) {
    const tablist = el('div', { role: 'tablist', 'aria-label': opcoes.rotulo || 'Seções do resultado' });
    const paineis = [];
    const botoes = lista.map((aba, i) => {
      const b = el('button', { role: 'tab', type: 'button', id: `${idBase}-aba-${i}`, 'aria-selected': i === 0 ? 'true' : 'false', 'aria-controls': `${idBase}-painel-${i}`, tabindex: i === 0 ? '0' : '-1' }, aba.icone ? icone(aba.icone) : null, aba.rotulo);
      const p = el('section', { role: 'tabpanel', id: `${idBase}-painel-${i}`, 'aria-labelledby': b.id, tabindex: '0', hidden: i !== 0 });
      paineis.push(p);
      let montado = false;
      const selecionar = () => {
        botoes.forEach((o, j) => { o.setAttribute('aria-selected', j === i ? 'true' : 'false'); o.tabIndex = j === i ? 0 : -1; paineis[j].hidden = j !== i; });
        if (!montado) { montado = true; p.append(aba.conteudo()); }
      };
      b.addEventListener('click', selecionar);
      b.addEventListener('keydown', (ev) => {
        const n = botoes.length; let alvo = null;
        if (ev.key === 'ArrowRight') alvo = (i + 1) % n; else if (ev.key === 'ArrowLeft') alvo = (i - 1 + n) % n;
        else if (ev.key === 'Home') alvo = 0; else if (ev.key === 'End') alvo = n - 1;
        if (alvo !== null) { ev.preventDefault(); botoes[alvo].focus(); botoes[alvo].click(); }
      });
      if (i === 0) setTimeout(selecionar, 0);
      return b;
    });
    tablist.append(...botoes);
    const raiz = el('div', { class: `abas ${opcoes.classe || ''}` }, tablist, ...paineis);
    raiz.selecionar = (i) => botoes[i].click();
    return raiz;
  }

  function graficoLinhas(opcoes) {
    // opcoes: {titulo, x, series: [{nome, y, classe}], banda: {inferior, superior, nome}, yRotulo, yMax, formatoY, tabela (details)}
    const L = 640, A = 300, mE = 52, mD = 16, mT = 14, mB = 44;
    const x = opcoes.x;
    const xMax = Math.max(...x), xMin = Math.min(...x);
    let yMax = opcoes.yMax;
    if (yMax === undefined) {
      const todos = [];
      for (const s of opcoes.series) todos.push(...s.y.filter((v) => v !== null));
      if (opcoes.banda) todos.push(...opcoes.banda.superior.filter((v) => v !== null));
      yMax = Math.max(0.01, ...todos) * 1.1;
      if (yMax > 0.9 && yMax < 1.15 && !opcoes.livre) yMax = 1;
    }
    const sx = (v) => mE + ((v - xMin) / (xMax - xMin || 1)) * (L - mE - mD);
    const sy = (v) => A - mB - (v / yMax) * (A - mT - mB);
    const svg = svgEl('svg', { viewBox: `0 0 ${L} ${A}`, role: 'img', 'aria-label': opcoes.descricao || opcoes.titulo });
    svg.append(svgEl('title', {}, opcoes.titulo));
    for (let i = 0; i <= 4; i++) {
      const v = (yMax * i) / 4;
      svg.append(svgEl('line', { x1: mE, x2: L - mD, y1: sy(v), y2: sy(v), class: 'grade-linha' }));
      svg.append(svgEl('text', { x: mE - 6, y: sy(v) + 4, 'text-anchor': 'end', class: 'rotulo-eixo' }, (opcoes.formatoY || ((q) => fmtPct(q, 0)))(v)));
    }
    for (let v = Math.ceil(xMin / 10) * 10; v <= xMax; v += 10) {
      svg.append(svgEl('line', { x1: sx(v), x2: sx(v), y1: mT, y2: A - mB, class: 'grade-linha' }));
      svg.append(svgEl('text', { x: sx(v), y: A - mB + 16, 'text-anchor': 'middle', class: 'rotulo-eixo' }, String(v)));
    }
    svg.append(svgEl('line', { x1: mE, x2: L - mD, y1: A - mB, y2: A - mB, class: 'eixo' }), svgEl('line', { x1: mE, x2: mE, y1: mT, y2: A - mB, class: 'eixo' }));
    svg.append(svgEl('text', { x: (mE + L - mD) / 2, y: A - 6, 'text-anchor': 'middle', class: 'rotulo-eixo titulo-eixo' }, opcoes.xRotulo || 'Idade (anos)'));
    if (opcoes.banda) {
      const pts = [];
      x.forEach((xv, i) => { if (opcoes.banda.superior[i] !== null) pts.push(`${sx(xv)},${sy(Math.min(yMax, opcoes.banda.superior[i]))}`); });
      for (let i = x.length - 1; i >= 0; i--) if (opcoes.banda.inferior[i] !== null) pts.push(`${sx(x[i])},${sy(opcoes.banda.inferior[i])}`);
      svg.append(svgEl('polygon', { points: pts.join(' '), class: 'banda' }));
    }
    opcoes.series.forEach((s) => {
      const d = x.map((xv, i) => (s.y[i] === null ? null : `${i === 0 ? 'M' : 'L'}${sx(xv)},${sy(Math.min(yMax, s.y[i]))}`)).filter(Boolean).join(' ');
      svg.append(svgEl('path', { d, class: s.classe || 'curva' }));
    });
    const legenda = el('div', { class: 'grafico-legenda' });
    for (const s of opcoes.series) legenda.append(el('span', { class: 'legenda-item' }, el('span', { class: `amostra-linha ${s.classe || ''}`, 'aria-hidden': 'true' }), s.nome));
    if (opcoes.banda) legenda.append(el('span', { class: 'legenda-item' }, el('span', { class: 'amostra-banda', 'aria-hidden': 'true' }), opcoes.banda.nome));
    if (opcoes.tabela) {
      legenda.append(el('button', { type: 'button', class: 'botao botao-link ver-tabela', onclick: () => { opcoes.tabela.open = true; opcoes.tabela.querySelector('summary').focus(); } }, 'Ver dados em tabela ', icone('seta-dir')));
    }
    return el('figure', { class: 'grafico' }, el('h3', { text: opcoes.titulo }), svg, legenda, opcoes.tabela || null);
  }
  function tabelaAlternativa(legenda, x, colunas) { // colunas: [{rotulo, y, formato}]
    const linhas = x.map((xv, i) => { const l = { t: xv }; colunas.forEach((c, j) => { l[`c${j}`] = c.y[i]; }); return l; });
    const defs = [{ rotulo: 'Idade (anos)', chave: 't', num: true }, ...colunas.map((c, j) => ({ rotulo: c.rotulo, valor: (l) => (c.formato || fmtPct)(l[`c${j}`]), num: true }))];
    return el('details', {}, el('summary', { text: `Dados em tabela: ${legenda}` }), tabela(defs, linhas.filter((l, i) => i % 5 === 0 || i === linhas.length - 1)));
  }

  // ---------------------------------------------------------------------------------------------
  // Roteamento
  // ---------------------------------------------------------------------------------------------
  const ROTAS = [
    { re: /^#\/entrar$/, tela: telaEntrar, publica: true, dividida: true },
    { re: /^#\/criar-conta$/, tela: telaCriarConta, publica: true, dividida: true },
    { re: /^#\/primeiro-acesso$/, tela: telaPrimeiroAcesso, publica: true },
    { re: /^#\/privacidade$/, tela: telaPrivacidade, publica: true },
    { re: /^#\/ajuda$/, tela: telaAjuda, publica: true },
    { re: /^#\/inicio$/, tela: telaInicio },
    { re: /^#\/situacao$/, tela: telaSituacao, sessao: true },
    { re: /^#\/trocar-senha$/, tela: telaTrocarSenha, sessao: true },
    { re: /^#\/minha-conta$/, tela: telaMinhaConta, sessao: true, permissao: 'conta.gerir' },
    { re: /^#\/pacientes$/, tela: telaPacientes, permissao: 'pacientes.gerir' },
    { re: /^#\/pacientes\/novo$/, tela: telaPacienteFormulario, permissao: 'pacientes.gerir' },
    { re: /^#\/pacientes\/(\d+)$/, tela: telaFicha, permissao: 'pacientes.gerir' },
    { re: /^#\/pacientes\/(\d+)\/editar$/, tela: telaPacienteFormulario, permissao: 'pacientes.gerir' },
    { re: /^#\/analises$/, tela: telaAnalises, permissao: 'analises.executar' },
    { re: /^#\/analises\/(\d+)\/(\d+)$/, tela: telaResultadoGuardado, permissao: 'analises.executar' },
    { re: /^#\/analise(?:\?paciente=(\d+)(?:&descendente=(\d+|todos))?)?$/, tela: telaAnalise, permissao: 'analises.executar' },
    { re: /^#\/resultado\/([A-Za-z0-9_-]+)(?:\?par=([A-Za-z0-9_-]+))?$/, tela: telaResultado, permissao: 'analises.executar' },
    { re: /^#\/pesquisa\/casos$/, tela: telaCasos, permissao: 'pesquisa.casos' },
    { re: /^#\/modelo$/, tela: telaModelo, permissao: 'modelo.ver' },
    { re: /^#\/artefato$/, tela: telaArtefato, permissao: 'artefato.executar' },
    { re: /^#\/artefato\/([0-9]{14}-[0-9a-f]{6})$/, tela: telaTarefa, permissao: 'artefato.executar' },
    { re: /^#\/base$/, tela: telaBase, permissao: 'base.ver' },
    { re: /^#\/admin\/pendentes$/, tela: telaPendentes, permissao: 'usuarios.gerir' },
    { re: /^#\/admin\/pendentes\/(\d+)$/, tela: telaPendente, permissao: 'usuarios.gerir' },
    { re: /^#\/admin\/usuarios$/, tela: telaUsuarios, permissao: 'usuarios.gerir' },
    { re: /^#\/admin\/auditoria$/, tela: telaAuditoria, permissao: 'auditoria.ver_tudo' },
  ];
  function navegar(hash) { if (location.hash === hash) aoMudarRota(); else location.hash = hash; }
  function primeiroAcessoPendente() { const pa = estado.sistema && estado.sistema.primeiro_acesso; return !!(pa && (pa.administrador || pa.demonstracao)); }
  function inicioPorPapel() {
    if (!estado.eu) return primeiroAcessoPendente() ? '#/primeiro-acesso' : '#/entrar';
    if (estado.eu.trocar_senha) return '#/trocar-senha';
    if (!estado.eu.verificado) return '#/situacao';
    return '#/inicio';
  }
  async function aoMudarRota() {
    const hash = location.hash || '#/';
    if (hash === '#/' || hash === '#') { navegar(inicioPorPapel()); return; }
    let rota = null, m = null;
    for (const r of ROTAS) { m = hash.match(r.re); if (m) { rota = r; break; } }
    renderizarCasca();
    abrirGavetaSilenciosa();
    document.body.classList.toggle('tela-dividida', !!(rota && rota.dividida && !estado.eu));
    limparAvisos();
    definirTrilha([[areaDoPapel()]]);
    if (estado.avisoPendente) { avisar(/^(Você saiu|Cadastro|Registro|VCF|Descendente|Filho|Dados|Paciente|Usuário|Conta|Consentimento|Versão registrada|Base enviada|Download concluído|Execução removida|\d)/.test(estado.avisoPendente) || /Nova situação/.test(estado.avisoPendente) ? 'sucesso' : 'aviso', estado.avisoPendente); estado.avisoPendente = null; }
    const area = el('div', { class: 'tela' }); // contêiner próprio por navegação: uma tela anterior ainda carregando não escreve sobre a atual
    limpar(main()).append(area);
    if (!rota) { telaNaoEncontrada(area); return; }
    if (!rota.publica && !estado.eu) { estado.avisoPendente = 'Entre para continuar.'; navegar('#/entrar'); return; }
    if (!rota.publica && estado.eu.trocar_senha && hash !== '#/trocar-senha') { navegar('#/trocar-senha'); return; }
    if (rota.publica && estado.eu && (hash === '#/entrar' || hash === '#/criar-conta' || hash === '#/primeiro-acesso')) { navegar(inicioPorPapel()); return; }
    if (!rota.publica && !rota.sessao && !estado.eu.verificado) { navegar('#/situacao'); return; }
    if (rota.permissao && !tem(rota.permissao)) { tela403(area); return; }
    try { await rota.tela(area, m.slice(1)); } catch (e) {
      if (e.status === 403) tela403(area, e.message);
      else if (e.status === 404) telaNaoEncontrada(area, e.message);
      else if (e.status !== 401) { avisar('erro', e.message || 'Erro inesperado.'); }
    }
    main().focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }
  function abrirGavetaSilenciosa() { document.getElementById('lateral').classList.remove('aberta'); document.getElementById('sobreposicao').hidden = true; document.getElementById('botao-menu').setAttribute('aria-expanded', 'false'); }
  function tela403(area, mensagem) {
    limpar(area);
    definirTitulo('Sem acesso');
    area.append(el('div', { class: 'cartao vazio' }, icone('escudo'), el('h1', { text: 'Seu perfil não tem acesso a esta função' }),
      el('p', { text: mensagem || 'Esta tela é restrita a outro papel. Se acha que deveria ter acesso, fale com o administrador.' }),
      el('p', {}, linkBotao('Voltar ao início', inicioPorPapel(), { classe: 'botao-secundario', icone: 'casa' }))));
  }
  function telaNaoEncontrada(area, mensagem) {
    definirTitulo('Não encontrado');
    area.append(el('div', { class: 'cartao vazio' }, icone('alerta'), el('h1', { text: 'Página não encontrada' }), el('p', { text: mensagem || 'O endereço não existe ou o registro não está disponível para você.' }), el('p', {}, linkBotao('Voltar ao início', '#/', { classe: 'botao-secundario', icone: 'casa' }))));
  }

  // ---------------------------------------------------------------------------------------------
  // Telas públicas
  // ---------------------------------------------------------------------------------------------
  function helice() {
    const svg = svgEl('svg', { class: 'helice', viewBox: '0 0 200 320', 'aria-hidden': 'true', focusable: 'false' });
    for (let i = 0; i < 2; i++) svg.append(svgEl('path', { d: i === 0 ? 'M40 0c0 80 120 80 120 160S40 240 40 320' : 'M160 0c0 80-120 80-120 160s120 80 120 160', fill: 'none', stroke: '#ffffff', 'stroke-width': '4' }));
    for (let y = 20; y < 320; y += 40) svg.append(svgEl('path', { d: `M${100 - 45 * Math.abs(Math.sin((y / 320) * Math.PI * 2))} ${y}h${90 * Math.abs(Math.sin((y / 320) * Math.PI * 2))}`, stroke: '#ffffff', 'stroke-width': '3.2' }));
    return svg;
  }
  function logoSvg() { // a mesma dupla hélice do index.html (barra lateral, topo e favicon)
    const svg = svgEl('svg', { viewBox: '0 0 48 48', 'aria-hidden': 'true', focusable: 'false', class: 'logo' });
    svg.append(svgEl('path', { d: 'M31 3C11 10 11 20 24 24s13 14-7 21M17 3c20 7 20 17 7 21s-13 14 7 21', fill: 'none', stroke: 'currentColor', 'stroke-width': '3.2', 'stroke-linecap': 'round' }),
      svgEl('path', { d: 'M19 10h10M17.5 15.5h13M17.5 32.5h13M19 38h10', stroke: 'currentColor', 'stroke-width': '2.4', 'stroke-linecap': 'round', opacity: '.9' }));
    return svg;
  }
  function painelNavy(titulo, texto) {
    return el('section', { class: 'painel-navy', 'aria-label': 'Apresentação' },
      el('a', { class: 'marca', href: '#/ajuda' }, el('span', { class: 'marca-linha' }, logoSvg(), el('span', { class: 'marca-nome', text: 'EloSense' })), el('span', { class: 'marca-sub', text: 'Plataforma clínica' })),
      el('h2', { text: titulo }), el('p', { text: texto }), helice());
  }
  async function telaEntrar(area) {
    definirTitulo('Entrar');
    const email = campo({ nome: 'email', rotulo: 'E-mail', tipo: 'email', obrigatorio: true, icone: 'email', atributos: { autocomplete: 'username', placeholder: 'nome@instituicao.com.br' } });
    const senha = campo({ nome: 'senha', rotulo: 'Senha', tipo: 'password', obrigatorio: true, icone: 'cadeado', mostrarSenha: true, atributos: { autocomplete: 'current-password' } });
    const campos = { email, senha };
    const form = el('form', { novalidate: true, onsubmit: async (ev) => {
      ev.preventDefault();
      const erros = {};
      if (!email.valor().trim()) erros.email = 'Informe o e-mail.';
      if (!senha.valor()) erros.senha = 'Informe a senha.';
      if (Object.keys(erros).length) { aplicarErros(campos, erros); return; }
      try {
        const eu = await api('POST', '/api/contas/login', { json: { email: email.valor().trim(), senha: senha.valor() }, semRedirecionar: true });
        estado.eu = eu; estado.csrf = eu.csrf; estado.opcoes = null;
        renderizarCasca();
        navegar(inicioPorPapel());
      } catch (e) { aplicarErros(campos, e.campos, e.message); senha.input.value = ''; }
    } }, email.no, senha.no, el('div', { class: 'acoes' }, botao('Entrar', { tipo: 'submit', classe: 'botao-largo' })),
      el('p', { class: 'texto-suave centro' }, 'Ainda não tem uma conta? ', el('a', { href: '#/criar-conta', text: 'Criar conta' })),
      primeiroAcessoPendente() ? el('p', { class: 'texto-suave centro' }, 'Plataforma recém-instalada? ', el('a', { href: '#/primeiro-acesso', text: 'Fazer o primeiro acesso' })) : null);
    area.append(el('div', { class: 'dividida' }, painelNavy('Ciência e cuidado, conectados.', 'Apoio ao aconselhamento genético preditivo.'),
      el('section', { class: 'painel-form', 'aria-label': 'Acesso' }, el('div', { class: 'caixa' }, el('p', { class: 'sobretitulo', text: 'Acesso profissional' }), el('h1', { text: 'Bem-vindo de volta' }), el('p', { class: 'subtitulo', text: 'Entre para acessar a plataforma.' }), form),
        el('p', { class: 'rodape-form' }, el('a', { href: '#/privacidade', text: 'Privacidade e proteção de dados' })))));
    email.input.focus();
  }

  async function telaCriarConta(area) {
    definirTitulo('Criar conta');
    const sis = estado.sistema || {};
    const versoes = sis.versoes_termos || {};
    let etapa = 0;
    const dados = { papel_pretendido: 'MEDICO', medico: { tipo: 'CRM' }, pesquisador: { tipo: 'INSTITUCIONAL' } };
    const raiz = el('div');
    const nomesEtapas = ['Dados pessoais', 'Dados profissionais', 'Senha e aceites'];
    area.append(el('div', { class: 'dividida' }, painelNavy('Crie sua conta profissional.', 'Toda conta nasce pendente e é liberada após verificação manual pelo administrador. Pedimos apenas o indispensável.'),
      el('section', { class: 'painel-form', 'aria-label': 'Cadastro' }, el('div', { class: 'caixa caixa-larga' }, el('p', { class: 'sobretitulo', text: 'Acesso profissional' }), el('h1', { text: 'Criar conta' }), raiz),
        el('p', { class: 'rodape-form' }, el('a', { href: '#/entrar', text: 'Já tem conta? Entrar' })))));

    function render() {
      limpar(raiz);
      raiz.append(etapas(nomesEtapas, etapa));
      if (etapa === 0) renderEtapa1(); else if (etapa === 1) renderEtapa2(); else renderEtapa3();
      const h2 = raiz.querySelector('h2'); if (h2) { h2.tabIndex = -1; h2.focus(); }
    }
    function renderEtapa1() {
      const nome = campo({ nome: 'nome', rotulo: 'Nome completo', obrigatorio: true, valor: dados.nome, icone: 'pessoa', atributos: { autocomplete: 'name' } });
      const cpf = campo({ nome: 'cpf', rotulo: 'CPF', obrigatorio: true, valor: dados.cpf, dica: 'Só números; os dígitos verificadores são conferidos. Fica cifrado e é exibido mascarado.', atributos: { inputmode: 'numeric', autocomplete: 'off' } });
      cpf.input.addEventListener('input', () => { cpf.input.value = mascararCpf(cpf.input.value); });
      const email = campo({ nome: 'email', rotulo: 'E-mail', tipo: 'email', obrigatorio: true, valor: dados.email, icone: 'email', atributos: { autocomplete: 'email' } });
      const campos = { nome, cpf, email };
      raiz.append(el('form', { novalidate: true, onsubmit: (ev) => {
        ev.preventDefault();
        const erros = {};
        if (nome.valor().trim().length < 3) erros.nome = 'Informe o nome completo.';
        if (!cpfValido(cpf.valor())) erros.cpf = 'CPF inválido: confira os dígitos.';
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email.valor().trim())) erros.email = 'Informe um e-mail válido.';
        if (Object.keys(erros).length) { aplicarErros(campos, erros); return; }
        Object.assign(dados, { nome: nome.valor().trim(), cpf: cpf.valor(), email: email.valor().trim() });
        etapa = 1; render();
      } }, secaoNumerada(1, 'Dados pessoais', nome.no, el('div', { class: 'grade-campos' }, cpf.no, email.no)), el('div', { class: 'acoes acoes-direita' }, botao('Continuar', { tipo: 'submit', icone: 'seta-dir' }))));
    }
    function renderEtapa2() {
      const areaPapel = el('div');
      let campos = {};
      const papel = cartoesOpcao({ nome: 'papel_pretendido', rotulo: 'Papel pretendido', valor: dados.papel_pretendido, onchange: (v) => { dados.papel_pretendido = v; renderCamposPapel(); }, opcoes: [
        { valor: 'MEDICO', titulo: 'Médico(a) ou aconselhador(a) genético(a)', descricao: 'Cadastra atendimentos, anexa VCFs e executa análises; vê só os próprios registros.', icone: 'pessoa' },
        { valor: 'PESQUISADOR', titulo: 'Pesquisador(a)', descricao: 'Consulta o modelo e casos pseudonimizados com filtros e exportação. Nunca vê dado identificável.', icone: 'microscopio' },
      ] });
      function renderCamposPapel() {
        limpar(areaPapel); campos = {};
        if (dados.papel_pretendido === 'MEDICO') {
          const m = dados.medico;
          const tipo = el('fieldset', {}, el('legend', { text: 'Registro profissional' }));
          for (const [v, r] of [['CRM', 'Tenho CRM'], ['ACONSELHADOR', 'Aconselhador(a) genético(a) sem CRM (informo formação e instituição)']]) {
            const mk = marcacao({ nome: 'medico.tipo', tipo: 'radio', valor: v, rotulo: r, marcado: m.tipo === v });
            mk.input.addEventListener('change', () => { m.tipo = v; renderCamposPapel(); });
            tipo.append(mk.no);
          }
          areaPapel.append(tipo);
          if (m.tipo === 'CRM') {
            campos['medico.crm'] = campo({ nome: 'medico.crm', rotulo: 'Número do CRM', obrigatorio: true, valor: m.crm, dica: 'A conferência do CRM é manual, feita pelo administrador.', atributos: { inputmode: 'numeric' } });
            campos['medico.uf'] = campo({ nome: 'medico.uf', rotulo: 'UF do CRM', tipo: 'select', obrigatorio: true, valor: m.uf || '', opcoes: [['', 'Selecione'], ...UFS.map((u) => [u, u])] });
            areaPapel.append(el('div', { class: 'grade-campos' }, campos['medico.crm'].no, campos['medico.uf'].no));
          } else {
            campos['medico.formacao'] = campo({ nome: 'medico.formacao', rotulo: 'Formação', obrigatorio: true, valor: m.formacao });
            campos['medico.instituicao'] = campo({ nome: 'medico.instituicao', rotulo: 'Instituição', obrigatorio: true, valor: m.instituicao });
            areaPapel.append(el('div', { class: 'grade-campos' }, campos['medico.formacao'].no, campos['medico.instituicao'].no));
          }
          campos['medico.especialidade'] = campo({ nome: 'medico.especialidade', rotulo: 'Especialidade', opcional: true, valor: m.especialidade });
          areaPapel.append(campos['medico.especialidade'].no);
        } else {
          const p = dados.pesquisador;
          campos['pesquisador.tipo'] = campo({ nome: 'pesquisador.tipo', rotulo: 'Tipo', tipo: 'select', valor: p.tipo, opcoes: [['INSTITUCIONAL', 'Institucional'], ['INDEPENDENTE', 'Independente']], dica: 'Vínculo institucional não é obrigatório.' });
          campos['pesquisador.cargo'] = campo({ nome: 'pesquisador.cargo', rotulo: 'Cargo ou condição acadêmica', obrigatorio: true, valor: p.cargo });
          campos['pesquisador.linha_pesquisa'] = campo({ nome: 'pesquisador.linha_pesquisa', rotulo: 'Linha de pesquisa', obrigatorio: true, valor: p.linha_pesquisa });
          campos['pesquisador.instituicao'] = campo({ nome: 'pesquisador.instituicao', rotulo: 'Instituição', opcional: true, valor: p.instituicao });
          campos['pesquisador.grupo'] = campo({ nome: 'pesquisador.grupo', rotulo: 'Grupo de pesquisa', opcional: true, valor: p.grupo });
          campos['pesquisador.orcid'] = campo({ nome: 'pesquisador.orcid', rotulo: 'ORCID', opcional: true, valor: p.orcid, dica: 'Formato 0000-0000-0000-0000. Não aprova automaticamente.' });
          campos['pesquisador.lattes_url'] = campo({ nome: 'pesquisador.lattes_url', rotulo: 'Link do Lattes', opcional: true, valor: p.lattes_url, tipo: 'text' });
          campos['pesquisador.projetos'] = campo({ nome: 'pesquisador.projetos', rotulo: 'Participação em projetos', opcional: true, tipo: 'textarea', valor: p.projetos, linhas: 3 });
          campos['pesquisador.evidencias'] = campo({ nome: 'pesquisador.evidencias', rotulo: 'Evidências (texto e links; sem envio de arquivos)', opcional: true, tipo: 'textarea', valor: p.evidencias, linhas: 3 });
          areaPapel.append(el('div', { class: 'grade-campos' }, campos['pesquisador.tipo'].no, campos['pesquisador.cargo'].no), campos['pesquisador.linha_pesquisa'].no, el('div', { class: 'grade-campos' }, campos['pesquisador.instituicao'].no, campos['pesquisador.grupo'].no), el('div', { class: 'grade-campos' }, campos['pesquisador.orcid'].no, campos['pesquisador.lattes_url'].no), campos['pesquisador.projetos'].no, campos['pesquisador.evidencias'].no);
        }
      }
      renderCamposPapel();
      raiz.append(el('form', { novalidate: true, onsubmit: (ev) => {
        ev.preventDefault();
        const erros = {};
        const v = (k) => (campos[k] ? campos[k].valor().trim() : '');
        if (dados.papel_pretendido === 'MEDICO') {
          if (dados.medico.tipo === 'CRM') { if (!/^\d{4,10}$/.test(v('medico.crm'))) erros['medico.crm'] = 'Informe o número do CRM (só dígitos).'; if (!v('medico.uf')) erros['medico.uf'] = 'Informe a UF do CRM.'; }
          else { if (!v('medico.formacao')) erros['medico.formacao'] = 'Informe a formação.'; if (!v('medico.instituicao')) erros['medico.instituicao'] = 'Informe a instituição.'; }
        } else {
          if (!v('pesquisador.cargo')) erros['pesquisador.cargo'] = 'Informe o cargo ou a condição acadêmica.';
          if (!v('pesquisador.linha_pesquisa')) erros['pesquisador.linha_pesquisa'] = 'Informe a linha de pesquisa.';
          if (v('pesquisador.orcid') && !/^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/.test(v('pesquisador.orcid'))) erros['pesquisador.orcid'] = 'ORCID no formato 0000-0000-0000-0000.';
          if (v('pesquisador.lattes_url') && !/^https?:\/\//.test(v('pesquisador.lattes_url'))) erros['pesquisador.lattes_url'] = 'Informe o link completo (começando por http).';
        }
        if (Object.keys(erros).length) { aplicarErros(campos, erros); return; }
        for (const [k, c] of Object.entries(campos)) { const [grupo, nome] = k.split('.'); dados[grupo][nome] = c.valor().trim() || null; }
        etapa = 2; render();
      } }, secaoNumerada(2, 'Dados profissionais', papel.no, areaPapel), el('div', { class: 'acoes acoes-direita' }, botao('Voltar', { classe: 'botao-secundario', icone: 'seta-esq', onclick: () => { etapa = 0; render(); } }), botao('Continuar', { tipo: 'submit', icone: 'seta-dir' }))));
    }
    function renderEtapa3() {
      const senha = campo({ nome: 'senha', rotulo: 'Senha', tipo: 'password', obrigatorio: true, icone: 'cadeado', mostrarSenha: true, dica: 'Mínimo de 10 caracteres; não pode ser igual ao e-mail nem ao CPF.', atributos: { autocomplete: 'new-password' } });
      const confirma = campo({ nome: 'confirma', rotulo: 'Confirme a senha', tipo: 'password', obrigatorio: true, icone: 'cadeado', mostrarSenha: true, atributos: { autocomplete: 'new-password' } });
      const aceitePriv = marcacao({ nome: 'aceite_privacidade', rotulo: `Li e aceito o aviso de privacidade (versão ${versoes.aviso_privacidade || '—'}).` });
      const aceiteUso = marcacao({ nome: 'aceite_termo_uso', rotulo: `Li e aceito o termo de uso (versão ${versoes.termo_uso || '—'}).` });
      const termo = el('details', {}, el('summary', { text: 'Ler o termo de uso' }), el('ul', {}, ((sis.termo_uso || {}).itens || []).map((t) => el('li', { text: t }))));
      const campos = { senha, confirma, aceite_privacidade: aceitePriv, aceite_termo_uso: aceiteUso };
      raiz.append(el('form', { novalidate: true, onsubmit: async (ev) => {
        ev.preventDefault();
        const erros = {};
        if (senha.valor().length < 10) erros.senha = 'A senha precisa ter pelo menos 10 caracteres.';
        if (confirma.valor() !== senha.valor()) erros.confirma = 'As senhas não coincidem.';
        if (!aceitePriv.valor()) erros.aceite_privacidade = 'É preciso aceitar o aviso de privacidade.';
        if (!aceiteUso.valor()) erros.aceite_termo_uso = 'É preciso aceitar o termo de uso.';
        if (Object.keys(erros).length) { aplicarErros(campos, erros); return; }
        const corpo = { nome: dados.nome, cpf: dados.cpf, email: dados.email, senha: senha.valor(), papel_pretendido: dados.papel_pretendido, aceite_privacidade: true, aceite_termo_uso: true, versao_privacidade: versoes.aviso_privacidade, versao_termo_uso: versoes.termo_uso };
        if (dados.papel_pretendido === 'MEDICO') corpo.medico = dados.medico; else corpo.pesquisador = dados.pesquisador;
        try {
          const r = await api('POST', '/api/contas/cadastro', { json: corpo });
          estado.avisoPendente = r.mensagem; navegar('#/entrar');
        } catch (e) {
          const nossos = {}; const outros = {};
          for (const [k, v] of Object.entries(e.campos)) (campos[k] ? nossos : outros)[k] = v;
          aplicarErros(campos, nossos, Object.keys(outros).length ? `${e.message} ${Object.entries(outros).map(([k, v]) => `${k}: ${v}`).join(' ')} Volte às etapas anteriores para corrigir.` : (Object.keys(nossos).length ? null : e.message));
        }
      } }, secaoNumerada(3, 'Senha e aceites', el('div', { class: 'grade-campos' }, senha.no, confirma.no), el('p', {}, el('a', { href: '#/privacidade', target: '_blank', rel: 'noopener', text: 'Ler o aviso de privacidade (abre em nova aba)' })), termo, aceitePriv.no, aceiteUso.no),
        el('div', { class: 'acoes acoes-direita' }, botao('Voltar', { classe: 'botao-secundario', icone: 'seta-esq', onclick: () => { etapa = 1; render(); } }), botao('Criar conta', { tipo: 'submit', icone: 'check' }))));
    }
    render();
  }

  async function telaPrivacidade(area) {
    definirTitulo('Privacidade e proteção de dados');
    definirTrilha([[areaDoPapel()], ['Privacidade']]);
    const p = await api('GET', '/api/privacidade');
    area.append(cabecalhoTela({ titulo: p.titulo, subtitulo: `Versão ${p.versao}. Lei 13.709/2018 (LGPD).` }));
    const doc = el('div', { class: 'documento' });
    for (const s of p.secoes) {
      const c = el('section', { class: 'cartao' }, el('h2', { text: s.titulo }));
      (s.paragrafos || []).forEach((t) => c.append(el('p', { text: t })));
      if (s.itens) c.append(el('ul', {}, s.itens.map((t) => el('li', { text: t }))));
      doc.append(c);
    }
    const sis = estado.sistema;
    if (sis && sis.termo_uso) doc.append(el('section', { class: 'cartao' }, el('h2', { text: `${sis.termo_uso.titulo} (versão ${sis.termo_uso.versao})` }), el('ul', {}, sis.termo_uso.itens.map((t) => el('li', { text: t })))));
    area.append(doc);
  }

  async function telaAjuda(area) {
    definirTitulo('Ajuda');
    definirTrilha([[areaDoPapel()], ['Ajuda']]);
    const a = await api('GET', '/api/ajuda');
    area.append(cabecalhoTela({ titulo: 'Ajuda', subtitulo: a.descricao }));
    const doc = el('div', { class: 'documento' });
    doc.append(el('section', { class: 'cartao' }, el('h2', { text: 'Quem o EloSense atende: três casos' }),
      el('div', { class: 'casos-ajuda' }, a.casos.map((c) => el('div', { class: 'caso-ajuda' }, chip(`Caso ${c.numero}`, 'chip-azul', c.tipo === 'CASAL' ? 'casal' : c.tipo === 'FAMILIA' ? 'familia' : 'pessoa'), el('h3', { text: c.rotulo.replace(/^Caso \d · /, '') }), el('p', { text: c.descricao }),
        el('p', { class: 'pequeno texto-suave', text: `O resultado responde: ${c.responde.join('; ')}.` }), el('p', { class: 'pequeno texto-suave', text: `Registro: ${c.registro}.` }))))));
    doc.append(el('section', { class: 'cartao' }, el('h2', { text: 'Para quem não se destina' }), el('ul', {}, a.fora_do_escopo.map((t) => el('li', { text: t })))));
    doc.append(el('section', { class: 'cartao' }, el('h2', { text: 'Como se encaixa na prática' }), el('p', { text: a.operacao }), el('ul', {}, a.usos.map((u) => el('li', {}, el('strong', { text: `${u.momento}: ` }), u.texto)))));
    doc.append(el('section', { class: 'cartao' }, el('h2', { text: 'Fluxo de uso' }), el('ol', {}, a.fluxo.map((t) => el('li', { text: t }))),
      el('p', { text: 'O TCC descreve a anotação de variantes (seção 4.2.2), a verificação de qualidade dos VCFs (seção 4.2.3) e a dosagem dos genitores (seção 4.3).' })));
    doc.append(el('section', { class: 'cartao' }, el('h2', { text: 'Perfis de acesso' }), el('ul', {}, a.perfis.map(([p, t]) => el('li', {}, el('strong', { text: `${p}: ` }), t)))));
    doc.append(el('section', { class: 'cartao' }, el('h2', { text: 'Limitação do modelo' }), el('p', { text: a.limitacao }), el('p', {}, el('strong', { text: 'Encarregado pelo tratamento de dados: ' }), `${a.encarregado.nome}; contato: ${a.encarregado.contato}. `, el('a', { href: '#/privacidade', text: 'Aviso de privacidade' }), '.')));
    area.append(doc);
  }

  // ---------------------------------------------------------------------------------------------
  // Início (painel por papel)
  // ---------------------------------------------------------------------------------------------
  function saudacao() {
    const h = new Date().getHours();
    return h < 12 ? 'Bom dia' : h < 18 ? 'Boa tarde' : 'Boa noite';
  }
  function indicadorLink(def) { // indicador clicável
    const a = el('a', { class: `indicador ${def.destaque ? 'indicador-destaque' : ''}`, href: def.href }, el('div', { class: 'indicador-topo' }, el('span', { class: 'indicador-icone' }, icone(def.icone || 'info')), el('span', { class: 'indicador-rotulo', text: def.rotulo })), el('div', { class: 'indicador-valor', text: def.valor }), def.detalhe ? el('div', { class: 'indicador-detalhe', text: def.detalhe }) : null);
    return a;
  }
  async function telaInicio(area) {
    definirTitulo('Início');
    definirTrilha([[areaDoPapel()], ['Início']]);
    const u = estado.eu.usuario;
    const hoje = new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
    if (tem('pacientes.gerir')) return inicioMedico(area, u, hoje);
    if (tem('pesquisa.casos')) return inicioPesquisador(area, u, hoje);
    if (tem('usuarios.gerir')) return inicioAdmin(area, u, hoje);
    navegar('#/minha-conta');
  }
  function detalhePendencias(t) { // uma linha: genitor inferido por parentes e análises com suposição; tudo zerado, registros prontos
    const partes = [];
    if (t.com_genitor_inferido) partes.push(`${t.com_genitor_inferido} com genitor inferido por parentes`);
    if (t.com_suposicao) partes.push(`${t.com_suposicao} ${t.com_suposicao === 1 ? 'analisado' : 'analisados'} com suposição`);
    return partes.length ? partes.join(' · ') : 'Todos os registros estão prontos para análise';
  }

  async function inicioMedico(area, u, hoje) {
    const d = await api('GET', '/api/pacientes/painel');
    const t = d.totais;
    for (const p of d.recentes) estado.nomesPacientes[p.id] = p.nome;
    area.append(cabecalhoTela({ titulo: `${saudacao()}, ${u.nome}`, subtitulo: `${hoje.charAt(0).toUpperCase()}${hoje.slice(1)} · visão geral dos seus atendimentos.`, acoes: [linkBotao('Novo paciente', '#/pacientes/novo', { icone: 'mais' }), linkBotao('Pacientes', '#/pacientes', { classe: 'botao-secundario', icone: 'pacientes' }), linkBotao('Análise sem registro', '#/analise', { classe: 'botao-secundario', icone: 'frasco' })] }));
    area.append(el('div', { class: 'indicadores' },
      indicadorLink({ icone: 'pacientes', rotulo: 'Registros', valor: String(t.registros), detalhe: `Pessoas ${t.por_tipo.PESSOA} · casais ${t.por_tipo.CASAL} · famílias ${t.por_tipo.FAMILIA}`, href: '#/pacientes', destaque: true }),
      indicadorLink({ icone: 'frasco', rotulo: 'Análises executadas', valor: String(t.analises), detalhe: `${t.com_analise} registro(s) com análise · ${t.sem_analise} sem`, href: '#/pacientes' }),
      indicadorLink({ icone: 'dna', rotulo: 'Registros com pendência para análise', valor: String(t.pendencias_analise), detalhe: detalhePendencias(t), href: '#/pacientes' }),
      indicadorLink({ icone: 'escudo', rotulo: 'Liberados para pesquisa', valor: String(t.liberados_pesquisa), detalhe: `${t.consentimentos_pendentes} com consentimentos pendentes`, href: '#/pacientes' })));
    const recentes = el('div', { class: 'cartao tabela-cartao' }, el('div', { class: 'cabecalho-tabela' }, el('h2', { text: 'Registros recentes' }), linkBotao('Ver todos', '#/pacientes', { classe: 'botao-link botao-pequeno', icone: 'seta-dir' })),
      d.recentes.length ? tabela([
        { rotulo: 'Registro', classe: 'registro', valor: (p) => el('div', {}, el('a', { href: `#/pacientes/${p.id}`, text: p.nome }), el('div', { class: 'pequeno texto-suave', text: `Prontuário ${p.prontuario}` })) },
        { rotulo: 'Caso', valor: (p) => chip(p.tipo_curto, 'chip-azul chip-tabela') }, { rotulo: 'Pessoas', valor: (p) => pessoasDoRegistro(p) },
        { rotulo: 'VCFs', valor: (p) => chipVcfs(p) }, { rotulo: 'Última análise', valor: (p) => resumoUltimaAnalise(p, true) }, { rotulo: 'Pesquisa', valor: (p) => chipPesquisa(p) }], d.recentes, { blocos: true })
        : el('div', { class: 'vazio' }, icone('pacientes'), el('p', { text: 'Nenhum registro ainda. Comece por "Novo paciente".' })));
    const analises = el('div', { class: 'cartao' }, el('div', { class: 'cabecalho-tela' }, el('div', { class: 'titulos' }, el('h2', { text: 'Análises recentes' })), linkBotao('Ver todas', '#/analises', { classe: 'botao-link botao-pequeno', icone: 'seta-dir' })), d.analises_recentes.length ? el('ul', { class: 'lista-simples' }, d.analises_recentes.map((a) => el('li', {},
      el('div', {}, el('a', { href: a.tem_resultado ? `#/analises/${a.paciente_id}/${a.id}` : `#/pacientes/${a.paciente_id}`, text: a.registro }), el('div', { class: 'pequeno texto-suave', text: `${a.pessoa} · ${fmtData(a.executado_em)}` })),
      el('div', { class: 'chips' }, a.genes_de_risco.length ? a.genes_de_risco.map((g) => chip(g, 'chip-azul')) : chip(SEM_LOCUS, 'chip-neutro'), a.genes_de_risco.length ? chip(a.condicionado ? `a partir dos ${fmtNum(a.idade_referencia, 0)} anos: ${fmtPct(a.p_manifesta)}` : `risco vitalício ${fmtPct(a.p_manifesta)}`, 'chip-neutro') : null, a.com_suposicao ? chip('suposição', 'chip-aviso') : null)))) : el('p', { class: 'texto-suave', text: 'Nenhuma análise executada ainda.' }));
    const pend = el('div', { class: 'cartao' }, el('h2', { text: 'Pendências' }));
    const pendentes = d.pendencias.sem_dados_para_analise;
    if (!pendentes.length && !d.pendencias.sem_analise.length) pend.append(el('p', { class: 'texto-suave' }, icone('check'), ' Nenhuma pendência para análise.'));
    if (pendentes.length) pend.append(el('h3', { text: 'Dados genéticos pendentes' }), el('ul', { class: 'lista-simples' }, pendentes.map((p) => el('li', {}, el('a', { href: `#/pacientes/${p.id}`, text: p.nome })))));
    if (d.pendencias.sem_analise.length) pend.append(el('h3', { text: 'Prontos para a primeira análise' }), el('ul', { class: 'lista-simples' }, d.pendencias.sem_analise.map((p) => el('li', {}, el('a', { href: `#/pacientes/${p.id}`, text: p.nome }), linkBotao('Analisar', `#/analise?paciente=${p.id}`, { classe: 'botao-pequeno', icone: 'frasco' })))));
    const fluxo = el('div', { class: 'cartao' }, el('h2', { text: 'Fluxo de trabalho' }), el('ol', { class: 'passos passos-coluna' },
      el('li', {}, el('strong', { text: 'Cadastrar' }), el('div', { class: 'pequeno texto-suave', text: 'Escolha o caso (pessoa, casal ou família), informe prontuário, genitores e VCFs.' })),
      el('li', {}, el('strong', { text: 'Consentir' }), el('div', { class: 'pequeno texto-suave', text: 'Na ficha, registre os consentimentos para pesquisa, se houver.' })),
      el('li', {}, el('strong', { text: 'Analisar' }), el('div', { class: 'pequeno texto-suave', text: 'Execute a análise: herdou, manifestação por idade e idade de início.' }))),
      el('p', { class: 'pequeno' }, el('a', { href: '#/ajuda', text: 'Ajuda: os três casos e o que fica fora do escopo' })));
    area.append(recentes, el('div', { class: 'grade-painel grade-painel-3' }, analises, pend, fluxo));
  }
  async function inicioPesquisador(area, u, hoje) {
    const c = await api('GET', '/api/pesquisa/casos');
    const t = c.totais;
    area.append(cabecalhoTela({ titulo: `${saudacao()}, ${u.nome}`, subtitulo: `${hoje.charAt(0).toUpperCase()}${hoje.slice(1)} · área de pesquisa.`, acoes: [linkBotao('Registros de pesquisa', '#/pesquisa/casos', { icone: 'microscopio' }), linkBotao('Modelo e parâmetros', '#/modelo', { classe: 'botao-secundario', icone: 'modelo' })] }));
    area.append(el('div', { class: 'indicadores' },
      indicadorLink({ icone: 'microscopio', rotulo: 'Registros de pesquisa', valor: String(t.casos), detalhe: Object.entries(t.por_tipo).map(([k, n]) => `${(c.opcoes.tipos.find((x) => x.valor === k) || {}).curto || k}: ${n}`).join(' · ') || 'nenhum ainda', href: '#/pesquisa/casos', destaque: true }),
      indicadorLink({ icone: 'frasco', rotulo: 'Pessoas analisadas', valor: String(t.analises), detalhe: Object.entries(t.por_sexo).map(([s, n]) => `${s === 'NI' ? 'não informado' : ROTULO_SEXO[s]} ${n}`).join(' · ') || '—', href: '#/pesquisa/casos' }),
      indicadorLink({ icone: 'dna', rotulo: 'Genes de risco', valor: String(Object.keys(t.por_gene).length), detalhe: Object.entries(t.por_gene).map(([g, n]) => `${g} ${n}`).join(' · ') || '—', href: '#/pesquisa/casos' }),
      indicadorLink({ icone: 'escudo', rotulo: 'Risco vitalício mediano', valor: fmtPct(t.risco_vitalicio_mediano), detalhe: `Desde o nascimento, até o horizonte. ${t.com_suposicao} caso(s) com suposição de não portador`, href: '#/pesquisa/casos' })));
    area.append(el('div', { class: 'grade-painel' },
      el('div', { class: 'cartao' }, el('h2', { text: 'Registros de pesquisa' }), el('p', { text: c.descricao }), el('div', { class: 'linhas-info' }, dica('Cada registro pode ser expandido com as variantes encontradas nos VCFs dos genitores, as dosagens por lócus, a curva de risco por idade e os metadados da análise.'), dica('Exportações: resumo (CSV, uma linha por análise), variantes (CSV, uma linha por variante) e JSON detalhado. Consultas e exportações ficam na auditoria.'))),
      el('div', { class: 'cartao' }, el('h2', { text: 'Modelo' }), el('p', { text: (estado.sistema && estado.sistema.descricao) || '' }), el('p', {}, el('a', { href: '#/modelo', text: 'Ver genes, penetrância, distribuições de início e limiares' })))));
  }
  async function inicioAdmin(area, u, hoje) {
    const [pend, usuarios, verif] = await Promise.all([api('GET', '/api/admin/cadastros/pendentes'), api('GET', '/api/admin/usuarios'), api('GET', '/api/admin/auditoria/verificacao')]);
    const porSituacao = {};
    for (const x of usuarios.usuarios) porSituacao[x.situacao] = (porSituacao[x.situacao] || 0) + 1;
    area.append(cabecalhoTela({ titulo: `${saudacao()}, ${u.nome}`, subtitulo: `${hoje.charAt(0).toUpperCase()}${hoje.slice(1)} · administração da plataforma.`, acoes: [linkBotao('Cadastros pendentes', '#/admin/pendentes', { icone: 'prancheta' }), linkBotao('Usuários', '#/admin/usuarios', { classe: 'botao-secundario', icone: 'pacientes' }), linkBotao('Auditoria', '#/admin/auditoria', { classe: 'botao-secundario', icone: 'auditoria' })] }));
    const demo = await api('GET', '/api/admin/demonstracao');
    if (demo.pode_popular) area.append(cartaoDemonstracao('/api/admin/demonstracao', 'Este ambiente é de homologação e ainda não tem médicos nem pesquisadores. Crie os usuários e os registros fictícios para testar a plataforma.'));
    area.append(el('div', { class: 'indicadores' },
      indicadorLink({ icone: 'prancheta', rotulo: 'Cadastros pendentes', valor: String(pend.cadastros.length), detalhe: pend.cadastros.length ? 'Verificação manual de CRM, formação e vínculo' : 'Nenhum pedido aguardando', href: '#/admin/pendentes', destaque: true }),
      indicadorLink({ icone: 'pacientes', rotulo: 'Usuários', valor: String(usuarios.total), detalhe: `verificados ${porSituacao.VERIFICADO || 0} · desativados ${porSituacao.DESATIVADO || 0} · reprovados ${porSituacao.REPROVADO || 0}`, href: '#/admin/usuarios' }),
      indicadorLink({ icone: 'escudo', rotulo: 'Auditoria', valor: verif.ok ? 'íntegra' : 'adulterada', detalhe: verif.ok ? `${verif.total} registros encadeados` : `falha a partir da sequência ${verif.primeira_falha}`, href: '#/admin/auditoria' })));
    area.append(el('div', { class: 'grade-painel' },
      el('div', { class: 'cartao' }, el('h2', { text: 'Pedidos aguardando verificação' }), pend.cadastros.length ? el('ul', { class: 'lista-simples' }, pend.cadastros.slice(0, 8).map((x) => el('li', {}, el('div', {}, el('strong', { text: x.nome }), el('div', { class: 'pequeno texto-suave', text: `${x.papel_rotulo} · ${fmtData(x.criado_em)}` })), chipSituacaoConta(x)))) : el('p', { class: 'texto-suave', text: 'Nenhum cadastro pendente.' }), el('p', {}, linkBotao('Analisar pedidos', '#/admin/pendentes', { classe: 'botao-secundario botao-pequeno', icone: 'seta-dir' }))),
      el('div', { class: 'cartao' }, el('h2', { text: 'O que o administrador faz' }), el('div', { class: 'linhas-info' }, dica('Aprova, reprova ou pede informações nos cadastros; desativa e reativa usuários.'), dica('Consulta a auditoria completa e verifica a cadeia de hash.'), dica('Não acessa registros, dados clínicos, VCFs nem resultados.'), dica('Cria outros administradores (tela Usuários) e gere a base de anotação.')))));
  }

  // ---------------------------------------------------------------------------------------------
  // Qualquer usuário: situação do cadastro e minha conta
  // ---------------------------------------------------------------------------------------------
  function chipSituacaoConta(s) {
    const classe = { VERIFICADO: 'chip-ok', REPROVADO: 'chip-erro', DESATIVADO: 'chip-erro', PENDENTE: 'chip-aviso', INFORMACOES_SOLICITADAS: 'chip-aviso' }[s.situacao] || 'chip-neutro';
    return chip(s.situacao_rotulo, classe);
  }
  async function telaSituacao(area) {
    definirTitulo('Situação do cadastro');
    definirTrilha([['Conta'], ['Situação do cadastro']]);
    const s = await api('GET', '/api/contas/situacao');
    area.append(cabecalhoTela({ titulo: 'Situação do cadastro', chips: [chipSituacaoConta(s)] }));
    const principal = el('div');
    principal.append(el('div', { class: 'cartao' }, el('dl', { class: 'lista-definicao' },
      el('dt', { text: 'Situação' }), el('dd', {}, chipSituacaoConta(s)),
      el('dt', { text: 'Papel pretendido' }), el('dd', { text: s.papel_rotulo }),
      el('dt', { text: 'Cadastro feito em' }), el('dd', { text: fmtData(s.criado_em) }),
      s.verificado_em ? el('dt', { text: 'Verificado em' }) : null, s.verificado_em ? el('dd', { text: fmtData(s.verificado_em) }) : null)));
    if (s.situacao === 'PENDENTE') principal.append(el('div', { class: 'alerta alerta-info' }, icone('relogio'), el('p', { text: 'Seu cadastro aguarda verificação manual pelo administrador (inclusive a conferência do CRM, quando houver). Até lá, só esta tela e "Minha conta" ficam disponíveis.' })));
    if (s.situacao === 'VERIFICADO') principal.append(el('div', { class: 'alerta alerta-sucesso' }, icone('check'), el('p', { text: 'Conta verificada. Use o menu para acessar as funções do seu papel.' })));
    if (s.mensagem_admin) principal.append(el('div', { class: 'cartao' }, el('h2', { text: s.situacao === 'REPROVADO' ? 'Justificativa do administrador' : 'Pedido do administrador' }), el('p', { text: s.mensagem_admin })));
    if (s.resposta_usuario) principal.append(el('div', { class: 'cartao' }, el('h2', { text: `Sua resposta (${fmtData(s.respondido_em)})` }), el('p', { text: s.resposta_usuario })));
    if (s.pode_responder) {
      const resposta = campo({ nome: 'resposta', rotulo: 'Responder ao administrador', tipo: 'textarea', obrigatorio: true, dica: 'Informe o que foi pedido. Não envie arquivos nem dados de pacientes.' });
      principal.append(el('div', { class: 'cartao' }, el('form', { novalidate: true, onsubmit: async (ev) => {
        ev.preventDefault();
        if (!resposta.valor().trim()) { aplicarErros({ resposta }, { resposta: 'Escreva a resposta.' }); return; }
        try { const r = await api('POST', '/api/contas/situacao/resposta', { json: { resposta: resposta.valor().trim() } }); avisar('sucesso', r.mensagem); aoMudarRota(); }
        catch (e) { aplicarErros({ resposta }, e.campos, e.message); }
      } }, resposta.no, el('div', { class: 'acoes' }, botao('Enviar resposta', { tipo: 'submit' })))));
    }
    if (s.situacao === 'VERIFICADO') area.append(principal);
    else area.append(duasColunas(principal, cartaoApoio('Sobre a verificação', ['A conferência é manual: CRM, formação e vínculo são checados pelo administrador.', 'ORCID, Lattes ou vínculo institucional não aprovam automaticamente.', 'Você será avisado aqui quando houver resposta.'])));
  }

  async function telaMinhaConta(area) {
    definirTitulo('Minha conta');
    definirTrilha([['Conta'], ['Minha conta']]);
    const u = await api('GET', '/api/contas/minha');
    area.append(cabecalhoTela({ titulo: 'Minha conta', subtitulo: 'Veja e corrija seus dados, exporte-os ou peça o encerramento da conta (LGPD, art. 18).', chips: [chip(u.papel_rotulo, 'chip-azul', 'pessoa'), chipSituacaoConta(u)] }));
    const FIXO = 'Definido no cadastro e conferido pelo administrador; não editável aqui.';
    const nome = campo({ nome: 'nome', rotulo: 'Nome completo', valor: u.nome, somenteLeitura: true, dica: FIXO, atributos: { autocomplete: 'name' } });
    const cpf = campo({ nome: 'cpf', rotulo: 'CPF', valor: u.cpf_mascarado, somenteLeitura: true, dica: 'Cifrado no banco; exibido mascarado.' });
    const email = campo({ nome: 'email', rotulo: 'E-mail', tipo: 'email', obrigatorio: true, valor: u.email, atributos: { autocomplete: 'email' } });
    const campos = { nome, email };
    const perfilCampos = [];
    const perfil = u.perfil || {};
    if (u.papel === 'MEDICO') {
      if (perfil.tipo === 'CRM') perfilCampos.push(campo({ nome: 'medico.crm', rotulo: 'Número do CRM', valor: perfil.crm, somenteLeitura: true, dica: FIXO }), campo({ nome: 'medico.uf', rotulo: 'UF do CRM', valor: perfil.uf || '', somenteLeitura: true }));
      else perfilCampos.push(campo({ nome: 'medico.formacao', rotulo: 'Formação', valor: perfil.formacao }), campo({ nome: 'medico.instituicao', rotulo: 'Instituição', valor: perfil.instituicao }));
      perfilCampos.push(campo({ nome: 'medico.especialidade', rotulo: 'Especialidade', opcional: true, valor: perfil.especialidade }));
    } else if (u.papel === 'PESQUISADOR') {
      perfilCampos.push(campo({ nome: 'pesquisador.orcid', rotulo: 'ORCID', valor: perfil.orcid || '', somenteLeitura: true, dica: FIXO }));
      for (const [n, r, opc] of [['cargo', 'Cargo ou condição acadêmica', false], ['linha_pesquisa', 'Linha de pesquisa', false], ['instituicao', 'Instituição', true], ['grupo', 'Grupo', true], ['lattes_url', 'Link do Lattes', true], ['projetos', 'Projetos', true], ['evidencias', 'Evidências', true]])
        perfilCampos.push(campo({ nome: `pesquisador.${n}`, rotulo: r, opcional: opc, valor: perfil[n], tipo: ['projetos', 'evidencias'].includes(n) ? 'textarea' : 'text' }));
    }
    for (const c of perfilCampos) campos[c.nome] = c;
    const form = el('form', { novalidate: true, onsubmit: async (ev) => {
      ev.preventDefault();
      const corpo = { nome: nome.valor(), email: email.valor() };
      const v = (k) => (campos[k] ? campos[k].valor() : null);
      if (u.papel === 'MEDICO') corpo.medico = { tipo: perfil.tipo || 'CRM', crm: perfil.crm, uf: perfil.uf, especialidade: v('medico.especialidade'), formacao: v('medico.formacao'), instituicao: v('medico.instituicao') };
      if (u.papel === 'PESQUISADOR') { corpo.pesquisador = { tipo: perfil.tipo || 'INSTITUCIONAL', orcid: perfil.orcid }; for (const c of perfilCampos) if (!c.no.classList.contains('somente-leitura')) corpo.pesquisador[c.nome.split('.')[1]] = c.valor(); }
      try { await api('PUT', '/api/contas/minha', { json: corpo }); avisar('sucesso', 'Dados atualizados.'); await carregarSessao(); renderizarCasca(); }
      catch (e) { aplicarErros(campos, e.campos, Object.keys(e.campos).length ? null : e.message); }
    } }, secaoNumerada(1, 'Dados', el('div', { class: 'grade-campos' }, nome.no, cpf.no, email.no)),
      perfilCampos.length ? secaoNumerada(2, 'Dados profissionais', el('div', { class: 'grade-campos' }, perfilCampos.map((c) => c.no))) : null, el('div', { class: 'acoes acoes-direita' }, botao('Salvar alterações', { tipo: 'submit', icone: 'check' })));
    const principal = el('div', {}, el('div', { class: 'cartao' }, form));
    const atual = campo({ nome: 'senha_atual', rotulo: 'Senha atual', tipo: 'password', obrigatorio: true, mostrarSenha: true, atributos: { autocomplete: 'current-password' } });
    const nova = campo({ nome: 'senha_nova', rotulo: 'Nova senha', tipo: 'password', obrigatorio: true, mostrarSenha: true, dica: 'Mínimo de 10 caracteres.', atributos: { autocomplete: 'new-password' } });
    const camposSenha = { senha_atual: atual, senha_nova: nova };
    principal.append(el('div', { class: 'cartao' }, el('form', { novalidate: true, onsubmit: async (ev) => {
      ev.preventDefault();
      try { const r = await api('POST', '/api/contas/minha/senha', { json: { senha_atual: atual.valor(), senha_nova: nova.valor() } }); avisar('sucesso', r.mensagem); atual.input.value = ''; nova.input.value = ''; }
      catch (e) { aplicarErros(camposSenha, e.campos, Object.keys(e.campos).length ? null : e.message); }
    } }, el('h2', { text: 'Trocar senha' }), el('div', { class: 'grade-campos' }, atual.no, nova.no), el('div', { class: 'acoes acoes-direita' }, botao('Trocar senha', { tipo: 'submit', classe: 'botao-secundario', icone: 'cadeado' })))));
    const lateral = el('div', {}, el('div', { class: 'cartao' }, el('h2', { text: 'Seus dados e sua conta' }),
      el('div', { class: 'acoes' },
        botao('Exportar meus dados (JSON)', { classe: 'botao-secundario', icone: 'baixar', onclick: async () => { try { const d = await api('POST', '/api/contas/minha/exportar'); baixarJson(d, 'minha-conta.json'); avisar('sucesso', 'Exportação gerada.'); } catch (e) { avisar('erro', e.message); } } }),
        u.papel === 'ADMIN' ? el('p', { class: 'pequeno texto-suave', text: 'Administradores não pedem encerramento pela plataforma: a conta é desativada por outro administrador.' })
          : u.encerramento_solicitado_em ? chip(`Encerramento pedido em ${fmtData(u.encerramento_solicitado_em)}`, 'chip-aviso')
          : botao('Pedir encerramento da conta', { classe: 'botao-perigo', onclick: async () => { if (!window.confirm('Pedir o encerramento da conta? O administrador a desativará; a auditoria permanece sem dado identificável.')) return; try { const r = await api('POST', '/api/contas/minha/encerramento'); avisar('sucesso', r.mensagem); aoMudarRota(); } catch (e) { avisar('erro', e.message); } } })),
      el('h3', { text: 'Aceites registrados' }),
      tabela([{ rotulo: 'Documento', valor: (a) => ({ AVISO_PRIVACIDADE: 'Aviso de privacidade', TERMO_USO: 'Termo de uso' }[a.documento] || a.documento) }, { rotulo: 'Versão', chave: 'versao' }, { rotulo: 'Aceito em', valor: (a) => fmtData(a.aceito_em) }], u.aceites || [])));
    area.append(duasColunas(principal, lateral));
    if (tem('auditoria.ver_propria') && estado.eu.verificado) {
      try {
        const a = await api('GET', '/api/contas/minha/auditoria');
        area.append(el('div', { class: 'cartao' }, el('h2', { text: 'Auditoria das minhas ações (últimas 200)' }), tabelaAuditoria(a.registros)));
      } catch (e) { /* conta pendente não vê auditoria */ }
    }
  }
  function baixarJson(dados, nome) {
    const blob = new Blob([JSON.stringify(dados, null, 2)], { type: 'application/json' });
    baixarBlob(blob, nome);
  }
  function baixarBlob(blob, nome) {
    const url = URL.createObjectURL(blob);
    const a = el('a', { href: url, download: nome }); document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function tabelaAuditoria(registros) {
    return tabela([
      { rotulo: 'Seq.', chave: 'sequencia', num: true }, { rotulo: 'Quando', valor: (r) => fmtData(r.ocorrido_em) }, { rotulo: 'Usuário (id)', valor: (r) => (r.usuario_id === null ? '—' : `${r.usuario_id} (${r.papel || '—'})`) },
      { rotulo: 'Ação', chave: 'acao' }, { rotulo: 'Alvo', valor: (r) => (r.alvo_tipo ? `${r.alvo_tipo} ${r.alvo_id}` : '—') },
      { rotulo: 'Resultado', valor: (r) => chip(r.resultado, r.resultado === 'OK' ? 'chip-ok' : 'chip-erro') }, { rotulo: 'Detalhe', chave: 'detalhe' }], registros, { blocos: true });
  }

  // ---------------------------------------------------------------------------------------------
  // Médico: lista de pacientes (atendimentos) com filtros
  // ---------------------------------------------------------------------------------------------
  function chipC9Parcial(a) { // análise em que o C9orf72 saiu do cálculo: o resultado é parcial para esse gene
    return a && a.c9orf72_indeterminado ? chip('C9orf72 não avaliado', 'chip-aviso', 'alerta') : null;
  }
  const SEM_LOCUS = 'nenhum lócus de risco encontrado'; // resultado sem lócus: a tela diz isso, nunca "0,0 %" como se fosse o risco
  function estadoLaudo(g, naAnalise) { // genitor sem o nº de repetições: inferido por parentes, arquivo sem o número ou sem laudo
    const nota = (texto) => el('div', { class: 'pequeno texto-suave', text: texto });
    if ((g.c9orf72_por_parentes || []).length) {
      const parentes = g.c9orf72_por_parentes.map((x) => x.charAt(0).toLowerCase() + x.slice(1)).join(' e ');
      return [el('div', { class: 'chips' }, chip(`C9orf72 inferido pelo laudo de ${parentes}`, 'chip-azul', 'info')), nota('Este genitor não tem laudo próprio: o C9orf72 dele é inferido pelo laudo do parente e o lócus entra no cálculo.')];
    }
    if (g.laudo_documento) return [el('div', { class: 'chips' }, chip('Falta o nº de repetições: C9orf72 indeterminado', 'chip-aviso', 'alerta')), nota(`O arquivo do laudo está anexado, mas o modelo usa o nº de repetições digitado; o arquivo não é lido. ${naAnalise ? 'Digite o número na ficha' : 'Digite o número em "Editar dados"'}: sem ele, o C9orf72 sai do cálculo e o resultado é parcial para esse gene.`)];
    return [el('div', { class: 'chips' }, chip(naAnalise ? 'Não testado: C9orf72 indeterminado' : 'Sem laudo: C9orf72 indeterminado na análise', 'chip-aviso', 'alerta')), nota(`Sem o nº de repetições do laudo, o lócus do C9orf72 sai do cálculo e o resultado é parcial para esse gene. ${naAnalise ? 'Registre o número na ficha.' : 'Registre o número em "Editar dados".'}`)];
  }
  // registro que ainda não pode ser analisado: o botão fica desativado e o clique repete a mensagem de cada genitor sem exame,
  // a mesma com que a análise seria recusada
  function faltaParaAnalisar(p) { return PAPEIS_GENITOR.map((g) => p.genitores[g].falta_exame).filter(Boolean).join(' ') || 'Anexe no cartão "Genitores" o VCF de ao menos um genitor, ou o de um parente de um genitor sem exame, para analisar.'; }
  function desativarAnalise(a, p) { a.setAttribute('aria-disabled', 'true'); a.addEventListener('click', (ev) => { ev.preventDefault(); avisar('aviso', faltaParaAnalisar(p)); }); }
  function resumoUltimaAnalise(p, inicio = false) {
    const a = p.ultima_analise;
    if (!a) return el('span', { class: 'texto-suave', text: 'Sem análise' });
    const genes = a.sem_locus ? [chip('Nenhum lócus de risco encontrado', 'chip-neutro')] : p.genes_de_risco.map((g) => chip(g, 'chip-azul'));
    const riscoVitalicio = inicio ? a.risco_vitalicio : p.risco_vitalicio_maximo;
    const mostrarRiscoVitalicio = riscoVitalicio !== null && (!a.sem_locus || (!inicio && riscoVitalicio > 0));
    return el('div', {}, el('div', { class: 'pequeno', text: fmtData(a.executado_em, true) }),
      el('div', { class: 'chips' }, genes, chipC9Parcial(a)),
      inicio && a.condicionado && !a.sem_locus ? el('div', { text: `a partir dos ${fmtNum(a.idade_referencia, 0)} anos: ${fmtPct(a.p_manifesta)}` }) : null,
      mostrarRiscoVitalicio ? el('div', {
        class: 'pequeno texto-suave',
        title: inicio ? 'Risco desde o nascimento até o horizonte da última análise.' : 'Maior risco vitalício entre as pessoas do registro: desde o nascimento, até o horizonte.',
        text: `${inicio ? 'desde o nascimento:' : 'risco vitalício'} ${fmtPct(riscoVitalicio)}`,
      }) : null, p.com_suposicao ? chip('com suposição', 'chip-aviso', 'alerta') : null);
  }
  function pessoasDoRegistro(p) {
    if (p.tipo === 'CASAL') return 'Casal (futuro filho)';
    if (p.tipo === 'PESSOA' && p.descendentes[0]) return `${p.descendentes[0].idade} anos, ${ROTULO_SEXO[p.descendentes[0].sexo]}`;
    return `${p.descendentes.length} filho(s)`;
  }
  async function telaPacientes(area) {
    definirTitulo('Pacientes');
    definirTrilha([['Área clínica'], ['Pacientes']]);
    const op = await opcoesPacientes();
    const lista = el('div');
    const filtrosAtivos = el('div', { class: 'chips filtros-ativos' });
    area.append(cabecalhoTela({ titulo: 'Pacientes', subtitulo: 'Atendimentos de pessoas, casais e famílias. Você vê apenas os registros que cadastrou. Fluxo: Pacientes › Ficha › Nova análise › Resultado.', acoes: [linkBotao('Novo paciente', '#/pacientes/novo', { icone: 'mais' })] }));
    const busca = campo({ nome: 'busca', rotulo: 'Buscar por nome, prontuário, descendente ou genitor', tipo: 'search', icone: 'lupa', atributos: { autocomplete: 'off' } });
    const f = {
      tipo: campo({ nome: 'f_tipo', rotulo: 'Caso', tipo: 'select', opcoes: [['', 'Todos'], ...op.tipos.map((t) => [t.valor, t.rotulo])] }),
      sexo: campo({ nome: 'f_sexo', rotulo: 'Sexo do descendente', tipo: 'select', opcoes: [['', 'Qualquer'], ['F', 'Feminino'], ['M', 'Masculino']] }),
      idade_min: campo({ nome: 'f_idade_min', rotulo: 'Idade mínima', tipo: 'number', atributos: { min: 0, max: 120 } }),
      idade_max: campo({ nome: 'f_idade_max', rotulo: 'Idade máxima', tipo: 'number', atributos: { min: 0, max: 120 } }),
      menor_de_idade: campo({ nome: 'f_menor', rotulo: 'Menor de idade', tipo: 'select', opcoes: [['', 'Qualquer'], ['true', 'Sim'], ['false', 'Não']] }),
      momento: campo({ nome: 'f_momento', rotulo: 'Momento do aconselhamento', tipo: 'select', opcoes: [['', 'Qualquer'], ...op.momentos.map((m) => [m.valor, m.rotulo])] }),
      pesquisa: campo({ nome: 'f_pesquisa', rotulo: 'Pesquisa e consentimento', tipo: 'select', opcoes: [['', 'Qualquer'], ...op.pesquisa.map((m) => [m.valor, m.rotulo])] }),
      vcfs: campo({ nome: 'f_vcfs', rotulo: 'VCFs dos genitores', tipo: 'select', opcoes: [['', 'Qualquer'], ['COMPLETOS', 'Completos (2 de 2)'], ['INCOMPLETOS', 'Incompletos']] }),
      analise: campo({ nome: 'f_analise', rotulo: 'Análise', tipo: 'select', opcoes: [['', 'Qualquer'], ['COM', 'Com análise'], ['SEM', 'Sem análise']] }),
      risco_min: campo({ nome: 'f_risco', rotulo: 'Risco vitalício mínimo (%)', tipo: 'number', dica: 'Desde o nascimento, até o horizonte.', atributos: { min: 0, max: 100, step: 1 } }),
      laudo: campo({ nome: 'f_laudo', rotulo: 'Laudo do C9orf72', tipo: 'select', opcoes: [['', 'Qualquer'], ['true', 'Informado'], ['false', 'Não informado']] }),
      suposicao: campo({ nome: 'f_suposicao', rotulo: 'Suposição de não portador', tipo: 'select', opcoes: [['', 'Qualquer'], ['true', 'Com suposição'], ['false', 'Sem suposição']] }),
      analise_de: campo({ nome: 'f_analise_de', rotulo: 'Última análise de', tipo: 'date' }),
      analise_ate: campo({ nome: 'f_analise_ate', rotulo: 'Última análise até', tipo: 'date' }),
      cadastro_de: campo({ nome: 'f_cadastro_de', rotulo: 'Cadastro de', tipo: 'date' }),
      cadastro_ate: campo({ nome: 'f_cadastro_ate', rotulo: 'Cadastro até', tipo: 'date' }),
      ordenar: campo({ nome: 'f_ordenar', rotulo: 'Ordenar por', tipo: 'select', valor: 'nome', opcoes: op.ordenacoes.map((o) => [o.valor, o.rotulo]) }),
      direcao: campo({ nome: 'f_direcao', rotulo: 'Direção', tipo: 'select', valor: 'asc', opcoes: [['asc', 'Crescente'], ['desc', 'Decrescente']] }),
    };
    const genes = op.genes.map((g) => marcacao({ nome: 'f_genes', valor: g, rotulo: g }));
    const painel = el('details', { class: 'filtros' }, el('summary', {}, icone('filtro'), ' Filtros'),
      el('div', { class: 'grade-campos' }, f.tipo.no, f.sexo.no, f.idade_min.no, f.idade_max.no, f.menor_de_idade.no, f.momento.no, f.pesquisa.no, f.vcfs.no),
      el('fieldset', {}, el('legend', { text: 'Gene de risco (resultado da última análise)' }), el('div', { class: 'genes-opcoes opcoes-linha' }, genes.map((g) => g.no))),
      el('div', { class: 'grade-campos' }, f.analise.no, f.risco_min.no, f.laudo.no, f.suposicao.no, f.analise_de.no, f.analise_ate.no, f.cadastro_de.no, f.cadastro_ate.no, f.ordenar.no, f.direcao.no));
    const rotulos = { tipo: 'Caso', sexo: 'Sexo', idade_min: 'Idade mín.', idade_max: 'Idade máx.', menor_de_idade: 'Menor', momento: 'Momento', pesquisa: 'Pesquisa', vcfs: 'VCFs', genes: 'Genes', analise: 'Análise', risco_min: 'Risco mín.', laudo_c9orf72: 'Laudo', suposicao: 'Suposição', analise_de: 'Análise de', analise_ate: 'Análise até', cadastro_de: 'Cadastro de', cadastro_ate: 'Cadastro até', ordenar: 'Ordem', direcao: 'Direção', texto: 'Busca' };
    const form = el('form', { novalidate: true, role: 'search', onsubmit: async (ev) => { ev.preventDefault(); await carregar(); } }, busca.no, painel,
      el('div', { class: 'acoes' }, botao('Aplicar', { tipo: 'submit', icone: 'lupa' }), botao('Limpar', { classe: 'botao-secundario', onclick: () => { form.reset(); carregar(); } })));
    area.append(el('div', { class: 'cartao' }, form), filtrosAtivos, lista);
    const bool = (v) => (v === '' ? null : v === 'true');
    const num = (v) => (v === '' ? null : Number(v));
    function filtros() {
      const d = { texto: busca.valor().trim() || null, tipo: f.tipo.valor() || null, sexo: f.sexo.valor() || null, idade_min: num(f.idade_min.valor()), idade_max: num(f.idade_max.valor()), menor_de_idade: bool(f.menor_de_idade.valor()), momento: f.momento.valor() || null,
        pesquisa: f.pesquisa.valor() || null, vcfs: f.vcfs.valor() || null, genes: genes.filter((g) => g.valor()).map((g) => g.input.value), analise: f.analise.valor() || null, risco_min: f.risco_min.valor() === '' ? null : Number(f.risco_min.valor()) / 100,
        laudo_c9orf72: bool(f.laudo.valor()), suposicao: bool(f.suposicao.valor()), analise_de: f.analise_de.valor() || null, analise_ate: f.analise_ate.valor() || null, cadastro_de: f.cadastro_de.valor() || null, cadastro_ate: f.cadastro_ate.valor() || null, ordenar: f.ordenar.valor(), direcao: f.direcao.valor() };
      for (const k of Object.keys(d)) if (d[k] === null || (Array.isArray(d[k]) && !d[k].length)) delete d[k];
      return d;
    }
    async function carregar() {
      limpar(lista); limpar(filtrosAtivos);
      let r;
      try { r = await api('POST', '/api/pacientes/busca', { json: filtros() }); } catch (e) { aplicarErros({}, {}, `${e.message} ${Object.entries(e.campos || {}).map(([k, v]) => `${rotulos[k] || k}: ${v}`).join(' ')}`); return; }
      for (const [k, v] of Object.entries(r.filtros || {})) filtrosAtivos.append(chip(`${rotulos[k] || k}: ${Array.isArray(v) ? v.join(', ') : k === 'risco_min' ? fmtPct(v, 0) : v}`, 'chip-azul'));
      for (const p of r.pacientes) estado.nomesPacientes[p.id] = p.nome;
      if (!r.pacientes.length) { lista.append(vazio(Object.keys(r.filtros || {}).length ? 'Nenhum registro encontrado com esses filtros.' : 'Nenhum paciente cadastrado ainda. Use "Novo paciente".', 'pacientes')); return; }
      lista.append(el('div', { class: 'cartao tabela-cartao' }, el('div', { class: 'cabecalho-tabela' }, el('strong', { text: `${r.total} registro(s)` })), tabela([
        { rotulo: 'Registro', classe: 'registro', valor: (p) => el('div', {}, el('a', { href: `#/pacientes/${p.id}`, text: p.nome }), el('div', { class: 'pequeno texto-suave', text: `Prontuário ${p.prontuario}` })) },
        { rotulo: 'Caso', valor: (p) => chip(p.tipo_curto, 'chip-azul chip-tabela', p.tipo === 'CASAL' ? 'casal' : p.tipo === 'FAMILIA' ? 'familia' : 'pessoa') },
        { rotulo: 'Pessoas', valor: (p) => el('div', {}, pessoasDoRegistro(p), el('div', { class: 'pequeno texto-suave', text: p.momento_rotulo || '' })) },
        { rotulo: 'VCFs', valor: (p) => chipVcfs(p) }, { rotulo: 'Última análise', valor: (p) => resumoUltimaAnalise(p) }, { rotulo: 'Pesquisa', valor: (p) => chipPesquisa(p) }], r.pacientes, { blocos: true })));
    }
    await carregar();
  }

  // ---------------------------------------------------------------------------------------------
  // Médico: novo paciente / editar (três casos; VCFs enviados logo após o cadastro)
  // ---------------------------------------------------------------------------------------------
  function camposGenitor(prefixo, rotulo, valores, comVcf) {
    const nome = campo({ nome: `${prefixo}.nome`, rotulo: `Nome completo`, obrigatorio: true, valor: valores.nome, atributos: { autocomplete: 'off' } });
    const nasc = campo({ nome: `${prefixo}.data_nascimento`, rotulo: 'Data de nascimento', tipo: 'date', obrigatorio: true, valor: valores.data_nascimento });
    const laudo = campo({ nome: `${prefixo}.laudo_c9orf72`, rotulo: 'Repetições do C9orf72 conforme o laudo', opcional: true, valor: valores.laudo_c9orf72, dica: 'Nº de repetições GGGGCC do maior alelo (ex.: 45) ou dos dois alelos (ex.: 12,45), copiado do laudo. A expansão não é lida do VCF nem do arquivo do laudo: sem este número, o C9orf72 fica indeterminado.', atributos: { inputmode: 'numeric' } });
    const laudoDoc = comVcf ? campo({ nome: `${prefixo}.laudo_documento`, rotulo: 'Arquivo do laudo do C9orf72', opcional: true, tipo: 'file', dica: 'PDF, JPG ou PNG, até 10 MB. Fica cifrado; só você abre.', atributos: { accept: '.pdf,.jpg,.jpeg,.png' } }) : null;
    const vcf = comVcf ? campo({ nome: `${prefixo}.vcf`, rotulo: 'Arquivo VCF', opcional: true, tipo: 'file', dica: 'GRCh38, .vcf ou .vcf.gz, até 20 MB. Fica cifrado; pode ser anexado depois na ficha.', atributos: { accept: '.vcf,.gz' } }) : null;
    // arquivo do laudo escolhido sem o número digitado: avisa na hora, sem impedir o cadastro
    const faltaNumero = laudoDoc ? el('div', { class: 'alerta alerta-aviso', role: 'status', hidden: true }, icone('alerta'), el('p', { text: 'Arquivo do laudo escolhido sem o nº de repetições. O arquivo fica guardado como documento e não é lido: digite o número que consta no laudo, senão o C9orf72 fica indeterminado e o resultado é parcial para esse gene.' })) : null;
    if (laudoDoc) {
      const conferir = () => { faltaNumero.hidden = !(laudoDoc.input.files.length && !laudo.valor().trim()); };
      laudoDoc.input.addEventListener('change', conferir);
      laudo.input.addEventListener('input', conferir);
    }
    const bloco = el('div', { class: 'bloco-genitor' }, el('h3', {}, icone('pessoa'), rotulo), nome.no, el('div', { class: 'grade-campos' }, nasc.no, laudo.no), laudoDoc ? laudoDoc.no : null, faltaNumero, vcf ? vcf.no : null);
    return { bloco, campos: { [`${prefixo}.nome`]: nome, [`${prefixo}.data_nascimento`]: nasc, [`${prefixo}.laudo_c9orf72`]: laudo, ...(vcf ? { [`${prefixo}.vcf`]: vcf } : {}), ...(laudoDoc ? { [`${prefixo}.laudo_documento`]: laudoDoc } : {}) }, nome, nasc, laudo, vcf, laudoDoc,
      valor() { return { nome: nome.valor().trim(), data_nascimento: nasc.valor(), laudo_c9orf72: laudo.valor().trim() || null }; } };
  }
  function camposDescendente(prefixo, valores) {
    const nome = campo({ nome: `${prefixo}.nome`, rotulo: 'Nome completo', obrigatorio: true, valor: valores.nome, atributos: { autocomplete: 'off' } });
    const nasc = campo({ nome: `${prefixo}.data_nascimento`, rotulo: 'Data de nascimento', tipo: 'date', obrigatorio: true, valor: valores.data_nascimento, dica: 'A idade será calculada automaticamente.' });
    const sexo = campo({ nome: `${prefixo}.sexo`, rotulo: 'Sexo', tipo: 'select', obrigatorio: true, valor: valores.sexo || '', opcoes: [['', 'Selecione'], ['F', 'Feminino'], ['M', 'Masculino']], dica: 'Entra no modelo (efeito documentado só para o C9orf72).' });
    return { campos: { [`${prefixo}.nome`]: nome, [`${prefixo}.data_nascimento`]: nasc, [`${prefixo}.sexo`]: sexo }, no: el('div', {}, nome.no, el('div', { class: 'grade-campos' }, nasc.no, sexo.no)), valor() { return { nome: nome.valor().trim(), data_nascimento: nasc.valor(), sexo: sexo.valor() }; } };
  }
  async function enviarArquivos(pid, envios, progresso) { // envios: [{rotulo, caminho, form}]; sequencial, com progresso acessível
    const erros = [];
    for (let i = 0; i < envios.length; i++) {
      const { rotulo, caminho, form } = envios[i];
      progresso.texto.textContent = `Enviando arquivo ${i + 1} de ${envios.length} (${rotulo})…`;
      progresso.barra.style.width = `${Math.round((i / envios.length) * 100)}%`;
      try { await api('POST', caminho, { form }); } catch (e) { erros.push(`${rotulo}: ${(e.campos && (e.campos.vcf || e.campos.arquivo)) || e.message}`); }
    }
    progresso.barra.style.width = '100%';
    return erros;
  }
  function formArquivo(campoNome, arquivo, extras = {}) { const fd = new FormData(); for (const [k, v] of Object.entries(extras)) fd.append(k, v); fd.append(campoNome, arquivo); return fd; }
  async function telaPacienteFormulario(area, params) {
    const id = params[0] ? Number(params[0]) : null;
    definirTitulo(id ? 'Editar paciente' : 'Novo paciente');
    const op = await opcoesPacientes();
    const existente = id ? await api('GET', `/api/pacientes/${id}`) : null;
    definirTrilha([['Área clínica'], ['Pacientes', '#/pacientes'], ...(existente ? [[existente.nome, `#/pacientes/${id}`], ['Editar']] : [['Novo paciente']])]);
    let tipo = existente ? existente.tipo : 'PESSOA';
    const raiz = el('div');
    area.append(cabecalhoTela({ titulo: id ? 'Editar paciente' : 'Novo paciente', subtitulo: id ? 'Altere os dados do registro e dos genitores. Descendentes e VCFs são editados na ficha.' : 'Escolha o caso e cadastre os dados essenciais. Os VCFs são enviados junto com o cadastro.', chips: existente ? [chipTipo(existente)] : [], acoes: [linkBotao('Voltar aos pacientes', existente ? `#/pacientes/${id}` : '#/pacientes', { classe: 'botao-secundario', icone: 'seta-esq' })] }));
    const apoio = cartaoApoio('Sobre o cadastro', ['Informe apenas os dados necessários ao atendimento. Não pedimos CPF, endereço, telefone nem e-mail de atendidos ou genitores.', 'Todos os atendidos são assintomáticos: o EloSense estima risco preditivo, não prognóstico.', 'Base legal do atendimento: LGPD, art. 11, II, f (tutela da saúde por profissional de saúde). Não depende de consentimento.', 'Prontuário e laudo do C9orf72 são anexados como documentos (PDF ou imagem), cifrados; o número de repetições do laudo é digitado porque o modelo precisa dele.', 'O VCF de cada genitor é opcional no cadastro e pode ser anexado depois na ficha. Sem o exame de um genitor, a análise só roda com a suposição de que ele não é portador, declarada no resultado.', 'Os consentimentos para pesquisa são registrados na ficha, nunca pré-marcados.']);
    area.append(duasColunas(raiz, apoio));
    render();

    function render() {
      limpar(raiz);
      const t = op.tipos.find((x) => x.valor === tipo);
      const todos = {};
      const partes = [];
      if (!existente) {
        const escolha = cartoesOpcao({ nome: 'tipo', rotulo: 'Tipo de atendimento', valor: tipo, onchange: (v) => { tipo = v; render(); }, opcoes: op.tipos.map((x) => ({ valor: x.valor, titulo: x.rotulo, descricao: x.descricao, icone: x.valor === 'CASAL' ? 'casal' : x.valor === 'FAMILIA' ? 'familia' : 'pessoa' })) });
        partes.push(secaoNumerada(1, 'Tipo de atendimento', escolha.no, dica(`O resultado responde: ${t.responde.join('; ')}.`)));
      }
      let n = existente ? 1 : 2;
      const rotulosG = op.rotulos_genitor[tipo];
      const nomeReg = campo({ nome: 'nome', rotulo: tipo === 'FAMILIA' ? 'Nome da família' : 'Nome do registro', obrigatorio: tipo === 'FAMILIA', opcional: tipo !== 'FAMILIA', valor: existente ? existente.nome : '', dica: tipo === 'FAMILIA' ? 'Ex.: Família Silva. Aparece na lista de pacientes.' : tipo === 'CASAL' ? 'Se vazio, usa "Parceira e Parceiro".' : 'Se vazio, usa o nome da pessoa atendida.' });
      const pront = campo({ nome: 'prontuario', rotulo: 'Número do prontuário', obrigatorio: true, valor: existente ? existente.prontuario : '', atributos: { autocomplete: 'off' } });
      const prontDoc = existente ? null : campo({ nome: 'prontuario_documento', rotulo: 'Documento do prontuário', obrigatorio: true, tipo: 'file', dica: 'PDF, JPG ou PNG, até 10 MB. Fica cifrado; só você abre.', atributos: { accept: '.pdf,.jpg,.jpeg,.png' } });
      const momento = campo({ nome: 'momento', rotulo: 'Momento do aconselhamento', tipo: 'select', opcional: true, valor: existente ? existente.momento || '' : '', opcoes: [['', 'Não informado'], ...op.momentos.map((m) => [m.valor, m.rotulo])] });
      const obs = campo({ nome: 'observacoes', rotulo: 'Observações', opcional: true, tipo: 'textarea', valor: existente ? existente.observacoes : '', dica: 'Só o necessário ao atendimento; nunca dados de terceiros além dos genitores e descendentes.' });
      Object.assign(todos, { nome: nomeReg, prontuario: pront, momento, observacoes: obs, ...(prontDoc ? { prontuario_documento: prontDoc } : {}) });
      const descs = [];
      const listaDesc = el('div', { class: 'lista-dinamica' });
      function addDescendente(valores) {
        const d = camposDescendente(`descendentes.${descs.length}`, valores || {});
        const item = el('div', { class: 'item-dinamico' }, tipo === 'FAMILIA' ? el('h3', { text: `Filho(a) ${descs.length + 1}` }) : null, d.no);
        if (tipo === 'FAMILIA') item.append(botao('Remover', { classe: 'botao-secundario botao-pequeno remover', icone: 'lixeira', ariaLabel: `Remover filho(a) ${descs.length + 1}`, onclick: () => { const i = descs.indexOf(d); descs.splice(i, 1); item.remove(); } }));
        descs.push(d); listaDesc.append(item);
        Object.assign(todos, d.campos);
      }
      const gm = camposGenitor('mae', rotulosG.MAE, existente ? existente.genitores.MAE : {}, !existente);
      const gp = camposGenitor('pai', rotulosG.PAI, existente ? existente.genitores.PAI : {}, !existente);
      Object.assign(todos, gm.campos, gp.campos);
      const secGenitores = secaoNumerada(0, tipo === 'CASAL' ? 'Casal: parceira e parceiro' : 'Genitores', el('div', { class: 'grade-2' }, gm.bloco, gp.bloco), dica(tipo === 'CASAL' ? 'A análise estima a transmissão a um futuro filho a partir dos VCFs dos dois parceiros.' : 'Os VCFs analisados são os da mãe e do pai, titulares desses dados.'));
      if (tipo === 'PESSOA') {
        if (!existente) addDescendente({});
        partes.push(secaoNumerada(n++, 'Pessoa atendida', existente ? dica('Os dados da pessoa atendida são editados na ficha, no cartão "Descendentes".') : listaDesc, el('div', { class: 'grade-campos' }, pront.no, prontDoc ? prontDoc.no : null, momento.no), nomeReg.no));
      } else if (tipo === 'CASAL') {
        partes.push(secaoNumerada(n++, 'Registro do casal', el('div', { class: 'grade-campos' }, nomeReg.no, pront.no, prontDoc ? prontDoc.no : null, momento.no)));
      } else {
        partes.push(secaoNumerada(n++, 'Família', el('div', { class: 'grade-campos' }, nomeReg.no, pront.no, prontDoc ? prontDoc.no : null, momento.no)));
      }
      secGenitores.querySelector('.secao-num').textContent = String(n++).padStart(2, '0');
      partes.push(secGenitores);
      if (tipo === 'FAMILIA' && !existente) {
        addDescendente({});
        partes.push(secaoNumerada(n++, 'Filhos', listaDesc, el('div', { class: 'acoes' }, botao('Adicionar filho(a)', { classe: 'botao-secundario', icone: 'mais', onclick: () => addDescendente({}) }))));
      }
      partes.push(secaoNumerada(n++, 'Observações', obs.no));
      const progresso = { texto: el('p', { role: 'status', text: '' }), barra: el('div') };
      const caixaProgresso = el('div', { class: 'ocupado', hidden: true }, el('div', { class: 'flex-1' }, progresso.texto, el('div', { class: 'progresso' }, progresso.barra)));
      const enviar = botao(existente ? 'Salvar alterações' : 'Cadastrar paciente', { tipo: 'submit', icone: 'check' });
      const form = el('form', { novalidate: true, onsubmit: async (ev) => {
        ev.preventDefault();
        const erros = {};
        const corpo = { tipo, nome: nomeReg.valor().trim() || null, prontuario: pront.valor().trim(), momento: momento.valor() || null, observacoes: obs.valor().trim() || null, mae: gm.valor(), pai: gp.valor(), descendentes: descs.map((d) => d.valor()) };
        if (!corpo.prontuario) erros.prontuario = 'Informe o número do prontuário.';
        if (prontDoc && !prontDoc.input.files.length) erros.prontuario_documento = 'Anexe o documento do prontuário (PDF ou imagem).';
        if (tipo === 'FAMILIA' && !corpo.nome) erros.nome = 'Informe o nome da família.';
        for (const [k, g] of [['mae', gm], ['pai', gp]]) { if (g.nome.valor().trim().length < 3) erros[`${k}.nome`] = 'Informe o nome completo.'; if (!g.nasc.valor()) erros[`${k}.data_nascimento`] = 'Informe a data de nascimento.'; if (g.laudo.valor().trim() && !/^\s*\d+\s*([,; ]\s*\d+\s*)?$/.test(g.laudo.valor())) erros[`${k}.laudo_c9orf72`] = 'Use um número (45) ou dois (12,45).'; }
        descs.forEach((d, i) => { const v = d.valor(); if (v.nome.length < 3) erros[`descendentes.${i}.nome`] = 'Informe o nome completo.'; if (!v.data_nascimento) erros[`descendentes.${i}.data_nascimento`] = 'Informe a data de nascimento.'; else if (new Date(v.data_nascimento) > new Date()) erros[`descendentes.${i}.data_nascimento`] = 'A data não pode estar no futuro.'; if (!v.sexo) erros[`descendentes.${i}.sexo`] = 'Informe o sexo.'; });
        if (Object.keys(erros).length) { aplicarErros(todos, erros); return; }
        enviar.disabled = true;
        try {
          const p = existente ? await api('PUT', `/api/pacientes/${id}`, { json: corpo }) : await api('POST', '/api/pacientes', { json: corpo });
          estado.nomesPacientes[p.id] = p.nome;
          const envios = [];
          if (prontDoc && prontDoc.input.files.length) envios.push({ rotulo: 'documento do prontuário', caminho: `/api/pacientes/${p.id}/documentos`, form: formArquivo('arquivo', prontDoc.input.files[0], { tipo: 'PRONTUARIO' }) });
          for (const [papel, g] of [['MAE', gm], ['PAI', gp]]) {
            const quem = papel === 'MAE' ? 'mãe/parceira' : 'pai/parceiro';
            if (g.vcf && g.vcf.input.files.length) envios.push({ rotulo: `VCF ${quem}`, caminho: `/api/pacientes/${p.id}/genitores/${papel}/vcf`, form: formArquivo('vcf', g.vcf.input.files[0]) });
            if (g.laudoDoc && g.laudoDoc.input.files.length) envios.push({ rotulo: `laudo ${quem}`, caminho: `/api/pacientes/${p.id}/documentos`, form: formArquivo('arquivo', g.laudoDoc.input.files[0], { tipo: 'LAUDO_C9ORF72', papel }) });
          }
          let errosEnvio = [];
          if (envios.length) { caixaProgresso.hidden = false; errosEnvio = await enviarArquivos(p.id, envios, progresso); }
          estado.avisoPendente = existente ? 'Registro atualizado.' : (errosEnvio.length ? `Registro cadastrado, mas um arquivo não foi aceito: ${errosEnvio.join(' ')} Anexe-o na ficha.` : 'Registro cadastrado.' + (envios.length ? ` ${envios.length} arquivo(s) anexado(s).` : ''));
          navegar(`#/pacientes/${p.id}`);
        } catch (e) { aplicarErros(todos, e.campos, Object.keys(e.campos || {}).length ? null : e.message); }
        finally { enviar.disabled = false; caixaProgresso.hidden = true; }
      } }, partes, caixaProgresso, el('div', { class: 'acoes acoes-direita' }, linkBotao('Cancelar', existente ? `#/pacientes/${id}` : '#/pacientes', { classe: 'botao-secundario' }), enviar));
      raiz.append(el('div', { class: 'cartao' }, form));
    }
  }

  // ---------------------------------------------------------------------------------------------
  // Médico: ficha do registro
  // ---------------------------------------------------------------------------------------------
  function refAnalise(a) { // a que os três valores se referem: desde o nascimento ou a partir da idade atual, sem sintomas
    if (!a) return '';
    if (a.condicionado && a.idade_referencia !== null && a.idade_referencia !== undefined) return `a partir dos ${fmtNum(a.idade_referencia, 0)} anos, sem sintomas`;
    if (a.condicionado && a.faixa_idade_referencia) return `a partir da idade atual (faixa ${a.faixa_idade_referencia} anos), sem sintomas`;
    return 'desde o nascimento';
  }
  function linhaRisco(a, rotuloPessoa) {
    if (!a) return null;
    const ini = a.inicio || {};
    return { pessoa: rotuloPessoa, referencia: refAnalise(a), herdou: a.sem_locus ? SEM_LOCUS : fmtPct(a.p_portador), manifestacao: a.sem_locus ? '—' : `${fmtPct(a.p_manifesta)} [${fmtPct(a.q025)}–${fmtPct(a.q975)}]`, vitalicio: a.sem_locus ? '—' : fmtPct(a.risco_vitalicio), inicio: a.sem_locus ? '—' : `${fmtNum(a.idade_mediana, 0)} anos (25–75 %: ${fmtNum(ini.q25, 0)}–${fmtNum(ini.q75, 0)})`, quando: fmtData(a.executado_em, true), suposicao: a.com_suposicao ? 'sim' : 'não', sexo: a.sexo ? ROTULO_SEXO[a.sexo] : 'não informado', id: a.id, tem_resultado: a.tem_resultado };
  }
  async function telaFicha(area, params) {
    const id = Number(params[0]);
    const op = await opcoesPacientes();
    const p = await api('GET', `/api/pacientes/${id}`);
    estado.nomesPacientes[p.id] = p.nome;
    definirTitulo(`Ficha: ${p.nome}`);
    definirTrilha([['Área clínica'], ['Pacientes', '#/pacientes'], ['Ficha']]);
    const faltam = PAPEIS_GENITOR.filter((g) => !p.genitores[g].vcf.presente);
    const podeAnalisar = p.pode_analisar !== undefined ? p.pode_analisar : faltam.length < 2;
    const acoes = [
      linkBotao('Nova análise', podeAnalisar ? `#/analise?paciente=${p.id}` : '#', { icone: 'frasco' }),
      linkBotao('Editar', `#/pacientes/${p.id}/editar`, { classe: 'botao-secundario', icone: 'editar' }),
      botao('Exportar (JSON)', { classe: 'botao-secundario', icone: 'baixar', onclick: async () => { try { const d = await api('POST', `/api/pacientes/${p.id}/exportar`); baixarJson(d, `registro-${p.id}.json`); avisar('sucesso', 'Exportação gerada (direito de acesso e portabilidade).'); } catch (e) { avisar('erro', e.message); } } }),
      botao('Excluir', { classe: 'botao-perigo', icone: 'lixeira', onclick: () => renderExclusao() }),
    ];
    if (!podeAnalisar) desativarAnalise(acoes[0], p);
    const subt = [`Prontuário ${p.prontuario}`, p.momento_rotulo || null, p.tipo === 'PESSOA' && p.descendentes[0] ? `${p.descendentes[0].idade} anos, ${ROTULO_SEXO[p.descendentes[0].sexo]}` : null].filter(Boolean).join(' · ');
    area.append(cabecalhoTela({ titulo: p.nome, subtitulo: subt, chips: [chipTipo(p), chipVcfs(p), chipPesquisa(p)], acoes }));
    const areaExclusao = el('div');
    area.append(areaExclusao);
    area.append(el('p', { class: 'dica-linha' }, icone('info'), el('span', { text: p.linha_risco })));
    // registro e base legal
    area.append(el('div', { class: 'grade-2' },
      el('div', { class: 'cartao' }, el('h2', { text: 'Registro' }), el('dl', { class: 'lista-definicao' },
        el('dt', { text: 'Caso' }), el('dd', { text: p.tipo_rotulo }), el('dt', { text: 'Prontuário' }), el('dd', {}, el('div', { text: p.prontuario }), blocoDocumento(p, 'PRONTUARIO', null, p.prontuario_documento)),
        el('dt', { text: 'Momento' }), el('dd', { text: p.momento_rotulo || '—' }), el('dt', { text: 'Observações' }), el('dd', { text: p.observacoes || '—' }),
        el('dt', { text: 'Cadastrado em' }), el('dd', { text: fmtData(p.criado_em) }), el('dt', { text: 'Atualizado em' }), el('dd', { text: fmtData(p.atualizado_em) }))),
      el('div', { class: 'cartao' }, el('h2', { text: 'Base legal e compartilhamento' }),
        el('p', {}, el('strong', { text: 'Atendimento: ' }), p.base_legal, '. Não depende de consentimento.'),
        el('p', {}, el('strong', { text: 'Pesquisa: ' }), chipPesquisa(p), p.liberado_pesquisa_em ? ` desde ${fmtData(p.liberado_pesquisa_em)}` : ''),
        el('p', { class: 'pequeno texto-suave', text: 'Ao liberar, o sistema gera um código pseudonimizado aleatório, não derivado de nome, prontuário ou data, que não é exibido ao médico nem ao administrador. O vínculo com o atendido continua existindo (pseudonimização, não anonimização).' }))));
    area.append(cartaoGenitores(p, op));
    if (p.tipo !== 'CASAL') area.append(cartaoDescendentes(p));
    else area.append(el('div', { class: 'cartao' }, el('h2', { text: 'Futuro filho' }), el('p', { text: 'No caso 2 não há descendente cadastrado: a análise estima a transmissão e o risco de um futuro filho do casal, para o sexo escolhido ou para os dois sexos.' }), el('div', { class: 'acoes' }, linkBotao('Analisar transmissão', podeAnalisar ? `#/analise?paciente=${p.id}` : '#', { icone: 'transmissao' }))));
    area.append(cartaoHistorico(p));
    area.append(renderConsentimentos(p));
    function renderExclusao() {
      limpar(areaExclusao);
      const conf = campo({ nome: 'confirmacao_nome', rotulo: 'Para excluir, digite o nome do registro exatamente como aparece no título', obrigatorio: true, atributos: { autocomplete: 'off' } });
      areaExclusao.append(el('div', { class: 'cartao' }, el('h2', { text: 'Excluir registro' }), el('p', { text: 'Remove identificadores, genitores, VCFs cifrados, resumos de análise e consentimentos (direito de eliminação, art. 16 e 18, VI). A auditoria permanece, sem dado identificável. Esta ação não pode ser desfeita.' }),
        el('form', { novalidate: true, onsubmit: async (ev) => {
          ev.preventDefault();
          try { const r = await api('DELETE', `/api/pacientes/${p.id}`, { json: { confirmacao_nome: conf.valor() } }); delete estado.nomesPacientes[p.id]; estado.avisoPendente = r.mensagem; navegar('#/pacientes'); }
          catch (e) { aplicarErros({ confirmacao_nome: conf }, e.campos, Object.keys(e.campos).length ? null : e.message); }
        } }, conf.no, el('div', { class: 'acoes' }, botao('Cancelar', { classe: 'botao-secundario', onclick: () => limpar(areaExclusao) }), botao('Excluir definitivamente', { tipo: 'submit', classe: 'botao-perigo', icone: 'lixeira' })))));
      conf.input.focus();
    }
  }
  function blocoSemExame(p, papel, g, op) { // genitor sem VCF: situação clínica dele e parentes testados
    const caixa = el('div', { class: 'bloco-sem-exame' }, el('h4', { text: `${g.rotulo} sem exame: parentes testados` }),
      el('p', { class: 'pequeno texto-suave', text: 'Se este genitor não pôde ser testado (faleceu, não está disponível ou não quer fazer o teste), anexe o VCF e o laudo do pai, da mãe ou de um irmão dele. A dosagem do genitor passa a ser inferida e condicionada à situação clínica dele.' }));
    const situacao = campo({ nome: `situacao_${papel}`, rotulo: 'Situação clínica do genitor', tipo: 'select', valor: g.situacao_clinica || '', placeholderVazio: true, dica: 'Situação desconhecida: não se sabe se o genitor teve ELA. É aceita, mas sem o ajuste pela idade.', opcoes: [['', 'Selecione a situação'], ...(op.situacoes_genitor || []).map((s) => [s.valor, s.rotulo])] });
    const idade = campo({ nome: `idade_${papel}`, rotulo: 'Idade (atual, ou ao falecer)', tipo: 'number', opcional: true, valor: g.idade_situacao === null || g.idade_situacao === undefined ? '' : g.idade_situacao, atributos: { min: 0, max: 120, step: 1 }, dica: 'Vivo sem sintomas: vazio usa a idade pela data de nascimento. Falecido sem ELA: idade ao falecer.' });
    const salvar = botao('Salvar situação', { classe: 'botao-secundario botao-pequeno', icone: 'check', onclick: async () => {
      try { await api('PUT', `/api/pacientes/${p.id}/genitores/${papel}/situacao`, { json: { situacao: situacao.valor() || null, idade: String(idade.valor()).trim() === '' ? null : Number(idade.valor()) } }); estado.avisoPendente = 'Situação clínica do genitor atualizada.'; aoMudarRota(); }
      catch (e) { aplicarErros({ situacao, idade }, e.campos, Object.keys(e.campos || {}).length ? null : e.message); }
    } });
    caixa.append(el('div', {}, situacao.no, idade.no), el('div', { class: 'acoes' }, salvar));
    if (g.inferido_por_parentes && !g.situacao_clinica) caixa.append(el('div', { class: 'chips' }, chip('Informe a situação clínica para analisar', 'chip-aviso', 'alerta')));
    if (g.parentes.length) caixa.append(tabela([
      { rotulo: 'Parente', chave: 'rotulo' },
      { rotulo: 'VCF', valor: (x) => (x.vcf.presente ? el('div', {}, chip('VCF anexado', 'chip-ok', 'dna'), el('div', { class: 'pequeno texto-suave', text: `${fmtBytes(x.vcf.tamanho)} · hash ${x.vcf.hash_curto}` })) : chip('Sem VCF', 'chip-neutro')) },
      { rotulo: 'Laudo C9orf72', valor: (x) => (x.laudo_c9orf72 ? `${x.laudo_c9orf72} repetições` : 'sem laudo') },
      { rotulo: 'Ação', valor: (x) => botao('Remover', { classe: 'botao-perigo botao-pequeno', icone: 'lixeira', ariaLabel: `Remover parente: ${x.rotulo}`, onclick: async () => { if (!window.confirm(`Remover ${x.rotulo}? O VCF cifrado e o consentimento desse parente serão apagados.`)) return; try { await api('DELETE', `/api/pacientes/${p.id}/parentes/${x.id}`); estado.avisoPendente = 'Parente removido.'; aoMudarRota(); } catch (e) { avisar('erro', e.message); } } }) }], g.parentes, { legenda: `Parentes testados (${g.rotulo})` }));
    const area = el('div');
    const abrir = botao('Adicionar parente testado', { classe: 'botao-pequeno', icone: 'mais', onclick: () => {
      limpar(area);
      const parentesco = campo({ nome: `parentesco_${papel}`, rotulo: 'Parentesco com este genitor', tipo: 'select', obrigatorio: true, opcoes: (op.parentescos || []).map((x) => [x.valor, x.rotulo]) });
      const arquivo = campo({ nome: `vcf_parente_${papel}`, rotulo: 'VCF do parente', tipo: 'file', opcional: true, dica: 'Arquivo .vcf (ou .vcf.gz), GRCh38. Fica cifrado em disco, sem download.', atributos: { accept: '.vcf,.gz' } });
      const laudo = campo({ nome: `laudo_parente_${papel}`, rotulo: 'Laudo do C9orf72 do parente', opcional: true, dica: 'Nº de repetições (ex.: 45) ou os dois alelos (12,45). Sem laudo, o C9orf72 desse parente não entra.', atributos: { inputmode: 'numeric' } });
      const campos = { parentesco, vcf: arquivo, laudo_c9orf72: laudo };
      const form = el('form', { novalidate: true, onsubmit: async (ev) => {
        ev.preventDefault();
        const fd = new FormData(); fd.append('parentesco', parentesco.valor());
        if (arquivo.input.files.length) fd.append('vcf', arquivo.input.files[0]);
        if (laudo.valor().trim()) fd.append('laudo_c9orf72', laudo.valor().trim());
        try { await api('POST', `/api/pacientes/${p.id}/genitores/${papel}/parentes`, { form: fd }); estado.avisoPendente = 'Parente testado adicionado.'; aoMudarRota(); }
        catch (e) { aplicarErros(campos, e.campos, Object.keys(e.campos || {}).length ? null : e.message); }
      } }, el('div', { class: 'grade-campos' }, parentesco.no, arquivo.no, laudo.no),
        el('p', { class: 'pequeno texto-suave', text: 'O parente também é titular de dado genético: envie só com a autorização dele. Nenhum nome é guardado; o caso só vai para pesquisa com o consentimento dele.' }),
        el('div', { class: 'acoes' }, botao('Cancelar', { classe: 'botao-secundario botao-pequeno', onclick: () => limpar(area) }), botao('Adicionar', { tipo: 'submit', classe: 'botao-pequeno', icone: 'check' })));
      area.append(form);
      parentesco.input.focus();
    } });
    caixa.append(el('div', { class: 'acoes' }, abrir), area);
    return caixa;
  }
  function celulaTeste(p, d) { // filho que já fez o teste (caso de família): o VCF dele é evidência sobre o genitor sem exame
    const entrada = el('input', { type: 'file', accept: '.vcf,.gz', class: 'sr-only', id: `vcf-desc-${d.id}`, 'aria-label': `Arquivo VCF de ${d.nome} (filho já testado)` });
    entrada.addEventListener('change', async () => {
      if (!entrada.files.length) return;
      const fd = new FormData(); fd.append('vcf', entrada.files[0]);
      const aviso = avisar('info', `Enviando e validando o VCF de ${d.nome}…`);
      try { await api('POST', `/api/pacientes/${p.id}/descendentes/${d.id}/vcf`, { form: fd }); aviso.remove(); estado.avisoPendente = 'VCF do filho já testado anexado: ele entra como evidência e sai da lista de pessoas em risco.'; aoMudarRota(); }
      catch (e) { aviso.remove(); avisar('erro', (e.campos && e.campos.vcf) || e.message); entrada.value = ''; }
    });
    if (d.testado) return el('div', {}, el('div', { class: 'chips' }, chip('Já testado: evidência', 'chip-ok', 'dna')), el('div', { class: 'pequeno texto-suave', text: `${fmtBytes(d.vcf.tamanho)} · hash ${d.vcf.hash_curto}` }),
      botao('Remover VCF', { classe: 'botao-perigo botao-pequeno', icone: 'lixeira', ariaLabel: `Remover o VCF de ${d.nome}`, onclick: async () => { if (!window.confirm(`Remover o VCF de ${d.nome}? Essa pessoa volta a ser analisada como pessoa em risco.`)) return; try { await api('DELETE', `/api/pacientes/${p.id}/descendentes/${d.id}/vcf`); estado.avisoPendente = 'VCF removido.'; aoMudarRota(); } catch (e) { avisar('erro', e.message); } } }));
    return el('div', {}, el('label', { for: entrada.id, class: 'botao botao-secundario botao-pequeno' }, icone('upload'), 'Anexar VCF (já testado)'), entrada);
  }
  function resumoInferido(g) { // texto curto de um genitor inferido por parentes, para a tela de análise
    const quem = g.parentes.map((x) => `${x.rotulo}${x.vcf.presente ? ' (VCF' : ' (sem VCF'}${x.laudo_c9orf72 ? `, laudo ${x.laudo_c9orf72})` : ', sem laudo)'}`).join('; ');
    return quem || 'filho(a) já testado(a)';
  }
  function cartaoGenitores(p, op) {
    const cartao = el('div', { class: 'cartao' }, el('h2', { text: p.tipo === 'CASAL' ? 'Casal: parceira e parceiro' : 'Genitores' }), el('p', { class: 'texto-suave', text: 'Nome, nascimento, laudo do C9orf72 e VCF de cada genitor. O VCF fica cifrado em disco, nunca pode ser baixado e é decifrado só durante a análise. Para um genitor que não pôde ser testado, informe a situação clínica dele e adicione parentes testados.' }));
    const grade = el('div', { class: 'grade-2' });
    const parentes = [];
    for (const papel of PAPEIS_GENITOR) {
      const g = p.genitores[papel];
      const bloco = el('div', { class: 'bloco-genitor' }, el('h3', {}, icone('pessoa'), g.rotulo), el('dl', { class: 'lista-definicao' },
        el('dt', { text: 'Nome' }), el('dd', { text: g.nome }), el('dt', { text: 'Nascimento' }), el('dd', { text: `${fmtDataLocal(g.data_nascimento)} (${g.idade} anos)` }),
        el('dt', { text: 'Laudo C9orf72' }), el('dd', {}, g.laudo_c9orf72 ? el('div', { text: `${g.laudo_c9orf72} repetições` }) : estadoLaudo(g, false), blocoDocumento(p, 'LAUDO_C9ORF72', papel, g.laudo_documento))));
      const estadoVcf = el('div', { class: 'vcf-estado' });
      const entrada = el('input', { type: 'file', accept: '.vcf,.gz', class: 'sr-only', id: `vcf-${papel}`, 'aria-label': `Arquivo VCF: ${g.rotulo}` });
      entrada.addEventListener('change', async () => {
        if (!entrada.files.length) return;
        const fd = new FormData(); fd.append('vcf', entrada.files[0]);
        const aviso = avisar('info', `Enviando e validando o VCF (${g.rotulo})…`);
        try { const np = await api('POST', `/api/pacientes/${p.id}/genitores/${papel}/vcf`, { form: fd }); aviso.remove(); estado.avisoPendente = `VCF anexado (${g.rotulo}).`; aoMudarRota(); void np; }
        catch (e) { aviso.remove(); avisar('erro', `${g.rotulo}: ${(e.campos && e.campos.vcf) || e.message}`); entrada.value = ''; }
      });
      if (g.vcf.presente) {
        estadoVcf.append(chip('VCF anexado', 'chip-ok', 'dna'), el('span', { class: 'detalhe', text: `${fmtBytes(g.vcf.tamanho)} · enviado em ${fmtData(g.vcf.enviado_em)} · hash ${g.vcf.hash_curto}` }),
          el('label', { for: `vcf-${papel}`, class: 'botao botao-secundario botao-pequeno' }, icone('upload'), 'Substituir'), entrada,
          botao('Remover', { classe: 'botao-perigo botao-pequeno', icone: 'lixeira', ariaLabel: `Remover VCF: ${g.rotulo}`, onclick: async () => { if (!window.confirm(`Remover o VCF (${g.rotulo})? O arquivo cifrado será apagado.`)) return; try { await api('DELETE', `/api/pacientes/${p.id}/genitores/${papel}/vcf`); estado.avisoPendente = 'VCF removido.'; aoMudarRota(); } catch (e) { avisar('erro', e.message); } } }));
      } else {
        estadoVcf.append(chip(g.inferido_por_parentes ? 'Sem VCF' : 'Sem exame', 'chip-aviso', 'alerta'), el('span', { class: 'detalhe', text: g.inferido_por_parentes ? 'Sem exame: o genótipo será inferido pelos parentes testados.' : `${g.falta_exame || 'Sem exame: a análise exigirá um parente testado ou a suposição de não portador.'}${g.laudo_informado ? ' Com a suposição, só o laudo do C9orf72 deste genitor é considerado.' : ''}` }),
          el('label', { for: `vcf-${papel}`, class: 'botao botao-pequeno' }, icone('upload'), 'Anexar VCF'), entrada);
      }
      bloco.append(estadoVcf);
      if (g.aviso_qualidade) bloco.append(el('p', { class: 'pequeno', text: g.aviso_qualidade }));
      if (!g.vcf.presente) parentes.push(blocoSemExame(p, papel, g, op));
      bloco.append(el('div', { class: 'acoes' }, botao('Editar dados', { classe: 'botao-link botao-pequeno', icone: 'editar', onclick: () => editarGenitor(p, papel, g, op, bloco) })));
      grade.append(bloco);
    }
    cartao.append(grade, ...parentes);
    return cartao;
  }
  function blocoDocumento(p, tipo, papel, doc) { // documento anexado (prontuário ou laudo): abrir, substituir, remover
    const rotulo = tipo === 'PRONTUARIO' ? 'documento do prontuário' : 'arquivo do laudo';
    const entrada = el('input', { type: 'file', accept: '.pdf,.jpg,.jpeg,.png', class: 'sr-only', id: `doc-${tipo}-${papel || 'reg'}`, 'aria-label': `Enviar ${rotulo} (PDF, JPG ou PNG)` });
    entrada.addEventListener('change', async () => {
      if (!entrada.files.length) return;
      const fd = new FormData(); fd.append('tipo', tipo); if (papel) fd.append('papel', papel); fd.append('arquivo', entrada.files[0]);
      const aviso = avisar('info', `Enviando o ${rotulo}…`);
      try { await api('POST', `/api/pacientes/${p.id}/documentos`, { form: fd }); aviso.remove(); const semNumero = tipo === 'LAUDO_C9ORF72' && papel && p.genitores[papel] && !p.genitores[papel].laudo_c9orf72; estado.avisoPendente = tipo === 'PRONTUARIO' ? 'Documento do prontuário anexado.' : (semNumero ? 'Laudo anexado. Falta digitar o nº de repetições em "Editar dados": o arquivo não é lido e, sem o número, o C9orf72 fica indeterminado.' : 'Laudo anexado.'); aoMudarRota(); }
      catch (e) { aviso.remove(); avisar('erro', (e.campos && (e.campos.arquivo || e.campos.papel)) || e.message); entrada.value = ''; }
    });
    const caixa = el('div', { class: 'vcf-estado documento-estado' });
    if (doc) {
      caixa.append(chip(tipo === 'PRONTUARIO' ? 'Documento anexado' : 'Laudo anexado', 'chip-ok', 'arquivo'), el('span', { class: 'detalhe', text: `${doc.nome} · ${fmtBytes(doc.tamanho)} · ${fmtData(doc.enviado_em)}` }),
        el('a', { class: 'botao botao-pequeno', href: `/api/pacientes/${p.id}/documentos/${doc.id}`, target: '_blank', rel: 'noopener' }, icone('arquivo'), 'Abrir'),
        el('label', { for: entrada.id, class: 'botao botao-secundario botao-pequeno' }, icone('upload'), 'Substituir'), entrada,
        botao('Remover', { classe: 'botao-perigo botao-pequeno', icone: 'lixeira', ariaLabel: `Remover ${rotulo}`, onclick: async () => { if (!window.confirm(`Remover o ${rotulo}? O arquivo cifrado será apagado.`)) return; try { await api('DELETE', `/api/pacientes/${p.id}/documentos/${doc.id}`); estado.avisoPendente = 'Documento removido.'; aoMudarRota(); } catch (e) { avisar('erro', e.message); } } }));
    } else {
      caixa.append(chip(tipo === 'PRONTUARIO' ? 'Sem documento' : 'Sem arquivo do laudo', 'chip-aviso', 'alerta'), el('label', { for: entrada.id, class: 'botao botao-pequeno' }, icone('upload'), tipo === 'PRONTUARIO' ? 'Anexar documento' : 'Anexar laudo'), entrada);
    }
    return caixa;
  }
  function editarGenitor(p, papel, g, op, bloco) {
    const f = camposGenitor(papel.toLowerCase(), g.rotulo, g, false);
    const form = el('form', { novalidate: true, onsubmit: async (ev) => {
      ev.preventDefault();
      try { await api('PUT', `/api/pacientes/${p.id}/genitores/${papel}`, { json: f.valor() }); estado.avisoPendente = 'Dados do genitor atualizados.'; aoMudarRota(); }
      catch (e) { aplicarErros(f.campos, Object.fromEntries(Object.entries(e.campos || {}).map(([k, v]) => [k.includes('.') ? k : `${papel.toLowerCase()}.${k}`, v])), Object.keys(e.campos || {}).length ? null : e.message); }
    } }, f.bloco, el('div', { class: 'acoes' }, botao('Cancelar', { classe: 'botao-secundario botao-pequeno', onclick: () => aoMudarRota() }), botao('Salvar', { tipo: 'submit', classe: 'botao-pequeno', icone: 'check' })));
    bloco.replaceWith(el('div', { class: 'bloco-genitor' }, form));
    f.nome.input.focus();
  }
  function cartaoDescendentes(p) {
    const cartao = el('div', { class: 'cartao tabela-cartao' });
    const cab = el('div', { class: 'cabecalho-tabela' }, el('h2', { text: p.tipo === 'FAMILIA' ? 'Filhos' : 'Pessoa atendida' }));
    const podeAnalisar = p.pode_analisar !== undefined ? p.pode_analisar : PAPEIS_GENITOR.some((g) => p.genitores[g].vcf.presente);
    const acoes = el('div', { class: 'acoes acoes-compactas' });
    if (p.tipo === 'FAMILIA') {
      acoes.append(botao('Adicionar filho(a)', { classe: 'botao-secundario botao-pequeno', icone: 'mais', onclick: () => formDescendente(p, null, cartao) }));
      if (p.descendentes.filter((d) => !d.testado).length > 1 && podeAnalisar) acoes.append(linkBotao('Analisar todos', `#/analise?paciente=${p.id}&descendente=todos`, { classe: 'botao-pequeno', icone: 'frasco' }));
    }
    cab.append(acoes);
    const botaoAnalisar = (d) => { const a = linkBotao('Analisar', podeAnalisar ? `#/analise?paciente=${p.id}&descendente=${d.id}` : '#', { classe: 'botao-pequeno', icone: 'frasco' }); if (!podeAnalisar) desativarAnalise(a, p); return a; };
    cartao.append(cab, tabela([
      { rotulo: 'Nome', valor: (d) => el('div', {}, el('strong', { text: d.nome }), d.menor_de_idade ? el('div', {}, chip('menor de idade', 'chip-aviso')) : null) },
      { rotulo: 'Idade', valor: (d) => `${d.idade} anos`, num: true }, { rotulo: 'Sexo', valor: (d) => ROTULO_SEXO[d.sexo] },
      { rotulo: 'Última análise', valor: (d) => (d.ultima_analise ? el('div', {}, el('div', { class: 'pequeno', text: fmtData(d.ultima_analise.executado_em, true) }), el('div', { class: 'chips' }, d.ultima_analise.genes_de_risco.map((g) => chip(g, 'chip-azul'))), el('div', { class: 'pequeno texto-suave', text: d.ultima_analise.sem_locus ? SEM_LOCUS : `herdou ${fmtPct(d.ultima_analise.p_portador)} · ${d.ultima_analise.condicionado ? `a partir dos ${fmtNum(d.ultima_analise.idade_referencia, 0)} anos: ${fmtPct(d.ultima_analise.p_manifesta)}` : `risco vitalício ${fmtPct(d.ultima_analise.p_manifesta)}`}` })) : el('span', { class: 'texto-suave', text: 'Sem análise' })) },
      ...(p.tipo === 'FAMILIA' ? [{ rotulo: 'Teste próprio', valor: (d) => celulaTeste(p, d) }] : []),
      { rotulo: 'Ações', valor: (d) => el('div', { class: 'acoes acoes-compactas' }, d.testado ? null : botaoAnalisar(d), botao('Editar', { classe: 'botao-secundario botao-pequeno', icone: 'editar', ariaLabel: `Editar ${d.nome}`, onclick: () => formDescendente(p, d, cartao) }),
        p.tipo === 'FAMILIA' && p.descendentes.length > 1 ? botao('Remover', { classe: 'botao-perigo botao-pequeno', icone: 'lixeira', ariaLabel: `Remover ${d.nome}`, onclick: async () => { if (!window.confirm(`Remover ${d.nome} deste registro? As análises e consentimentos dessa pessoa serão apagados.`)) return; try { await api('DELETE', `/api/pacientes/${p.id}/descendentes/${d.id}`); estado.avisoPendente = 'Descendente removido.'; aoMudarRota(); } catch (e) { avisar('erro', e.message); } } }) : null) }], p.descendentes, { blocos: true }));
    return cartao;
  }
  function formDescendente(p, d, cartao) {
    const f = camposDescendente('descendente', d || {});
    const form = el('form', { novalidate: true, onsubmit: async (ev) => {
      ev.preventDefault();
      try { await api(d ? 'PUT' : 'POST', d ? `/api/pacientes/${p.id}/descendentes/${d.id}` : `/api/pacientes/${p.id}/descendentes`, { json: f.valor() }); estado.avisoPendente = d ? 'Descendente atualizado.' : 'Filho(a) incluído(a).'; aoMudarRota(); }
      catch (e) { aplicarErros(f.campos, Object.fromEntries(Object.entries(e.campos || {}).map(([k, v]) => [k.startsWith('descendente') ? k : `descendente.${k}`, v])), Object.keys(e.campos || {}).length ? null : e.message); }
    } }, el('h3', { text: d ? `Editar: ${d.nome}` : 'Novo filho(a)' }), f.no, el('div', { class: 'acoes' }, botao('Cancelar', { classe: 'botao-secundario botao-pequeno', onclick: () => aoMudarRota() }), botao('Salvar', { tipo: 'submit', classe: 'botao-pequeno', icone: 'check' })));
    cartao.append(el('div', { class: 'cartao-interno' }, form));
    f.campos['descendente.nome'].input.focus();
  }
  function cartaoHistorico(p) {
    const cartao = el('div', { class: 'cartao' }, el('h2', { text: p.tipo === 'FAMILIA' ? 'Risco por filho e histórico de análises' : 'Histórico de análises' }));
    if (!p.analises.length) { cartao.append(el('p', { class: 'texto-suave', text: 'Nenhuma análise executada ainda. O resumo de cada análise fica guardado aqui, cifrado; o resultado completo fica disponível por duas horas após a execução.' })); return cartao; }
    const comp = p.comparativo.map((a) => linhaRisco(a, a.descendente_nome));
    cartao.append(el('h3', { text: 'Última análise de cada pessoa: as três respostas' }), tabela([
      { rotulo: 'Pessoa', chave: 'pessoa' }, { rotulo: 'Sexo', chave: 'sexo' }, { rotulo: 'Referência', chave: 'referencia' }, { rotulo: '1. Herdou / transmissão', chave: 'herdou', num: true }, { rotulo: '2. Manifestação até o horizonte, pela referência [95 %]', chave: 'manifestacao', num: true }, { rotulo: 'Risco vitalício (desde o nascimento)', chave: 'vitalicio', num: true }, { rotulo: '3. Idade provável de início', chave: 'inicio' }, { rotulo: 'Suposição', chave: 'suposicao' }, { rotulo: 'Quando', chave: 'quando' }, { rotulo: 'Resultado', valor: (c) => (c.tem_resultado ? linkBotao('Abrir', `#/analises/${p.id}/${c.id}`, { classe: 'botao-pequeno', icone: 'grafico' }) : '—') }], comp, { blocos: true }));
    cartao.append(el('details', {}, el('summary', { text: `Todas as análises (${p.analises.length})` }), tabela([
      { rotulo: 'Quando', valor: (a) => fmtData(a.executado_em) }, { rotulo: 'Pessoa', valor: (a) => (a.descendente_id === null ? 'Futuro filho' : (p.descendentes.find((d) => d.id === a.descendente_id) || {}).nome || `descendente ${a.descendente_id}`) },
      { rotulo: 'Modo', valor: (a) => `${a.modo} · ${a.motor} · N=${fmtNum(a.n, 0)} · semente ${a.semente}${a.hipoteses ? ' · hipóteses' : ''}${a.cox ? ' · Cox' : ''}` },
      { rotulo: 'Genes', valor: (a) => el('div', { class: 'chips' }, (a.resumo.genes_de_risco || []).length ? a.resumo.genes_de_risco.map((g) => chip(g, 'chip-azul')) : chip(SEM_LOCUS, 'chip-neutro')) },
      { rotulo: 'Herdou', valor: (a) => ((a.resumo.genes_de_risco || []).length ? fmtPct(a.resumo.combinado.p_portador_qualquer_exato) : '—'), num: true }, { rotulo: 'Risco vitalício (desde o nascimento)', valor: (a) => ((a.resumo.genes_de_risco || []).length ? fmtPct(a.resumo.combinado.p_manifesta_qualquer_exato) : '—'), num: true },
      { rotulo: 'Ações', valor: (a) => el('div', { class: 'acoes acoes-compactas' }, a.tem_resultado ? linkBotao('Abrir resultado', `#/analises/${p.id}/${a.id}`, { classe: 'botao-pequeno', icone: 'grafico' }) : null, linkBotao('Repetir', `#/analise?paciente=${p.id}${a.descendente_id !== null ? `&descendente=${a.descendente_id}` : ''}`, { classe: 'botao-secundario botao-pequeno', icone: 'frasco' })) }], p.analises.slice().reverse())));
    return cartao;
  }
  function renderConsentimentos(p) {
    const cartao = el('div', { class: 'cartao' }, el('h2', { text: 'Consentimentos para pesquisa' }),
      el('p', { text: 'Separado do atendimento, específico e destacado; nunca vem pré-marcado; revogar é tão simples quanto conceder e tem efeito imediato (art. 8º, §5º). Como os dados genéticos são dos genitores e, quando anexados, de parentes deles, a liberação exige o consentimento de cada genitor, de cada parente testado e de cada descendente (ou responsável, se menor de 18).' }));
    cartao.append(tabela([{ rotulo: 'Titular', valor: (e) => e.rotulo }, { rotulo: 'Situação', valor: (e) => chip(e.consentido ? 'Consentimento ativo' : 'Sem consentimento', e.consentido ? 'chip-ok' : 'chip-neutro', e.consentido ? 'check' : null) }], p.pesquisa.exigidos, { legenda: 'Consentimentos exigidos para liberar o caso' }));
    const ativos = p.consentimentos.filter((c) => c.ativo), historico = p.consentimentos.filter((c) => !c.ativo);
    const nomeDesc = (c) => (c.descendente_id === null ? '' : ` (${(p.descendentes.find((d) => d.id === c.descendente_id) || {}).nome || ''})`);
    if (ativos.length) cartao.append(tabela([{ rotulo: 'Titular', valor: (c) => `${c.titular_rotulo}${nomeDesc(c)}` }, { rotulo: 'Quem consentiu', chave: 'nome_titular' }, { rotulo: 'Versão do termo', chave: 'versao_termo' }, { rotulo: 'Data', valor: (c) => fmtData(c.concedido_em) },
      { rotulo: 'Ação', valor: (c) => botao('Revogar', { classe: 'botao-perigo botao-pequeno', ariaLabel: `Revogar consentimento de ${c.titular_rotulo}${nomeDesc(c)}`, onclick: async () => { try { const np = await api('POST', `/api/pacientes/${p.id}/consentimentos/${c.id}/revogar`); avisar('sucesso', 'Consentimento revogado com efeito imediato.'); cartao.replaceWith(renderConsentimentos(np)); } catch (e) { avisar('erro', e.message); } } }) }], ativos, { legenda: 'Consentimentos ativos' }));
    if (historico.length) cartao.append(el('details', {}, el('summary', { text: `Consentimentos revogados (${historico.length})` }), tabela([{ rotulo: 'Titular', valor: (c) => `${c.titular_rotulo}${nomeDesc(c)}` }, { rotulo: 'Quem consentiu', chave: 'nome_titular' }, { rotulo: 'Concedido', valor: (c) => fmtData(c.concedido_em) }, { rotulo: 'Revogado', valor: (c) => fmtData(c.revogado_em) }], historico)));
    const pendentes = p.pesquisa.exigidos.filter((e) => !e.consentido);
    if (pendentes.length) {
      const opcoes = pendentes.map((e) => [`${e.titular}:${e.descendente_id === null ? '' : e.descendente_id}:${e.parente_id === null || e.parente_id === undefined ? '' : e.parente_id}`, e.rotulo]);
      const titular = campo({ nome: 'titular', rotulo: 'Titular que consente', tipo: 'select', obrigatorio: true, opcoes });
      const nomeT = campo({ nome: 'nome_titular', rotulo: 'Nome de quem consentiu', obrigatorio: true, dica: 'Preenchido com o nome do cadastro quando houver; confira. Para menor de 18 anos é obrigatória a identificação do responsável legal (art. 14, §1º).', atributos: { autocomplete: 'off' } });
      const preencher = () => {
        const [t, did] = titular.valor().split(':');
        if (t === 'MAE' || t === 'PAI') nomeT.input.value = p.genitores[t].nome;
        else if (t === 'DESCENDENTE') nomeT.input.value = (p.descendentes.find((d) => String(d.id) === did) || {}).nome || '';
        else nomeT.input.value = '';
      };
      titular.input.addEventListener('change', preencher); preencher();
      const confirmado = marcacao({ nome: 'confirmado', rotulo: `Declaro que o titular acima leu o termo (versão ${p.termo_consentimento.versao}) e consentiu, de forma livre, específica e informada, com o uso do caso em pesquisa de forma pseudonimizada.` });
      const campos = { titular, nome_titular: nomeT, confirmado };
      cartao.append(secaoNumerada(1, 'Registrar consentimento', el('details', {}, el('summary', { text: `Ler o termo de consentimento (versão ${p.termo_consentimento.versao})` }), el('ul', {}, p.termo_consentimento.itens.map((t) => el('li', { text: t })))),
        el('form', { novalidate: true, onsubmit: async (ev) => {
          ev.preventDefault();
          const erros = {};
          if (nomeT.valor().trim().length < 3) erros.nome_titular = 'Informe o nome de quem consentiu.';
          if (!confirmado.valor()) erros.confirmado = 'Marque a declaração de consentimento.';
          if (Object.keys(erros).length) { aplicarErros(campos, erros); return; }
          const [t, did, xid] = titular.valor().split(':');
          try { const np = await api('POST', `/api/pacientes/${p.id}/consentimentos`, { json: { titular: t, descendente_id: did ? Number(did) : null, parente_id: xid ? Number(xid) : null, nome_titular: nomeT.valor().trim(), confirmado: true, versao_termo: p.termo_consentimento.versao } }); avisar('sucesso', np.liberado_para_pesquisa ? 'Consentimento registrado. Caso liberado para pesquisa (pseudonimizado).' : 'Consentimento registrado.'); cartao.replaceWith(renderConsentimentos(np)); }
          catch (e) { aplicarErros(campos, e.campos, Object.keys(e.campos).length ? null : e.message); }
        } }, el('div', { class: 'grade-campos' }, titular.no, nomeT.no), confirmado.no, el('div', { class: 'acoes' }, botao('Registrar consentimento', { tipo: 'submit', icone: 'check' })))));
    } else cartao.append(el('p', { class: 'texto-suave', text: 'Todos os titulares exigidos já consentiram.' }));
    return cartao;
  }

  // ---------------------------------------------------------------------------------------------
  // Médico: nova análise
  // ---------------------------------------------------------------------------------------------
  function camposSimulacao(valores = {}) {
    const n = campo({ nome: 'n', rotulo: 'N (fecundações simuladas)', tipo: 'number', valor: valores.n || 10000, atributos: { min: 100, max: 200000, step: 100 } });
    const semente = campo({ nome: 'semente', rotulo: 'Semente', tipo: 'number', valor: valores.semente === undefined ? 42 : valores.semente, atributos: { min: 0, step: 1 }, dica: 'Garante a reprodutibilidade.' });
    const motor = campo({ nome: 'motor', rotulo: 'Motor', tipo: 'select', valor: valores.motor || 'pymc', opcoes: [['pymc', 'PyMC (motor declarado no TCC; o NumPy roda como verificação cruzada)'], ['numpy', 'NumPy (o PyMC roda como verificação cruzada)']], dica: 'Os dois motores rodam em toda análise, com o mesmo N; o escolhido dá os números do resultado e o outro confere.' });
    const cox = marcacao({ nome: 'cox', rotulo: 'Comparar com o modelo de Cox (CoxPHFitter) na coorte de portadores', marcado: valores.cox !== false });
    const dMae = campo({ nome: 'c9_delta_mae', rotulo: 'c9_delta_mae: variação de repetições do alelo materno na transmissão', tipo: 'number', opcional: true, atributos: { step: 1, min: -200, max: 200 } });
    const dPai = campo({ nome: 'c9_delta_pai', rotulo: 'c9_delta_pai: variação de repetições do alelo paterno na transmissão', tipo: 'number', opcional: true, atributos: { step: 1, min: -200, max: 200 } });
    const ant = campo({ nome: 'c9_antecipacao', rotulo: 'c9_antecipacao: antecipação da idade de início (anos)', tipo: 'number', opcional: true, atributos: { step: 0.5, min: 0, max: 40 } });
    const hipoteses = el('details', {}, el('summary', { text: 'Hipóteses experimentais (transmissão do C9orf72 por repetições)' }), el('p', { class: 'pequeno texto-suave', text: 'Sem base na literatura citada no TCC; servem para explorar sensibilidade, não para estimar risco. Vazio = modelo por dosagem (padrão). O delta só se aplica a alelos a partir da faixa intermediária (≥ 24).' }), el('div', { class: 'grade-campos' }, dMae.no, dPai.no, ant.no));
    const tornado = marcacao({ nome: 'tornado', rotulo: 'Sensibilidade tipo tornado: um parâmetro por vez, dentro das faixas publicadas (Tabela 20, Figura 12)', marcado: valores.tornado === true });
    const no = el('div', {}, el('div', { class: 'grade-campos grade-campos-3' }, n.no, semente.no, motor.no), cox.no, tornado.no, hipoteses);
    const campos = { n, semente, motor, c9_delta_mae: dMae, c9_delta_pai: dPai, c9_antecipacao: ant };
    return { no, campos, preencher(fd) { for (const c of [n, semente, motor, dMae, dPai, ant]) if (String(c.valor()).trim() !== '') fd.append(c.nome, String(c.valor()).trim()); fd.append('cox', cox.valor() ? '1' : '0'); fd.append('tornado', tornado.valor() ? '1' : '0'); } };
  }
  function caixaProgresso() {
    const texto = el('span', { text: '' });
    const caixa = el('div', { class: 'ocupado', role: 'status', hidden: true }, texto);
    return { caixa, mostrar(t) { texto.textContent = t; caixa.hidden = false; }, esconder() { caixa.hidden = true; } };
  }
  async function telaAnalise(area, params) {
    definirTitulo('Nova análise');
    const pacienteId = params[0] ? Number(params[0]) : null;
    const descParam = params[1] || null;
    if (pacienteId) return analiseDoRegistro(area, pacienteId, descParam);
    definirTrilha([['Área clínica'], ['Nova análise (sem registro)']]);
    const [cen, bases] = await Promise.all([api('GET', '/api/cenarios'), api('GET', '/api/base')]);
    area.append(cabecalhoTela({ titulo: 'Nova análise sem registro', subtitulo: 'Para uma simulação avulsa, por exemplo um casal que planeja filhos e ainda não tem cadastro. Os VCFs enviados não são guardados e o resultado fica disponível a você por tempo limitado.', chips: [chip('Sem vínculo com paciente', 'chip-neutro')], acoes: [linkBotao('Cadastrar paciente', '#/pacientes/novo', { classe: 'botao-secundario', icone: 'mais' })] }));
    const mVcf = marcacao({ nome: 'modo', tipo: 'radio', valor: 'vcf', rotulo: 'Enviar os VCFs da mãe e do pai (não são guardados)', marcado: true });
    const mCen = marcacao({ nome: 'modo', tipo: 'radio', valor: 'cenario', rotulo: 'Usar um cenário sintético de exemplo (VCFs fictícios do artefato)' });
    const modo = el('fieldset', {}, el('legend', { text: 'Origem dos dados genéticos' }), mVcf.no, mCen.no);
    const vcfMae = campo({ nome: 'vcf_mae', rotulo: 'VCF da mãe', tipo: 'file', obrigatorio: true, dica: 'Arquivo .vcf (ou .vcf.gz), GRCh38, até 20 MB.', atributos: { accept: '.vcf,.gz' } });
    const vcfPai = campo({ nome: 'vcf_pai', rotulo: 'VCF do pai', tipo: 'file', obrigatorio: true, dica: 'Arquivo .vcf (ou .vcf.gz), GRCh38, até 20 MB.', atributos: { accept: '.vcf,.gz' } });
    const cenario = campo({ nome: 'cenario', rotulo: 'Cenário de exemplo', tipo: 'select', opcoes: cen.cenarios.map((c) => [String(c.numero), `${c.numero}. ${c.descricao}`]), dica: cen.aviso });
    const blocoVcf = el('div', { class: 'grade-campos' }, vcfMae.no, vcfPai.no);
    const blocoCen = el('div', {}, cenario.no); blocoCen.hidden = true;
    const alternar = () => { blocoVcf.hidden = !mVcf.valor(); blocoCen.hidden = mVcf.valor(); };
    mVcf.input.addEventListener('change', alternar); mCen.input.addEventListener('change', alternar);
    const c9m = campo({ nome: 'c9orf72_mae', rotulo: 'Laudo do C9orf72 da mãe', opcional: true, dica: 'Nº de repetições GGGGCC do maior alelo (ex.: 45) ou dos dois alelos (ex.: 12,45).', atributos: { inputmode: 'numeric' } });
    const c9p = campo({ nome: 'c9orf72_pai', rotulo: 'Laudo do C9orf72 do pai', opcional: true, dica: 'Mesmo formato. Vazio em um dos dois = sem laudo: o C9orf72 fica indeterminado e sai do cálculo.', atributos: { inputmode: 'numeric' } });
    const sexo = campo({ nome: 'sexo', rotulo: 'Sexo do descendente', tipo: 'select', valor: '', opcoes: [['', 'Não informado'], ['F', 'Feminino'], ['M', 'Masculino']] });
    const idade = campo({ nome: 'idade_atual', rotulo: 'Idade atual sem sintomas (anos)', tipo: 'number', opcional: true, dica: 'Condiciona o risco ao descendente assintomático nessa idade. Vazio para um futuro filho.', atributos: { min: 0, max: 120, step: 1 } });
    const confirma = marcacao({ nome: 'confirma_assintomatico', rotulo: 'Confirmo que a pessoa analisada não apresenta sintomas de ELA' });
    const sim = camposSimulacao();
    const base = campo({ nome: 'base', rotulo: 'Base de anotação', tipo: 'select', valor: 'padrao', opcoes: opcoesDeBase({ base_em_uso: bases.em_uso ? bases.em_uso.nome : null, bases: bases.arquivos.map((a) => a.nome) }), dica: 'Linha de comando: --base-clinvar ou --so-tabela-curada.' });
    const horizonte = campo({ nome: 'horizonte', rotulo: 'Horizonte (anos)', tipo: 'number', opcional: true, dica: 'Vazio = o horizonte dos parâmetros (90 anos). Linha de comando: --horizonte.', atributos: { min: 1, max: 120, step: 1 } });
    const rotulo = campo({ nome: 'rotulo', rotulo: 'Rótulo do relatório', opcional: true, dica: 'Título do relatório. Não use nome de pessoa. Linha de comando: --rotulo.', atributos: { maxlength: 120 } });
    const amostraMae = campo({ nome: 'amostra_mae', rotulo: 'Amostra no VCF da mãe', opcional: true, dica: 'Nome da amostra, se o VCF tiver várias. Vazio = a primeira. Linha de comando: --amostra-mae.', atributos: { maxlength: 100 } });
    const amostraPai = campo({ nome: 'amostra_pai', rotulo: 'Amostra no VCF do pai', opcional: true, dica: 'Linha de comando: --amostra-pai.', atributos: { maxlength: 100 } });
    const config = campo({ nome: 'config', rotulo: 'Parâmetros alternativos (YAML)', tipo: 'file', opcional: true, dica: 'Vazio = parâmetros do artefato. Linha de comando: --config.', atributos: { accept: '.yaml,.yml' } });
    const tabelaVar = campo({ nome: 'tabela_variantes', rotulo: 'Tabela de variantes alternativa (CSV)', tipo: 'file', opcional: true, dica: 'Vazio = tabela curada do artefato. Linha de comando: --tabela-variantes.', atributos: { accept: '.csv' } });
    const semFiguras = marcacao({ nome: 'sem_figuras', rotulo: 'Não gerar as figuras (--sem-figuras)' });
    const avancadas = el('details', {}, el('summary', { text: 'Opções avançadas (as mesmas da linha de comando)' }), el('p', { class: 'pequeno texto-suave', text: 'Só nesta análise sem registro. Parâmetros ou tabela alternativos ficam declarados no resultado: ele deixa de ser o resultado do artefato com os parâmetros da literatura. Os arquivos em uso podem ser baixados em Modelo e parâmetros.' }),
      el('div', { class: 'grade-campos grade-campos-3' }, base.no, horizonte.no, rotulo.no, amostraMae.no, amostraPai.no), el('div', { class: 'grade-campos' }, config.no, tabelaVar.no), semFiguras.no);
    const campos = { vcf_mae: vcfMae, vcf_pai: vcfPai, cenario, c9orf72_mae: c9m, c9orf72_pai: c9p, sexo, idade_atual: idade, confirma_assintomatico: confirma, base, horizonte, rotulo, amostra_mae: amostraMae, amostra_pai: amostraPai, config, tabela_variantes: tabelaVar, ...sim.campos };
    const prog = caixaProgresso();
    const enviar = botao('Executar análise', { tipo: 'submit', icone: 'frasco' });
    const form = el('form', { novalidate: true, onsubmit: async (ev) => {
      ev.preventDefault();
      const erros = {};
      if (mVcf.valor()) { if (!vcfMae.input.files.length) erros.vcf_mae = 'Envie o VCF da mãe.'; if (!vcfPai.input.files.length) erros.vcf_pai = 'Envie o VCF do pai.'; }
      for (const c of [c9m, c9p]) if (c.valor().trim() && !/^\s*\d+\s*([,; ]\s*\d+\s*)?$/.test(c.valor())) erros[c.nome] = 'Use um número (45) ou dois (12,45).';
      if (Number(idade.valor()) > 0 && !confirma.valor()) erros.confirma_assintomatico = 'Confirme que a pessoa analisada não apresenta sintomas de ELA.';
      if (Object.keys(erros).length) { aplicarErros(campos, erros); return; }
      const fd = new FormData();
      fd.append('modo', mVcf.valor() ? 'vcf' : 'cenario');
      if (mVcf.valor()) { fd.append('vcf_mae', vcfMae.input.files[0]); fd.append('vcf_pai', vcfPai.input.files[0]); } else fd.append('cenario', cenario.valor());
      for (const c of [c9m, c9p, sexo, idade]) if (String(c.valor()).trim() !== '') fd.append(c.nome, String(c.valor()).trim());
      if (confirma.valor()) fd.append('confirma_assintomatico', '1');
      sim.preencher(fd);
      for (const c of [base, horizonte, rotulo, amostraMae, amostraPai]) if (String(c.valor()).trim() !== '') fd.append(c.nome, String(c.valor()).trim());
      for (const c of [config, tabelaVar]) if (c.input.files.length) fd.append(c.nome, c.input.files[0]);
      if (semFiguras.valor()) fd.append('sem_figuras', '1');
      enviar.disabled = true; prog.mostrar('Executando as três camadas (ingestão e anotação, rede bayesiana e Monte Carlo, sobrevivência)… isso leva alguns segundos.'); form.setAttribute('aria-busy', 'true');
      try {
        const r = await api('POST', '/api/analises', { form: fd });
        estado.analises[r.id] = { resultado: r, paciente: null };
        navegar(`#/resultado/${r.id}`);
      } catch (e) { aplicarErros(campos, e.campos, Object.keys(e.campos).length ? null : e.message); }
      finally { enviar.disabled = false; prog.esconder(); form.removeAttribute('aria-busy'); }
    } }, secaoNumerada(1, 'Origem dos dados genéticos', modo, blocoVcf, blocoCen), secaoNumerada(2, 'Laudo laboratorial do C9orf72', el('div', { class: 'grade-campos' }, c9m.no, c9p.no)),
      secaoNumerada(3, 'Descendente', el('div', { class: 'grade-campos' }, sexo.no, idade.no), confirma.no, dica('Obrigatória quando a idade atual é informada: o condicionamento pela idade só vale para quem não manifestou a doença. Com a idade, os três indicadores valem a partir dela, sem sintomas.')), secaoNumerada(4, 'Simulação', sim.no, avancadas), prog.caixa, el('div', { class: 'acoes acoes-direita' }, enviar));
    area.append(duasColunas(el('div', { class: 'cartao' }, form), cartaoApoio('Sobre a análise', ['Use esta tela só para simulações sem registro. Para um atendimento, cadastre o paciente: os VCFs ficam cifrados na ficha e o resumo de cada análise é guardado.', 'Os arquivos enviados aqui são apagados ao fim da execução.', 'O resultado traz as três respostas: se herdou (transmissão), a chance de manifestação por idade com banda de 95 % e a idade provável de início.'])));
  }
  async function analiseDoRegistro(area, pacienteId, descParam) {
    const op = await opcoesPacientes();
    const p = await api('GET', `/api/pacientes/${pacienteId}`);
    estado.nomesPacientes[p.id] = p.nome;
    definirTrilha([['Área clínica'], ['Pacientes', '#/pacientes'], [p.nome, `#/pacientes/${p.id}`], ['Nova análise']]);
    const sis = estado.sistema || {};
    area.append(cabecalhoTela({ titulo: 'Nova análise', subtitulo: `${p.nome} · Prontuário ${p.prontuario}`, chips: [chipTipo(p), chipVcfs(p)], acoes: [linkBotao('Voltar à ficha', `#/pacientes/${p.id}`, { classe: 'botao-secundario', icone: 'seta-esq' })] }));
    // 01 dados genéticos
    const blocos = el('div', { class: 'grade-2' });
    const assumir = {};
    const inferidos = []; // genitores sem VCF cujo genótipo será inferido por parentes
    const camposSup = {};
    for (const papel of PAPEIS_GENITOR) {
      const g = p.genitores[papel];
      const bloco = el('div', { class: 'bloco-genitor' }, el('h3', {}, icone('pessoa'), g.rotulo), el('dl', { class: 'lista-definicao' }, el('dt', { text: 'Nome' }), el('dd', { text: g.nome }), el('dt', { text: 'Laudo C9orf72' }), g.laudo_c9orf72 ? el('dd', { text: `${g.laudo_c9orf72} repetições (da ficha)` }) : el('dd', {}, estadoLaudo(g, true))));
      if (g.vcf.presente) bloco.append(el('div', { class: 'vcf-estado' }, chip('VCF anexado', 'chip-ok', 'dna'), el('span', { class: 'detalhe', text: `${fmtBytes(g.vcf.tamanho)} · hash ${g.vcf.hash_curto}` })));
      else if (g.inferido_por_parentes) {
        inferidos.push(papel);
        bloco.append(el('div', { class: 'vcf-estado' }, chip('Sem VCF: genótipo inferido por parentes', 'chip-azul', 'dna'), el('span', { class: 'detalhe', text: resumoInferido(g) })),
          el('dl', { class: 'lista-definicao' }, el('dt', { text: 'Situação clínica' }), g.situacao_clinica ? el('dd', { text: `${g.situacao_rotulo}${g.idade_situacao !== null && g.idade_situacao !== undefined ? `, ${g.idade_situacao} anos` : ''}` }) : el('dd', {}, el('div', { class: 'chips' }, chip('Não informada: obrigatória para analisar', 'chip-aviso', 'alerta')), linkBotao('Informar na ficha', `#/pacientes/${p.id}`, { classe: 'botao-secundario botao-pequeno', icone: 'editar' }))),
          el('p', { class: 'pequeno texto-suave', text: op.inferencia_por_parentes || '' }));
      }
      else {
        const m = marcacao({ nome: `assumir_${papel}`, rotulo: `Assumir que ${g.nome} não tem variante de risco (sem exame). ${g.laudo_informado ? 'O laudo do C9orf72 informado continua valendo.' : (g.laudo_documento ? 'O arquivo do laudo está anexado, mas o nº de repetições não foi digitado: sem o número, assume-se também laudo normal do C9orf72.' : 'Sem laudo, assume-se também laudo normal do C9orf72.')}` });
        assumir[papel] = m; camposSup[`assumir_${papel}`] = m;
        bloco.append(el('div', { class: 'vcf-estado' }, chip('Sem VCF', 'chip-aviso', 'alerta'), el('span', { class: 'detalhe', text: 'Anexe o arquivo na ficha ou marque a suposição abaixo.' }), linkBotao('Anexar na ficha', `#/pacientes/${p.id}`, { classe: 'botao-secundario botao-pequeno', icone: 'upload' })), m.no, el('p', { class: 'pequeno texto-suave', text: op.suposicao_nao_portador }));
      }
      blocos.append(bloco);
    }
    const semVcf = PAPEIS_GENITOR.filter((g) => !p.genitores[g].vcf.presente && !p.genitores[g].inferido_por_parentes);
    const priorAvos = inferidos.length ? campo({ nome: 'prior_avos', rotulo: 'Avô ou avó sem exame', tipo: 'select', valor: 'nao_portador', opcoes: [['nao_portador', 'Suposto não portador (padrão; declarado no resultado)'], ['hardy_weinberg', 'Prior de Hardy-Weinberg com a frequência alélica da base de anotação']], dica: 'Sem frequência na base para a variante, vale a suposição de não portador. Com tio testado e avós sem exame, a prior de Hardy-Weinberg entra sempre que houver frequência.' }) : null;
    const secao1 = secaoNumerada(1, 'Dados genéticos (da ficha)', blocos, priorAvos ? priorAvos.no : null, inferidos.length && p.tipo === 'CASAL' ? el('div', { class: 'alerta alerta-aviso' }, icone('alerta'), el('p', { text: op.aviso_parceiro_inferido || '' })) : null);
    // 02 descendente / futuro filho
    const emRisco = p.descendentes.filter((d) => !d.testado); // filho que já fez o teste é evidência, não pessoa em risco
    let alvoCampo = null, sexoFilho = null;
    let secao2;
    if (p.tipo === 'CASAL') {
      sexoFilho = campo({ nome: 'sexo_filho', rotulo: 'Sexo do futuro filho', tipo: 'select', valor: '', opcoes: [['', 'Não informado: calcular para os dois sexos'], ['F', 'Feminino'], ['M', 'Masculino']], dica: 'O sexo só altera a idade de início do C9orf72; com "não informado", o resultado mostra os dois lado a lado.' });
      secao2 = secaoNumerada(2, 'Futuro filho', el('p', { text: 'A análise estima a probabilidade de transmissão (herdar ao menos uma variante), a chance de manifestação ao longo da vida e a idade provável de início para um futuro filho do casal.' }), sexoFilho.no);
    } else if (p.tipo === 'PESSOA') {
      const d = p.descendentes[0];
      secao2 = secaoNumerada(2, 'Pessoa atendida', el('dl', { class: 'lista-definicao' }, el('dt', { text: 'Nome' }), el('dd', { text: d.nome }), el('dt', { text: 'Sexo' }), el('dd', { text: ROTULO_SEXO[d.sexo] }), el('dt', { text: 'Idade atual (sem sintomas)' }), el('dd', { text: `${d.idade} anos` })), dica('Sexo e idade vêm do cadastro e condicionam o risco à pessoa assintomática nessa idade.'));
    } else {
      alvoCampo = campo({ nome: 'descendente_id', rotulo: 'Filho(a) a analisar', tipo: 'select', obrigatorio: true, valor: descParam || (emRisco[0] ? String(emRisco[0].id) : ''), opcoes: [...emRisco.map((d) => [String(d.id), `${d.nome} (${d.idade} anos, ${ROTULO_SEXO[d.sexo]})`]), ['todos', `Todos os filhos em risco (${emRisco.length}), um por vez`]] });
      secao2 = secaoNumerada(2, 'Filho(a)', alvoCampo.no, dica(`Cada filho recebe a própria análise, com seu sexo e idade; o comparativo fica na ficha.${emRisco.length < p.descendentes.length ? ' Filho que já fez o teste entra como evidência sobre o genitor sem exame e não é analisado.' : ''}`));
    }
    const confirma = p.tipo === 'CASAL' ? null : marcacao({ nome: 'confirma_assintomatico', rotulo: p.tipo === 'FAMILIA' ? 'Confirmo que a pessoa analisada não apresenta sintomas de ELA (vale para cada filho analisado nesta execução)' : 'Confirmo que a pessoa analisada não apresenta sintomas de ELA' });
    if (confirma) secao2.append(confirma.no, dica('O condicionamento pela idade só vale para quem não manifestou a doença. Só a confirmação e a data ficam guardadas, sem nenhum dado clínico.'));
    // 03 simulação (+ cenário de exemplo quando em demonstração)
    const sim = camposSimulacao();
    let cenario = null, mCen = null;
    if (sis.demonstracao) {
      const cen = await api('GET', '/api/cenarios');
      mCen = marcacao({ nome: 'modo_cenario', rotulo: 'Ambiente de demonstração: usar um cenário sintético de exemplo em vez dos VCFs da ficha' });
      cenario = campo({ nome: 'cenario', rotulo: 'Cenário de exemplo', tipo: 'select', opcoes: cen.cenarios.map((c) => [String(c.numero), `${c.numero}. ${c.descricao}`]), dica: cen.aviso });
      cenario.no.hidden = true;
      mCen.input.addEventListener('change', () => { cenario.no.hidden = !mCen.valor(); });
    }
    const secao3 = secaoNumerada(3, 'Simulação', sim.no, mCen ? el('div', {}, mCen.no, cenario.no) : null);
    const prog = caixaProgresso();
    const enviar = botao(p.tipo === 'CASAL' ? 'Analisar transmissão' : 'Executar análise', { tipo: 'submit', icone: 'frasco' });
    const campos = { ...sim.campos, ...camposSup, descendente_id: alvoCampo, sexo_filho: sexoFilho, cenario, modo: mCen, confirma_assintomatico: confirma, prior_avos: priorAvos };
    const form = el('form', { novalidate: true, onsubmit: async (ev) => {
      ev.preventDefault();
      const erros = {};
      const usaCenario = mCen && mCen.valor();
      const assumidos = PAPEIS_GENITOR.filter((g) => assumir[g] && assumir[g].valor());
      if (confirma && !confirma.valor()) erros.confirma_assintomatico = 'Confirme que a pessoa analisada não apresenta sintomas de ELA.';
      const semSituacao = inferidos.filter((g) => !p.genitores[g].situacao_clinica);
      if (!usaCenario && semSituacao.length) { avisar('erro', `Informe na ficha a situação clínica de: ${semSituacao.map((g) => p.genitores[g].rotulo).join(' e ')} (genitor sem exame com parente testado).`); return; }
      if (!usaCenario) {
        for (const g of semVcf) if (!assumidos.includes(g)) erros[`assumir_${g}`] = 'Marque a suposição ou anexe o VCF na ficha.';
        if (semVcf.length === 2) erros.assumir_MAE = 'É preciso o VCF de ao menos um genitor.';
      }
      if (Object.keys(erros).length) { aplicarErros(campos, erros); return; }
      const alvos = p.tipo === 'CASAL' ? [null] : p.tipo === 'PESSOA' ? [p.descendentes[0]] : (alvoCampo.valor() === 'todos' ? emRisco : [p.descendentes.find((d) => String(d.id) === alvoCampo.valor())]);
      const sexos = p.tipo === 'CASAL' && !sexoFilho.valor() ? ['F', 'M'] : [sexoFilho ? sexoFilho.valor() : null];
      const execucoes = [];
      for (const d of alvos) for (const s of sexos) execucoes.push({ d, s });
      enviar.disabled = true; form.setAttribute('aria-busy', 'true');
      const ids = [];
      try {
        for (let i = 0; i < execucoes.length; i++) {
          const { d, s } = execucoes[i];
          prog.mostrar(execucoes.length > 1 ? `Executando análise ${i + 1} de ${execucoes.length}${d ? ` (${d.nome})` : s ? ` (sexo ${ROTULO_SEXO[s]})` : ''}…` : 'Executando as três camadas (ingestão e anotação, rede bayesiana e Monte Carlo, sobrevivência)… isso leva alguns segundos.');
          const fd = new FormData();
          fd.append('modo', usaCenario ? 'cenario' : 'vcf');
          if (usaCenario) fd.append('cenario', cenario.valor());
          fd.append('paciente_id', String(p.id));
          if (d) fd.append('descendente_id', String(d.id));
          if (s) fd.append('sexo_filho', s);
          if (assumidos.length) fd.append('assumir_nao_portador', assumidos.join(','));
          if (confirma && confirma.valor()) fd.append('confirma_assintomatico', '1');
          if (priorAvos && !usaCenario) fd.append('prior_avos', priorAvos.valor());
          sim.preencher(fd);
          const r = await api('POST', '/api/analises', { form: fd });
          estado.analises[r.id] = { resultado: r, paciente: { id: p.id, nome: p.nome, prontuario: p.prontuario, tipo: p.tipo, tipo_rotulo: p.tipo_rotulo }, descendente: d ? { id: d.id, nome: d.nome, idade: d.idade, sexo: d.sexo } : null };
          ids.push(r.id);
        }
        if (p.tipo === 'CASAL' && ids.length === 2) { estado.analises[ids[0]].par = ids[1]; navegar(`#/resultado/${ids[0]}?par=${ids[1]}`); }
        else if (ids.length > 1) { estado.avisoPendente = `${ids.length} análises executadas. O comparativo por filho está no cartão "Risco por filho".`; navegar(`#/pacientes/${p.id}`); }
        else navegar(`#/resultado/${ids[0]}`);
      } catch (e) { aplicarErros(campos, e.campos, Object.keys(e.campos).length ? null : e.message); if (ids.length) avisar('aviso', `${ids.length} análise(s) concluída(s) antes do erro; veja o histórico na ficha.`, { acumular: true }); }
      finally { enviar.disabled = false; prog.esconder(); form.removeAttribute('aria-busy'); }
    } }, secao1, secao2, secao3, prog.caixa, el('div', { class: 'acoes acoes-direita' }, enviar));
    const apoio = cartaoApoio('Sobre a análise', [p.linha_risco, 'VCFs e laudos vêm da ficha; nada é reenviado. Os arquivos são decifrados só durante a execução.', 'O resumo (genes de risco, probabilidades, idade provável de início e suposições) fica guardado na ficha; o resultado completo fica disponível por duas horas.', 'Resultado: 1. se herdou (transmissão); 2. chance de manifestação com banda de 95 %; 3. idade provável de início. Para uma pessoa com idade informada, os três valem a partir dessa idade, sem sintomas.']);
    area.append(duasColunas(el('div', { class: 'cartao' }, form), apoio));
  }

  // ---------------------------------------------------------------------------------------------
  // Médico: resultado
  // ---------------------------------------------------------------------------------------------
  async function telaResultadoGuardado(area, params) {
    const pid = Number(params[0]), aid = Number(params[1]);
    const [r, p] = await Promise.all([api('GET', `/api/pacientes/${pid}/analises/${aid}`), api('GET', `/api/pacientes/${pid}`)]);
    r.base_url = `/api/pacientes/${pid}/analises/${aid}`;
    estado.nomesPacientes[p.id] = p.nome;
    const d = r.entrada.descendente_id !== null ? p.descendentes.find((x) => x.id === r.entrada.descendente_id) : null;
    const item = { resultado: r, paciente: { id: p.id, nome: p.nome, prontuario: p.prontuario, tipo: p.tipo, tipo_rotulo: p.tipo_rotulo }, descendente: d ? { id: d.id, nome: d.nome, idade: r.entrada.idade_atual !== null ? fmtNum(r.entrada.idade_atual, 0) : d.idade, sexo: d.sexo } : null };
    definirTitulo('Resultado guardado');
    definirTrilha([['Área clínica'], ['Análises', '#/analises'], [p.nome, `#/pacientes/${p.id}`], ['Resultado']]);
    const ent = r.entrada;
    const chips = [chip(p.tipo_rotulo, 'chip-azul'), chip(`Executada em ${fmtData(r.criado_em)}`, 'chip-neutro', 'relogio')];
    if (ent.modo === 'cenario') chips.push(chip(`Cenário de exemplo ${ent.cenario}`, 'chip-aviso', 'frasco'));
    if (ent.suposicoes && ent.suposicoes.nao_portador && ent.suposicoes.nao_portador.length) chips.push(chip('Com suposição de não portador', 'chip-aviso', 'alerta'));
    const pessoa = item.descendente ? `${item.descendente.nome === p.nome ? '' : item.descendente.nome + ' · '}${item.descendente.idade} anos na análise, ${ROTULO_SEXO[item.descendente.sexo]}` : `Futuro filho (${ent.sexo ? ROTULO_SEXO[ent.sexo].toLowerCase() : 'sexo não informado'})`;
    area.append(cabecalhoTela({ titulo: 'Resultado da análise', subtitulo: `${p.nome} · Prontuário ${p.prontuario} · ${pessoa}`, chips, acoes: [botao('Baixar pacote (.zip)', { icone: 'baixar', onclick: () => baixarPacote(r) }), linkBotao('Voltar à ficha', `#/pacientes/${p.id}`, { classe: 'botao-secundario', icone: 'seta-esq' }), linkBotao('Todas as análises', '#/analises', { classe: 'botao-secundario', icone: 'frasco' })] }));
    area.append(corpoResultado(r, item));
  }
  async function telaAnalises(area) {
    definirTitulo('Análises');
    definirTrilha([['Área clínica'], ['Análises']]);
    const dados = await api('GET', '/api/pacientes/analises');
    for (const g of dados.registros) estado.nomesPacientes[g.id] = g.nome;
    const seletor = campo({ nome: 'registro_novo', rotulo: 'Registro a analisar', tipo: 'select', opcoes: [['', 'Selecione o paciente, casal ou família'], ...dados.registros.map((g) => [String(g.id), `${g.nome} · ${g.tipo_curto} · prontuário ${g.prontuario}${g.vcfs_presentes ? '' : ' (sem VCF)'}`])] });
    const nova = el('div', { class: 'cartao', hidden: true }, el('h2', { text: 'Nova análise' }), el('div', { class: 'grade-campos' }, seletor.no), el('div', { class: 'acoes' },
      botao('Continuar', { icone: 'seta-dir', onclick: () => { const id = seletor.valor(); if (!id) { seletor.setErro('Escolha um registro.'); seletor.input.focus(); return; } navegar(`#/analise?paciente=${id}`); } }),
      linkBotao('Análise sem registro', '#/analise', { classe: 'botao-secundario', icone: 'frasco' }), linkBotao('Cadastrar paciente', '#/pacientes/novo', { classe: 'botao-link', icone: 'mais' })));
    area.append(cabecalhoTela({ titulo: 'Análises', subtitulo: 'Todas as análises já executadas nos seus registros, com o resultado completo guardado. Escolha um registro para executar uma nova.', chips: [chip(`${dados.total} análise(s)`, 'chip-azul', 'frasco')], acoes: [botao('Nova análise', { icone: 'mais', onclick: () => { nova.hidden = !nova.hidden; if (!nova.hidden) seletor.input.focus(); } })] }), nova);
    const busca = campo({ nome: 'busca_analises', rotulo: 'Buscar por registro ou pessoa', tipo: 'search', icone: 'lupa', atributos: { autocomplete: 'off' } });
    const genes = Array.from(new Set(dados.analises.flatMap((a) => a.genes_de_risco))).sort();
    const gene = campo({ nome: 'gene_analises', rotulo: 'Gene de risco', tipo: 'select', opcoes: [['', 'Todos'], ...genes.map((g) => [g, g]), ['__sem__', 'Nenhum lócus de risco']] });
    const lista = el('div');
    const render = () => {
      limpar(lista);
      const t = normalizar(busca.valor()), g = gene.valor();
      const itens = dados.analises.filter((a) => (!t || normalizar(`${a.registro} ${a.pessoa} ${a.prontuario}`).includes(t)) && (!g || (g === '__sem__' ? a.sem_locus : a.genes_de_risco.includes(g))));
      if (!itens.length) { lista.append(vazio(dados.total ? 'Nenhuma análise com esses filtros.' : 'Nenhuma análise executada ainda. Clique em "Nova análise".', 'frasco')); return; }
      lista.append(el('div', { class: 'cartao tabela-cartao' }, el('div', { class: 'cabecalho-tabela' }, el('strong', { text: `${itens.length} análise(s)` })), tabela([
        { rotulo: 'Quando', valor: (a) => fmtData(a.executado_em) },
        { rotulo: 'Registro', classe: 'registro', valor: (a) => el('div', {}, el('a', { href: `#/pacientes/${a.paciente_id}`, text: a.registro }), el('div', { class: 'pequeno texto-suave', text: `${a.tipo_curto} · prontuário ${a.prontuario}` })) },
        { rotulo: 'Pessoa', valor: (a) => el('div', {}, a.pessoa, el('div', { class: 'pequeno texto-suave', text: `${a.sexo ? ROTULO_SEXO[a.sexo] : 'sexo não informado'}${a.idade_na_analise !== null ? `, ${a.idade_na_analise} anos` : ''}` })) },
        { rotulo: 'Genes', valor: (a) => el('div', { class: 'chips' }, a.sem_locus ? chip(SEM_LOCUS, 'chip-neutro') : a.genes_de_risco.map((x) => chip(x, 'chip-azul')), chipC9Parcial(a), a.com_suposicao ? chip('suposição', 'chip-aviso') : null, a.hipoteses ? chip('hipóteses', 'chip-neutro') : null) },
        { rotulo: 'Referência', valor: (a) => refAnalise(a) }, { rotulo: 'Herdou', valor: (a) => (a.sem_locus ? '—' : fmtPct(a.p_portador)), num: true }, { rotulo: 'Manifestação [95 %]', valor: (a) => (a.sem_locus ? '—' : `${fmtPct(a.p_manifesta)} [${fmtPct(a.q025)}–${fmtPct(a.q975)}]`), num: true }, { rotulo: 'Início', valor: (a) => (a.sem_locus ? '—' : `${fmtNum(a.idade_mediana, 0)} anos`), num: true },
        { rotulo: 'Execução', valor: (a) => `${a.modo} · ${a.motor} · N=${fmtNum(a.n, 0)}` },
        { rotulo: 'Ações', valor: (a) => el('div', { class: 'acoes acoes-compactas' }, a.tem_resultado ? linkBotao('Abrir resultado', `#/analises/${a.paciente_id}/${a.id}`, { classe: 'botao-pequeno', icone: 'grafico' }) : el('span', { class: 'texto-suave pequeno', text: 'resultado não guardado' }), linkBotao('Repetir', `#/analise?paciente=${a.paciente_id}${a.descendente_id !== null ? `&descendente=${a.descendente_id}` : ''}`, { classe: 'botao-secundario botao-pequeno', icone: 'frasco' })) }], itens, { blocos: true })));
    };
    const filtros = el('div', { class: 'cartao' }, el('div', { class: 'grade-campos' }, busca.no, gene.no));
    busca.input.addEventListener('input', render); gene.input.addEventListener('change', render);
    area.append(filtros, lista);
    render();
  }
  function normalizar(t) { return (t || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, ''); }
  async function obterAnalise(id) {
    let item = estado.analises[id];
    if (!item) { const r = await api('GET', `/api/analises/${id}`); item = estado.analises[id] = { resultado: r, paciente: r.entrada.paciente_id && estado.nomesPacientes[r.entrada.paciente_id] ? { id: r.entrada.paciente_id, nome: estado.nomesPacientes[r.entrada.paciente_id] } : null, descendente: null }; }
    return item;
  }
  async function telaResultado(area, params) {
    const id = params[0];
    const parId = params[1] || null;
    const item = await obterAnalise(id);
    const par = parId ? await obterAnalise(parId) : null;
    definirTitulo('Resultado da análise');
    const pac = item.paciente;
    definirTrilha([['Área clínica'], ['Pacientes', '#/pacientes'], ...(pac ? [['Ficha', `#/pacientes/${pac.id}`]] : []), ['Resultado']]);
    const r = item.resultado;
    const ent = r.entrada;
    const chips = [];
    if (pac && pac.tipo_rotulo) chips.push(chip(pac.tipo_rotulo, 'chip-azul'));
    if (ent.modo === 'cenario') chips.push(chip(`Cenário de exemplo ${ent.cenario}`, 'chip-aviso', 'frasco'));
    if (ent.suposicoes && ent.suposicoes.nao_portador && ent.suposicoes.nao_portador.length) chips.push(chip('Com suposição de não portador', 'chip-aviso', 'alerta'));
    const pessoa = item.descendente ? `${item.descendente.nome === pac?.nome ? '' : item.descendente.nome + ' · '}${item.descendente.idade} anos na análise, ${ROTULO_SEXO[item.descendente.sexo]}` : ent.tipo === 'CASAL' ? `Futuro filho (${ent.sexo ? ROTULO_SEXO[ent.sexo].toLowerCase() : 'sexo não informado'})` : (ent.sexo || ent.idade_atual !== null ? `Descendente: ${ent.sexo ? ROTULO_SEXO[ent.sexo] : 'sexo não informado'}${ent.idade_atual !== null ? `, ${fmtNum(ent.idade_atual, 0)} anos` : ''}` : 'Análise avulsa');
    const subt = [pac ? pac.nome : null, pac && pac.prontuario ? `Prontuário ${pac.prontuario}` : null, pessoa].filter(Boolean).join(' · ');
    area.append(cabecalhoTela({ titulo: 'Resultado da análise', subtitulo: subt, chips, acoes: [botao('Baixar pacote (.zip)', { icone: 'baixar', onclick: () => baixarPacote(r) }), pac ? linkBotao('Voltar à ficha', `#/pacientes/${pac.id}`, { classe: 'botao-secundario', icone: 'seta-esq' }) : linkBotao('Nova análise', '#/analise', { classe: 'botao-secundario', icone: 'frasco' })] }));
    const corpo = el('div');
    area.append(corpo);
    if (par) {
      const alternador = abas([
        { rotulo: `Filha (sexo feminino)`, icone: 'pessoa', conteudo: () => corpoResultado(r, item) },
        { rotulo: `Filho (sexo masculino)`, icone: 'pessoa', conteudo: () => corpoResultado(par.resultado, par) },
      ], 'sexo', { rotulo: 'Resultado por sexo do futuro filho', classe: 'abas-sexo' });
      corpo.append(el('p', { class: 'dica-linha' }, icone('info'), el('span', { text: 'Sexo do futuro filho não informado: as três respostas foram calculadas para os dois sexos (o sexo só altera a idade de início do C9orf72).' })), alternador);
    } else corpo.append(corpoResultado(r, item));
  }
  function faixaSuposicao(r) {
    const s = r.entrada.suposicoes || {};
    if (!s.nao_portador || !s.nao_portador.length) return null;
    const quem = s.nao_portador.map((g) => (g === 'MAE' ? 'mãe/parceira' : 'pai/parceiro')).join(' e ');
    return el('div', { class: 'alerta alerta-aviso' }, icone('alerta'), el('p', {}, el('strong', { text: `Suposição: ${quem} sem exame, assumido(a) sem variante de risco. ` }), r.suposicoes_texto.nao_portador, s.laudo_sem_vcf && s.laudo_sem_vcf.length ? ` ${r.suposicoes_texto.laudo_sem_vcf}` : '', s.laudo_normal_suposto && s.laudo_normal_suposto.length ? ` ${r.suposicoes_texto.laudo_normal_suposto || ''}` : ''));
  }
  function corpoResultado(r, item) {
    const raiz = el('div');
    const ent = r.entrada;
    const sup = faixaSuposicao(r);
    if (sup) raiz.append(sup);
    if (ent.parametros_alternativos || ent.tabela_alternativa) raiz.append(el('div', { class: 'alerta alerta-aviso' }, icone('alerta'), el('p', {}, el('strong', { text: 'Execução com arquivos alternativos. ' }), `Esta análise usou ${[ent.parametros_alternativos ? 'um YAML de parâmetros enviado' : null, ent.tabela_alternativa ? 'uma tabela de variantes enviada' : null].filter(Boolean).join(' e ')} no lugar dos arquivos do artefato. Os números não são os do artefato com os parâmetros da literatura.`)));
    if (r.c9orf72_indeterminado) raiz.append(el('div', { class: 'alerta alerta-aviso' }, icone('alerta'), el('p', {}, el('strong', { text: 'Resultado parcial: o C9orf72 não foi avaliado. ' }), r.texto_c9orf72_indeterminado || 'Falta o nº de repetições do C9orf72 de um genitor; o lócus ficou indeterminado e saiu do cálculo.', r.sem_locus ? ' Os valores abaixo não incluem o C9orf72: 0 % aqui não quer dizer ausência de risco.' : '')));
    const inf = r.parentes && r.parentes.loci_inferidos && r.parentes.loci_inferidos.length ? r.parentes : null;
    if (inf) { // genitor sem exame inferido por parentes: o que entrou e as suposições usadas
      const quem = (inf.pessoas || []).map((x) => x.parente).join(', ');
      const gens = Object.entries(inf.genitores || {}).map(([lado, g]) => `${lado === 'mae' ? 'mãe/parceira' : 'pai/parceiro'}: ${ROTULO_SITUACAO_GENITOR[g.situacao] || g.situacao}${g.idade !== null && g.idade !== undefined && (g.situacao === 'vivo_assintomatico' || g.situacao === 'falecido_sem_ela') ? ` aos ${fmtNum(g.idade, 0)} anos` : ''}`).join('; ');
      raiz.append(el('div', { class: 'alerta alerta-info' }, icone('info'), el('div', {}, el('p', {}, el('strong', { text: 'Genitor sem exame inferido por parentes. ' }), r.texto_inferencia || ''), el('p', { class: 'pequeno', text: `Parentes considerados: ${quem || '—'}. Situação clínica: ${gens || '—'}.` }),
        (inf.suposicoes || []).length ? el('details', {}, el('summary', { text: 'Suposições usadas' }), el('ul', {}, inf.suposicoes.map((s) => el('li', { text: s })))) : null)));
      if (r.limite_inferior) raiz.append(el('div', { class: 'alerta alerta-aviso' }, icone('alerta'), el('p', {}, el('strong', { text: 'Limite inferior. ' }), r.texto_limite_inferior || '')));
      if (r.aviso_parceiro_inferido) raiz.append(el('div', { class: 'alerta alerta-aviso' }, icone('alerta'), el('p', { text: r.aviso_parceiro_inferido })));
    }
    const pr = r.principais || {};
    const base = r.base_url || `/api/analises/${r.id}`;
    const fig = (nome, legenda) => el('figure', { class: 'figura' }, el('a', { href: `${base}/figuras/${nome}`, target: '_blank', rel: 'noopener', title: 'Abrir a figura em tamanho real' }, el('img', { src: `${base}/figuras/${nome}`, alt: legenda })), el('figcaption', { text: legenda }));
    const figuraPorNome = (prefixo) => { const f = r.figuras.find((x) => x.nome.startsWith(prefixo)); return f ? fig(f.nome, f.legenda) : null; };
    const tab = (nome) => { const t = r.tabelas.find((x) => x.nome === nome); return t ? tabelaRegistros(t, true) : null; };
    const secao = (titulo) => { const s = r.secoes.find((x) => x.titulo.startsWith(titulo)); return s ? el('div', { class: 'cartao' }, el('h2', { text: tituloClinico(s.titulo) }), s.texto.split('\n').map((l) => el('p', { text: localizarNumeros(semCitacaoTCC(l).replace(/\*\*/g, '').replace(/^- /, '• ')) }))) : null; };
    const unidades = Object.keys(r.curvas || {});
    const comb = r.curvas && (r.curvas['qualquer lócus'] || r.curvas[unidades[0]]);
    const transmissaoRotulo = ent.tipo === 'CASAL' ? '1. Probabilidade de transmissão' : '1. Probabilidade de ter herdado';
    const ini = pr.inicio || {};
    const cond = !!pr.condicionado;
    const refTxt = cond ? `A partir dos ${fmtNum(pr.idade_referencia, 0)} anos, sem sintomas` : '';
    const horizonteTxt = fmtNum(pr.horizonte || (r.metadados && r.metadados.horizonte) || 90, 0);
    const jan = pr.janelas || {};
    const indicadores = el('div', { class: 'indicadores' },
      indicador({ icone: 'transmissao', rotulo: transmissaoRotulo, valor: r.sem_locus ? '—' : fmtPct(pr.transmissao), detalhe: r.sem_locus ? 'Nenhum lócus de risco encontrado' : (cond ? `${refTxt}: portar ao menos uma variante de risco` : 'Herdar ao menos uma variante de risco (P portador ≥ 1)'), destaque: true }),
      indicador({ icone: 'escudo', rotulo: cond ? '2. Manifestação daqui em diante' : '2. Manifestação ao longo da vida', valor: r.sem_locus ? '—' : fmtPct(pr.vida ? pr.vida.valor : null), detalhe: r.sem_locus ? 'Nenhum lócus de risco encontrado' : (pr.vida ? `${cond ? `${refTxt}, até os ${horizonteTxt} anos` : `Até os ${horizonteTxt} anos`}. Intervalo de 95 %: ${fmtPct(pr.vida.q025)}–${fmtPct(pr.vida.q975)}` : ''), destaque: true }),
      ...(cond
        ? ['10', '20'].map((j) => indicador({ icone: 'pessoa', rotulo: `Nos próximos ${j} anos`, valor: r.sem_locus ? '—' : fmtPct(jan[j] ? jan[j].valor : null), detalhe: r.sem_locus ? 'Nenhum lócus de risco encontrado' : (jan[j] ? `${refTxt}. Intervalo de 95 %: ${fmtPct(jan[j].q025)}–${fmtPct(jan[j].q975)}` : refTxt) }))
        : ['50', '60', '70'].map((a) => indicador({ icone: 'pessoa', rotulo: `Aos ${a} anos`, valor: r.sem_locus ? '—' : fmtPct(pr.F && pr.F[a] ? pr.F[a].valor : null), detalhe: r.sem_locus ? 'Nenhum lócus de risco encontrado' : (pr.F && pr.F[a] ? `Intervalo de 95 %: ${fmtPct(pr.F[a].q025)}–${fmtPct(pr.F[a].q975)}` : '') }))),
      indicador({ icone: 'calendario', rotulo: '3. Idade provável de início', valor: r.sem_locus || ini.mediana === null || ini.mediana === undefined ? '—' : `${fmtNum(ini.mediana, 0)} anos`, detalhe: r.sem_locus ? 'Nenhum lócus de risco encontrado' : (ini.mediana === null || ini.mediana === undefined ? `${cond ? `${refTxt}: ` : ''}sem risco restante até o horizonte` : `${cond ? `${refTxt}, entre quem vai manifestar: mediana` : 'Mediana'}; faixa de 25–75 %: ${fmtNum(ini.q25, 0)}–${fmtNum(ini.q75, 0)} anos`), destaque: true }));
    const limitacoes = el('div', { class: 'cartao' }, el('h2', { text: 'Limitações do modelo' }), el('div', { class: 'linhas-info' },
      dica('Não considera ancestralidade.'), dica('Usa só genótipos: dos genitores e, quando um deles não pôde ser testado, de parentes dele. O fenótipo de parente sem teste genético não entra.'), dica('Vale para pessoa sem sintomas; não calcula números agregados da família.'), dica('Assume independência entre os genes.'),
      ...(r.limitacoes.parametros_provisorios.length ? [dica(`Parâmetros provisórios (a confirmar na literatura): ${r.limitacoes.parametros_provisorios.join(', ')}.`)] : [])), el('p', { class: 'pequeno texto-suave', text: r.limitacoes.texto }));
    const barra = el('div', { class: 'barra-inferior' },
      el('span', { class: 'item' }, icone('frasco'), `Entrada: ${ent.modo === 'cenario' ? `cenário ${ent.cenario}` : 'VCFs'}; laudo C9orf72: ${ent.laudo_c9orf72 ? Object.entries(ent.laudo_c9orf72).map(([k, v]) => `${k} ${Array.isArray(v) ? v.join(',') : v}`).join('; ') : 'não informado'}`),
      el('span', { class: 'item' }, icone('modelo'), `N = ${fmtNum(ent.n, 0)} · semente ${ent.semente} · motor ${ent.motor}${ent.hipoteses_c9orf72 ? ' · hipóteses experimentais' : ''}${ent.comparar_cox ? ' · Cox' : ''}${ent.tornado ? ' · tornado' : ''}${ent.horizonte ? ` · horizonte ${fmtNum(ent.horizonte, 0)} anos` : ''}${ent.base ? ` · base: ${ent.base}` : ''}`),
      ent.assintomatico_confirmado ? el('span', { class: 'item' }, icone('check'), `Sem sintomas: confirmado pelo profissional${ent.assintomatico_confirmado_em ? ` em ${fmtData(ent.assintomatico_confirmado_em)}` : ''}`) : null,
      el('button', { type: 'button', class: 'botao botao-link', onclick: () => raizAbas.selecionar(5) }, 'Ver metadados e verificações ', icone('seta-dir')));
    const resumoAba = () => {
      const d = el('div', {}, indicadores);
      if (r.sem_locus) {
        d.append(el('div', { class: 'cartao' }, el('h2', { text: r.c9orf72_indeterminado ? 'Nenhum lócus de risco nos genes avaliados (C9orf72 não avaliado)' : 'Nenhum lócus de risco encontrado' }), r.secoes.filter((s) => s.titulo === 'Resultado').map((s) => el('p', { text: localizarNumeros(s.texto) })), secao('Qualidade dos dados'), r.tabelas.map((t) => tabelaRegistros(t, true))), limitacoes, barra);
        return d;
      }
      const tabelaF = tabelaAlternativa('probabilidade acumulada por idade, banda de 95 % e S(t)', comb.t, [{ rotulo: 'F(t)', y: comb.F }, { rotulo: 'F 2,5 %', y: comb.F_q025 }, { rotulo: 'F 97,5 %', y: comb.F_q975 }, { rotulo: 'S(t)', y: comb.S }]);
      const grafico = graficoLinhas({ titulo: 'Probabilidade acumulada por idade', descricao: 'Gráfico de linhas da probabilidade acumulada de manifestação F(t) por idade, com banda de credibilidade de 95 %; os dados estão na tabela abaixo.', x: comb.t, series: [{ nome: 'Estimativa', y: comb.F, classe: 'curva' }], banda: { inferior: comb.F_q025, superior: comb.F_q975, nome: 'Intervalo de 95 %' }, tabela: tabelaF });
      d.append(el('div', { class: 'duas-colunas' }, el('div', {}, grafico, cond ? el('p', { class: 'pequeno texto-suave', text: `A curva mostra o risco acumulado desde o nascimento. Os indicadores acima valem a partir dos ${fmtNum(pr.idade_referencia, 0)} anos, sem sintomas; a aba "Risco por idade" traz a tabela completa.` }) : null), el('div', {}, limitacoes)));
      d.append(el('h2', { text: 'Por lócus de risco' }), el('div', { class: 'grade' }, r.resumo.map((l) => el('div', { class: 'cartao' }, el('h3', { text: l.variante }), el('p', { class: 'pequeno texto-suave', text: `${l.heranca}; dosagens mãe/pai ${rotuloDosagem(l.dosagem_mae, inf)}/${rotuloDosagem(l.dosagem_pai, inf)}` }),
        el('div', { class: 'grade' }, medida(fmtPct(l.p_portador_exato), 'herdou'), medida(fmtPct(l.p_manifesta_exato), `risco vitalício, desde o nascimento [${fmtPct(l.p_manifesta_q025)}–${fmtPct(l.p_manifesta_q975)}]`), medida(`${fmtNum(l.idade_mediana_exata, 1)} anos`, 'idade mediana de início'))))),
        el('div', {}, secao('Resultado'), tab('tabela_03_risco_vitalicio'), r.transmissao_c9orf72 ? secao('Transmissão do C9orf72') : null), barra);
      return d;
    };
    const raizAbas = abas([
      { rotulo: 'Resumo', icone: 'grafico', conteudo: resumoAba },
      { rotulo: 'Variantes e qualidade', icone: 'dna', conteudo: () => el('div', {}, secao('Qualidade dos dados'), tab('tabela_01_variantes_anotadas'), tab('tabela_01b_vetor_dosagem'), secao('Genitor inferido por parentes'), tab('tabela_01d_genitor_inferido'), tab('tabela_01c_transmissao_c9orf72')) },
      { rotulo: 'Risco por idade', icone: 'calendario', conteudo: () => el('div', {}, el('p', { text: 'Risco condicional ao descendente assintomático em cada idade atual: P(portador | assintomático), risco nos próximos 10 e 20 anos e risco residual (da idade atual até o horizonte), com banda de 95 % pela incerteza da penetrância. Na idade 0 o risco residual é o risco vitalício.' }), tab('tabela_04_risco_condicional'), tab('tabela_04b_risco_condicional_km')) },
      { rotulo: 'Curvas', icone: 'grafico', conteudo: () => r.sem_locus ? el('p', { text: 'Sem lócus de risco: não há curvas.' }) : el('div', {}, unidades.map((u) => { const c = r.curvas[u]; const t = tabelaAlternativa(`${u}, F(t), banda e S(t)`, c.t, [{ rotulo: 'F(t)', y: c.F }, { rotulo: 'F 2,5 %', y: c.F_q025 }, { rotulo: 'F 97,5 %', y: c.F_q975 }, { rotulo: 'S(t)', y: c.S }]);
          return graficoLinhas({ titulo: `${u}: F(t) com banda de 95 % e S(t)`, descricao: `Gráfico de linhas de ${u}: risco acumulado F(t) com banda de credibilidade de 95 % e sobrevivência S(t) por idade; os dados estão na tabela.`, x: c.t, yMax: 1, series: [{ nome: 'F(t) = P(C)·π·G(t)', y: c.F, classe: 'curva' }, { nome: 'S(t) = 1 − F(t)', y: c.S, classe: 'curva-2' }], banda: { inferior: c.F_q025, superior: c.F_q975, nome: 'banda 95 % (incerteza de π)' }, tabela: t }); }),
        graficoLinhas({ titulo: 'Risco instantâneo h(t) por unidade', descricao: 'Gráfico de linhas do risco instantâneo h(t) por ano para cada unidade; os dados estão na tabela.', x: r.curvas[unidades[0]].t, formatoY: (v) => fmtNum(v, 3), livre: true, series: unidades.map((u, i) => ({ nome: u, y: r.curvas[u].h, classe: ['curva', 'curva-2', 'curva-3'][i % 3] })), tabela: tabelaAlternativa('h(t) por unidade', r.curvas[unidades[0]].t, unidades.map((u) => ({ rotulo: `h(t) ${u}`, y: r.curvas[u].h, formato: (v) => fmtNum(v, 4) }))) }),
        figuraPorNome('figura_04'), figuraPorNome('figura_08'), figuraPorNome('figura_05')) },
      { rotulo: 'Sobrevivência', icone: 'degraus', conteudo: () => el('div', {}, el('p', { text: 'Coorte sintética censurada no horizonte: Kaplan-Meier (Lifelines), recuperação de π, λ e ρ pelo modelo de cura mista e, se pedido, o modelo de Cox como comparação.' }), tab('tabela_10_kaplan_meier'), tab('tabela_07_recuperacao_lifelines'), cartaoCox(r), figuraPorNome('figura_09')) },
      { rotulo: 'Verificações', icone: 'escudo', conteudo: () => el('div', {}, secao('Verificações'), tab('tabela_02_aderencia'), figuraPorNome('figura_06'), figuraPorNome('figura_01'),
        r.tornado ? [secao('Sensibilidade tipo tornado'), tab('tabela_20_tornado'), figuraPorNome('figura_12')] : (r.sem_locus ? null : el('p', { class: 'pequeno texto-suave', text: 'Sensibilidade tipo tornado não solicitada nesta execução (opção da análise, desligada por padrão).' })),
        el('div', { class: 'cartao' }, el('h2', { text: 'Metadados da execução (reprodutibilidade)' }), el('dl', { class: 'lista-definicao' }, Object.entries(r.metadados).filter(([, v]) => v !== null && typeof v !== 'object').map(([k, v]) => [el('dt', { text: k }), el('dd', { text: fmtCelula(v) })]).flat(),
          el('dt', { text: 'base de anotação' }), el('dd', { text: r.metadados.base_anotacao ? (r.metadados.base_anotacao.base_real || 'tabela curada') : '—' }), el('dt', { text: 'lóci descartados' }), el('dd', { text: (r.metadados.loci_descartados || []).join(', ') || 'nenhum' }),
          el('dt', { text: 'suposições' }), el('dd', { text: ent.suposicoes && ent.suposicoes.nao_portador ? `genitor assumido não portador: ${ent.suposicoes.nao_portador.join(', ')}` : 'nenhuma' }),
          ent.vcf_hash ? [el('dt', { text: 'VCFs (hash curto)' }), el('dd', { text: `mãe ${ent.vcf_hash.mae || '—'}; pai ${ent.vcf_hash.pai || '—'}` })] : null)),
        el('details', {}, el('summary', { text: 'Relatório completo (Markdown)' }), el('pre', { text: r.relatorio_md }))) },
    ], `res-${r.id.slice(0, 6)}`);
    raiz.append(raizAbas);
    void item;
    return raiz;
  }
  function rotuloDosagem(v, inferida) { // dosagem de um genitor num lócus; sem valor quando ele não foi testado
    if (v !== null && v !== undefined) return String(v);
    return inferida ? 'inferida por parentes' : 'não determinada';
  }
  function medida(valor, rotulo) { return el('div', { class: 'medida' }, el('span', { class: 'valor', text: valor }), el('span', { class: 'rotulo', text: rotulo })); }
  function cartaoCox(r) {
    const cartao = el('div', { class: 'cartao' }, el('h2', { text: 'Cox e cura mista' }));
    if (!r.cox) { cartao.append(el('p', { text: 'Comparação com o modelo de Cox não solicitada nesta execução.' })); return cartao; }
    for (const l of r.cox.tabela) {
      const g = el('div', {}, el('h3', { text: l.unidade }));
      if (l.cox !== 'ajustado') { g.append(el('p', { text: l.cox })); cartao.append(g); continue; }
      const hrs = Object.keys(l).filter((k) => k.startsWith('HR[') && l[k] !== null && l[k] !== undefined).map((k) => { const nome = k.slice(3, -1); return `HR ${nome} = ${fmtNum(l[k], 2)} [${l[`IC95 HR[${nome}]`] || '—'}], p = ${fmtNum(l[`p[${nome}]`], 3)}; riscos proporcionais p = ${fmtNum(l[`p_riscos_proporcionais[${nome}]`], 3)}`; });
      g.append(el('div', { class: 'grade' }, medida(fmtNum(l.concordancia, 3), 'índice de concordância'), medida(fmtNum(l['S_cox(horizonte)'], 3), 'S_Cox no horizonte'), medida(fmtNum(l.fracao_cura_lifelines, 3), 'fração de cura 1 − π̂ (Lifelines)'), medida(fmtNum(l.dif_max_cox_cura_mista, 3), 'maior diferença Cox × cura mista')),
        el('ul', {}, hrs.map((h) => el('li', { text: h }))),
        tabela([{ rotulo: 'Idade', chave: 'idade' }, { rotulo: 'S Cox', valor: (x) => fmtNum(x.cox, 3), num: true }, { rotulo: 'S cura mista', valor: (x) => fmtNum(x.cura, 3), num: true }, { rotulo: 'S Kaplan-Meier', valor: (x) => fmtNum(x.km, 3), num: true }, { rotulo: 'S analítico', valor: (x) => fmtNum(x.an, 3), num: true }],
          [50, 60, 70].map((a) => ({ idade: `${a} anos`, cox: l[`S_cox(${a})`], cura: l[`S_cura_mista(${a})`], km: l[`S_km(${a})`], an: l[`S_analitico(${a})`] })), { legenda: 'Sobrevivência entre portadores por método' }));
      cartao.append(g);
    }
    cartao.append(el('p', { class: 'pequeno', text: localizarNumeros(r.cox.texto.replace(/\*\*/g, '')) }));
    return cartao;
  }
  async function baixarPacote(r) {
    try {
      const base = r.base_url || `/api/analises/${r.id}`;
      const resp = await api('GET', `${base}/pacote.zip`, { bruto: true });
      if (!resp.ok) { avisar('erro', resp.status === 404 ? 'Pacote não disponível (análise expirada).' : 'Não foi possível baixar o pacote.'); return; }
      baixarBlob(await resp.blob(), `analise_${String(r.id).slice(0, 8)}.zip`);
      avisar('sucesso', 'Pacote gerado (relatório, tabelas, figuras, curvas e metadados; sem os VCFs).');
    } catch (e) { avisar('erro', e.message); }
  }

  // ---------------------------------------------------------------------------------------------
  // Pesquisador: casos pseudonimizados e modelo
  // ---------------------------------------------------------------------------------------------
  function analisePseudo(a) {
    if (!a) return el('span', { class: 'texto-suave', text: 'Sem análise' });
    const ini = a.inicio || {};
    return el('div', {}, el('div', { class: 'chips' }, a.sem_locus ? chip('Nenhum lócus de risco encontrado', 'chip-neutro') : a.genes_de_risco.map((g) => chip(g, 'chip-azul')), chipC9Parcial(a)),
      el('div', { class: 'pequeno', text: a.sem_locus ? 'Sem probabilidade a informar: a análise não encontrou lócus de risco.' : `herdou ${fmtPct(a.p_portador)} · ${a.condicionado ? 'daqui em diante' : 'risco vitalício'} ${fmtPct(a.p_manifesta)} [${fmtPct(a.q025)}–${fmtPct(a.q975)}] · início ${a.idade_mediana === null || a.idade_mediana === undefined ? '—' : `${fmtNum(a.idade_mediana, 0)} anos`}` }), el('div', { class: 'pequeno texto-suave', text: `Valores ${refAnalise(a)}` }),
      el('div', { class: 'pequeno texto-suave', text: `${fmtMes(a.executado_em)} · ${a.motor} · N=${fmtNum(a.n, 0)}${a.hipoteses ? ' · hipóteses' : ''}${a.com_suposicao ? ' · suposição' : ''}` }), void ini);
  }
  function cartaoCaso(c) {
    const cab = el('div', { class: 'cabecalho-tabela' }, el('div', {}, el('div', { class: 'chips' }, el('code', { text: c.codigo.slice(0, 12) + '…', title: 'código pseudonimizado' }), chip(c.tipo_rotulo, 'chip-azul', c.tipo === 'CASAL' ? 'casal' : c.tipo === 'FAMILIA' ? 'familia' : 'pessoa'), c.momento_rotulo ? chip(c.momento_rotulo, 'chip-neutro') : null, chip(`liberado em ${fmtMes(c.liberado_em)}`, 'chip-neutro'), c.com_suposicao ? chip('suposição de não portador', 'chip-aviso', 'alerta') : null)),
      el('div', { class: 'chips' }, PAPEIS_GENITOR.map((g) => chip(`${g === 'MAE' ? 'mãe' : 'pai'}: ${c.genitores[g] && c.genitores[g].vcf_presente ? 'VCF' : 'sem VCF'}${c.genitores[g] && c.genitores[g].laudo_informado ? ' + laudo' : ''}${c.genitores[g] && (c.genitores[g].parentes || []).length ? ` · inferido por ${c.genitores[g].parentes.length} parente(s)` : ''}`, c.genitores[g] && c.genitores[g].vcf_presente ? 'chip-ok' : 'chip-aviso'))));
    const pessoas = el('div', { class: 'grade' }, c.descendentes.map((d) => el('div', { class: 'medida' }, el('strong', { text: `Descendente ${d.indice}: ${ROTULO_SEXO[d.sexo]}, ${d.faixa_etaria} anos` }), analisePseudo(d.analise))),
      c.futuro_filho ? el('div', { class: 'medida' }, el('strong', { text: `Futuro filho${c.futuro_filho.sexo ? ` (${ROTULO_SEXO[c.futuro_filho.sexo]})` : ''}` }), analisePseudo(c.futuro_filho)) : null);
    const det = el('details', { class: 'detalhes-caso' }, el('summary', { text: 'Dados completos: variantes, dosagens, curva de risco e metadados' }));
    det.addEventListener('toggle', async () => {
      if (!det.open || det.dataset.carregado) return;
      det.dataset.carregado = '1';
      const corpo = el('div', {}, el('div', { class: 'ocupado', role: 'status', text: 'Carregando o registro…' }));
      det.append(corpo);
      try { const full = await api('GET', `/api/pesquisa/casos/${c.codigo}`); limpar(corpo).append(detalheCaso(full)); }
      catch (e) { limpar(corpo).append(el('p', { class: 'texto-suave', text: e.message })); }
    });
    return el('div', { class: 'cartao tabela-cartao caso-cartao' }, cab, el('div', { class: 'cartao-interno' }, pessoas, det));
  }
  function detalheCaso(c) {
    const raiz = el('div', { class: 'detalhe-caso' });
    raiz.append(el('h3', { text: 'Genitores' }), el('div', { class: 'grade' }, PAPEIS_GENITOR.map((g) => el('div', { class: 'medida' }, el('strong', { text: g === 'MAE' ? 'Mãe / parceira' : 'Pai / parceiro' }), el('div', { class: 'pequeno', text: `${c.genitores[g] && c.genitores[g].vcf_presente ? 'VCF analisado' : 'sem VCF'}${c.genitores[g] && c.genitores[g].laudo_informado ? ' · laudo do C9orf72 informado' : ''}` })))));
    const pessoas = [...c.descendentes.map((d) => ({ rotulo: `Descendente ${d.indice} (${ROTULO_SEXO[d.sexo]}, ${d.faixa_etaria} anos)`, a: d.analise })), ...(c.futuro_filho ? [{ rotulo: `Futuro filho${c.futuro_filho.sexo ? ` (${ROTULO_SEXO[c.futuro_filho.sexo]})` : ''}`, a: c.futuro_filho }] : [])];
    for (const { rotulo, a } of pessoas) {
      raiz.append(el('h3', { text: rotulo }));
      if (!a) { raiz.append(el('p', { class: 'texto-suave', text: 'Sem análise.' })); continue; }
      const ini = a.inicio || {};
      raiz.append(el('p', { class: 'pequeno texto-suave', text: `Os três valores abaixo valem ${refAnalise(a)}.` }));
      raiz.append(a.sem_locus ? el('div', { class: 'grade' }, medida('—', 'Nenhum lócus de risco encontrado: não há probabilidade a informar')) : el('div', { class: 'grade' }, medida(fmtPct(a.p_portador), '1. herdou / transmissão'), medida(`${fmtPct(a.p_manifesta)} [${fmtPct(a.q025)}–${fmtPct(a.q975)}]`, a.condicionado ? '2. manifestação daqui em diante, até o horizonte' : '2. risco vitalício: manifestação até o horizonte'), a.condicionado ? medida(fmtPct(a.risco_vitalicio), 'risco vitalício, desde o nascimento') : null, medida(a.sem_locus ? '—' : `${fmtNum(a.idade_mediana, 0)} anos (25–75 %: ${fmtNum(ini.q25, 0)}–${fmtNum(ini.q75, 0)})`, '3. idade provável de início')));
      if (a.loci && a.loci.length) raiz.append(tabela([{ rotulo: 'Gene', chave: 'gene' }, { rotulo: 'Variante', chave: 'variante' }, { rotulo: 'Herança', chave: 'heranca' }, { rotulo: 'Dosagem mãe', chave: 'dosagem_mae', num: true }, { rotulo: 'Dosagem pai', chave: 'dosagem_pai', num: true }, { rotulo: 'P(portador)', valor: (l) => fmtPct(l.p_portador), num: true }, { rotulo: 'Risco vitalício, desde o nascimento [95 %]', valor: (l) => `${fmtPct(l.p_manifesta)} [${fmtPct(l.q025)}–${fmtPct(l.q975)}]`, num: true }, ...(a.condicionado ? [{ rotulo: 'Risco residual, a partir da idade de referência [95 %]', valor: (l) => (l.risco_residual === null || l.risco_residual === undefined ? '—' : `${fmtPct(l.risco_residual)} [${fmtPct(l.risco_residual_q025)}–${fmtPct(l.risco_residual_q975)}]`), num: true }] : []), { rotulo: 'Idade mediana', valor: (l) => fmtNum(l.idade_mediana, 1), num: true }], a.loci, { legenda: 'Lóci de risco' }));
      if (a.vetor && a.vetor.length) raiz.append(tabela([{ rotulo: 'Gene', chave: 'gene' }, { rotulo: 'Variante', chave: 'variante' }, { rotulo: 'rs', chave: 'rs' }, { rotulo: 'Tipo', chave: 'tipo' }, { rotulo: 'Herança', chave: 'heranca' }, { rotulo: 'Dosagem mãe', chave: 'dosagem_mae', num: true }, { rotulo: 'Dosagem pai', chave: 'dosagem_pai', num: true }, { rotulo: 'Repetições mãe/pai', valor: (l) => `${fmtCelula(l.repeticoes_mae)} / ${fmtCelula(l.repeticoes_pai)}` }, { rotulo: 'ClinVar', chave: 'clnsig' }, { rotulo: 'Estrelas', chave: 'estrelas', num: true }, { rotulo: 'Descartado', chave: 'descartado' }], a.vetor, { legenda: 'Vetor genotípico parental (dosagem por lócus de risco)' }));
      if (a.variantes && a.variantes.length) raiz.append(tabela([{ rotulo: 'Genitor', valor: (v) => (v.amostra === 'MAE' ? 'mãe' : v.amostra === 'PAI' ? 'pai' : v.amostra) }, { rotulo: 'Gene', chave: 'gene' }, { rotulo: 'Crom.', chave: 'cromossomo' }, { rotulo: 'Posição', chave: 'posicao', num: true }, { rotulo: 'Ref', chave: 'ref' }, { rotulo: 'Alt', chave: 'alt' }, { rotulo: 'ID', chave: 'id' }, { rotulo: 'Tipo', chave: 'tipo' }, { rotulo: 'Classe', chave: 'classe' }, { rotulo: 'ClinVar', chave: 'clnsig' }, { rotulo: 'Estrelas', chave: 'estrelas', num: true }, { rotulo: 'Nome curto', chave: 'nome_curto' }, { rotulo: 'Dosagem', chave: 'dosagem', num: true }, { rotulo: 'Repetições', chave: 'repeticoes', num: true }], a.variantes, { legenda: 'Variantes aprovadas no filtro de qualidade, por genitor (dos VCFs)' }));
      if (a.curva) raiz.append(graficoLinhas({ titulo: 'Probabilidade acumulada por idade (unidade combinada)', descricao: 'Gráfico de linhas de F(t) com banda de 95 %; os dados estão na tabela.', x: a.curva.t, series: [{ nome: 'F(t)', y: a.curva.F, classe: 'curva' }, { nome: 'S(t)', y: a.curva.S, classe: 'curva-2' }], banda: { inferior: a.curva.F_q025, superior: a.curva.F_q975, nome: 'Intervalo de 95 %' }, tabela: tabelaAlternativa('F(t), banda e S(t)', a.curva.t, [{ rotulo: 'F(t)', y: a.curva.F }, { rotulo: 'F 2,5 %', y: a.curva.F_q025 }, { rotulo: 'F 97,5 %', y: a.curva.F_q975 }, { rotulo: 'S(t)', y: a.curva.S }]) }));
      raiz.append(el('p', { class: 'pequeno texto-suave', text: `Análise de ${fmtMes(a.executado_em)} · ${a.modo} · motor ${a.motor} · N = ${fmtNum(a.n, 0)} · semente ${a.semente === undefined ? '—' : a.semente}${a.hipoteses ? ' · hipóteses experimentais' : ''}${a.suposicoes && a.suposicoes.nao_portador && a.suposicoes.nao_portador.length ? ` · suposição de não portador: ${a.suposicoes.nao_portador.join(', ')}` : ''} · lóci descartados: ${(a.loci_descartados || []).join(', ') || 'nenhum'} · horizonte ${a.horizonte || '—'} anos · versão ${a.versao || '—'}` }));
    }
    return raiz;
  }
  async function telaCasos(area) {
    definirTitulo('Registros de pesquisa');
    definirTrilha([['Área de pesquisa'], ['Registros de pesquisa']]);
    const inicial = await api('GET', '/api/pesquisa/casos');
    const op = inicial.opcoes;
    area.append(cabecalhoTela({ titulo: 'Registros de pesquisa', subtitulo: inicial.descricao }));
    const f = {
      tipo: campo({ nome: 'f_tipo', rotulo: 'Caso', tipo: 'select', opcoes: [['', 'Todos'], ...op.tipos.map((t) => [t.valor, t.rotulo])] }),
      sexo: campo({ nome: 'f_sexo', rotulo: 'Sexo', tipo: 'select', opcoes: [['', 'Qualquer'], ['F', 'Feminino'], ['M', 'Masculino']] }),
      decada: campo({ nome: 'f_decada', rotulo: 'Década de idade', tipo: 'select', opcoes: [['', 'Qualquer'], ...op.decadas.map((d) => [d, d])] }),
      momento: campo({ nome: 'f_momento', rotulo: 'Momento do aconselhamento', tipo: 'select', opcoes: [['', 'Qualquer'], ...op.momentos.map((m) => [m.valor, m.rotulo])] }),
      heranca: campo({ nome: 'f_heranca', rotulo: 'Padrão de herança', tipo: 'select', opcoes: [['', 'Qualquer'], ...op.herancas.map((h) => [h, h])] }),
      risco_min: campo({ nome: 'f_risco_min', rotulo: 'Risco vitalício mínimo (%)', tipo: 'number', dica: 'Desde o nascimento, até o horizonte.', atributos: { min: 0, max: 100 } }),
      risco_max: campo({ nome: 'f_risco_max', rotulo: 'Risco vitalício máximo (%)', tipo: 'number', atributos: { min: 0, max: 100 } }),
      analise_de: campo({ nome: 'f_analise_de', rotulo: 'Análise de (AAAA-MM)', atributos: { placeholder: '2026-01', pattern: '\\d{4}-\\d{2}' } }),
      analise_ate: campo({ nome: 'f_analise_ate', rotulo: 'Análise até (AAAA-MM)', atributos: { placeholder: '2026-12' } }),
      hipoteses: campo({ nome: 'f_hipoteses', rotulo: 'Hipóteses experimentais', tipo: 'select', opcoes: [['', 'Qualquer'], ['true', 'Usadas'], ['false', 'Não usadas']] }),
      suposicao: campo({ nome: 'f_suposicao', rotulo: 'Suposição de não portador', tipo: 'select', opcoes: [['', 'Qualquer'], ['true', 'Com suposição'], ['false', 'Sem suposição']] }),
      com_analise: campo({ nome: 'f_com_analise', rotulo: 'Análise', tipo: 'select', opcoes: [['', 'Qualquer'], ['true', 'Com análise'], ['false', 'Sem análise']] }),
    };
    const genes = op.genes.map((g) => marcacao({ nome: 'f_genes', valor: g, rotulo: g }));
    const bool = (v) => (v === '' ? null : v === 'true');
    const filtros = () => {
      const d = { tipo: f.tipo.valor() || null, sexo: f.sexo.valor() || null, decada: f.decada.valor() || null, momento: f.momento.valor() || null, genes: genes.filter((g) => g.valor()).map((g) => g.input.value), heranca: f.heranca.valor() || null,
        risco_min: f.risco_min.valor() === '' ? null : Number(f.risco_min.valor()) / 100, risco_max: f.risco_max.valor() === '' ? null : Number(f.risco_max.valor()) / 100, analise_de: f.analise_de.valor().trim() || null, analise_ate: f.analise_ate.valor().trim() || null,
        hipoteses: bool(f.hipoteses.valor()), suposicao: bool(f.suposicao.valor()), com_analise: bool(f.com_analise.valor()) };
      for (const k of Object.keys(d)) if (d[k] === null || (Array.isArray(d[k]) && !d[k].length)) delete d[k];
      return d;
    };
    const exportar = async (caminho, nome, texto) => {
      try { const resp = await api('POST', caminho, { json: filtros(), bruto: true }); if (!resp.ok) { avisar('erro', 'Não foi possível exportar.'); return; } baixarBlob(await resp.blob(), nome); avisar('sucesso', `${texto} A exportação fica na auditoria.`); } catch (e) { avisar('erro', e.message); }
    };
    const totaisNo = el('div', { class: 'indicadores' });
    const lista = el('div');
    const form = el('form', { novalidate: true, role: 'search', onsubmit: async (ev) => { ev.preventDefault(); await carregar(); } },
      el('details', { class: 'filtros', open: true }, el('summary', {}, icone('filtro'), ' Filtros'), el('div', { class: 'grade-campos' }, f.tipo.no, f.sexo.no, f.decada.no, f.momento.no, f.heranca.no, f.risco_min.no, f.risco_max.no, f.analise_de.no, f.analise_ate.no, f.hipoteses.no, f.suposicao.no, f.com_analise.no),
        el('fieldset', {}, el('legend', { text: 'Gene de risco' }), el('div', { class: 'genes-opcoes opcoes-linha' }, genes.map((g) => g.no)))),
      el('div', { class: 'acoes' }, botao('Aplicar filtros', { tipo: 'submit', icone: 'lupa' }), botao('Limpar', { classe: 'botao-secundario', onclick: () => { form.reset(); carregar(); } }),
        botao('Exportar resumo (CSV)', { classe: 'botao-secundario', icone: 'baixar', onclick: () => exportar('/api/pesquisa/casos/exportar', 'registros_pesquisa.csv', 'CSV gerado: uma linha por análise, sem dado identificável.') }),
        botao('Exportar variantes (CSV)', { classe: 'botao-secundario', icone: 'dna', onclick: () => exportar('/api/pesquisa/casos/exportar-variantes', 'variantes_pesquisa.csv', 'CSV gerado: uma linha por variante, por genitor e análise.') }),
        botao('Exportar detalhado (JSON)', { classe: 'botao-secundario', icone: 'arquivo', onclick: () => exportar('/api/pesquisa/casos/exportar-detalhado', 'registros_pesquisa.json', 'JSON gerado com lóci, variantes, dosagens, curvas e metadados.') })));
    area.append(el('div', { class: 'cartao' }, form), totaisNo, lista);
    function renderTotais(t) {
      limpar(totaisNo);
      const porGene = Object.entries(t.por_gene).map(([g, n]) => `${g} ${n}`).join(' · ') || '—';
      const porSexo = Object.entries(t.por_sexo).map(([s, n]) => `${s === 'NI' ? 'não informado' : ROTULO_SEXO[s]} ${n}`).join(' · ') || '—';
      totaisNo.append(indicador({ icone: 'pacientes', rotulo: 'Registros no filtro', valor: String(t.casos), detalhe: Object.entries(t.por_tipo).map(([k, n]) => `${(op.tipos.find((x) => x.valor === k) || {}).curto || k}: ${n}`).join(' · ') || '—' }),
        indicador({ icone: 'frasco', rotulo: 'Pessoas analisadas', valor: String(t.analises), detalhe: `por sexo: ${porSexo}` }), indicador({ icone: 'dna', rotulo: 'Genes de risco', valor: String(Object.keys(t.por_gene).length), detalhe: porGene }),
        indicador({ icone: 'escudo', rotulo: 'Risco vitalício mediano', valor: fmtPct(t.risco_vitalicio_mediano), detalhe: `Desde o nascimento, até o horizonte. ${t.com_suposicao} registro(s) com suposição de não portador` }));
    }
    async function carregar(dados) {
      limpar(lista);
      let r = dados;
      if (!r) { try { r = await api('POST', '/api/pesquisa/casos/busca', { json: filtros() }); } catch (e) { aplicarErros({}, {}, `${e.message} ${Object.entries(e.campos || {}).map(([k, v]) => `${k}: ${v}`).join(' ')}`); return; } }
      renderTotais(r.totais);
      if (!r.casos.length) { lista.append(vazio(r.mensagem || 'Nenhum registro com esses filtros.', 'microscopio')); return; }
      lista.append(el('p', { class: 'texto-suave', text: `${r.casos.length} registro(s). Expanda um registro para ver as variantes, as dosagens, a curva de risco e os metadados.` }), ...r.casos.map(cartaoCaso));
    }
    await carregar(inicial);
  }
  async function telaModelo(area) {
    definirTitulo('Modelo e parâmetros');
    definirTrilha([[areaDoPapel()], ['Modelo e parâmetros']]);
    const p = await api('GET', '/api/parametros');
    area.append(cabecalhoTela({ titulo: 'Modelo e parâmetros', subtitulo: `Somente leitura. ela_preditivo ${p.versao_pacote}; parâmetros versão ${p.versao_parametros} (${p.data_parametros}); horizonte ${p.horizonte_anos} anos.` }),
      el('div', { class: 'cartao' }, el('h2', { text: 'Rede Bayesiana (DAG)' }), el('ol', {}, p.dag.map((t) => el('li', { text: t })))),
      el('div', { class: 'cartao' }, el('h2', { text: 'Genes e parâmetros da literatura' }), tabela([
        { rotulo: 'Gene', chave: 'gene' }, { rotulo: 'Herança', chave: 'heranca' }, { rotulo: 'Penetrância [IC 95 %]', valor: (g) => `${fmtNum(g.penetrancia.valor, 2)} [${fmtNum(g.penetrancia.ic95[0], 3)}–${fmtNum(g.penetrancia.ic95[1], 3)}]${g.penetrancia.confirmar ? ' (a confirmar)' : ''}` },
        { rotulo: 'Beta (α, β)', valor: (g) => `${fmtNum(g.penetrancia.alpha, 2)}, ${fmtNum(g.penetrancia.beta, 2)}` }, { rotulo: 'Início: mediana (método)', valor: (g) => { const m = g.inicio.metodo; const metodo = m && typeof m === 'object' ? [m.tipo || g.inicio.distribuicao, m.metodo].filter(Boolean).join(', ') : (m || g.inicio.distribuicao); return `${fmtNum(g.inicio.mediana, 1)} anos (${metodo})${g.inicio.confirmar ? ' (a confirmar)' : ''}`; } },
        { rotulo: 'Efeito do sexo (M/F, anos)', valor: (g) => `${fmtNum(g.delta_sexo.M, 0)} / ${fmtNum(g.delta_sexo.F, 0)}` }], p.genes)),
      el('div', { class: 'cartao' }, el('h2', { text: 'Citações' }), el('ul', {}, p.genes.map((g) => el('li', {}, el('strong', { text: `${g.gene}: ` }), `penetrância — ${g.penetrancia.citacao}. Início — ${g.inicio.citacao}. Sexo — ${g.delta_citacao}.`)))),
      el('div', { class: 'cartao' }, el('h2', { text: 'Tabela 6: calibração das priors e das distribuições de início' }), tabelaRegistros({ colunas: p.tabela_calibracao.length ? Object.keys(p.tabela_calibracao[0]) : [], linhas: p.tabela_calibracao, legenda: 'Calibração' })),
      el('div', { class: 'cartao' }, el('h2', { text: 'Limiares e filtros' }), el('dl', { class: 'lista-definicao' }, el('dt', { text: 'C9orf72 patogênico' }), el('dd', { text: `≥ ${p.limiar_repeticoes_c9orf72.patogenico} repetições; intermediário a partir de ${p.limiar_repeticoes_c9orf72.intermediario}` }),
        el('dt', { text: 'Filtro de qualidade do VCF' }), el('dd', { text: `DP ≥ ${p.filtro_qualidade.dp_minimo}, GQ ≥ ${p.filtro_qualidade.gq_minimo}, FILTER = PASS${p.filtro_qualidade.exigir_pass ? '' : ' (não exigido)'}` }),
        el('dt', { text: 'Extensões' }), el('dd', { text: `${p.extensoes.repeticoes}; ${p.extensoes.cox}.` }))),
      el('div', { class: 'cartao' }, el('h2', { text: 'Limitação' }), el('p', { text: p.limitacao_modelo })),
      el('div', { class: 'cartao' }, el('h2', { text: 'Arquivos em uso' }), el('p', { class: 'pequeno texto-suave', text: 'Os parâmetros e a tabela curada que o artefato lê. Uma cópia editada pode ser enviada como arquivo alternativo numa análise sem registro ou numa execução do artefato (opções --config e --tabela-variantes da linha de comando).' }),
        el('div', { class: 'acoes' }, el('a', { class: 'botao botao-secundario', href: '/api/parametros/arquivo', download: 'parametros_literatura.yaml' }, icone('baixar'), 'Parâmetros (YAML)'), el('a', { class: 'botao botao-secundario', href: '/api/parametros/tabela-variantes', download: 'variantes_curadas.csv' }, icone('baixar'), 'Tabela curada (CSV)'))));
  }

  // ---------------------------------------------------------------------------------------------
  // Administrador
  // ---------------------------------------------------------------------------------------------
  function cartaoUsuario(u, acoes) {
    const perfil = u.perfil || {};
    const itens = [['E-mail', u.email], ['CPF', u.cpf_mascarado], ['Papel', u.papel_rotulo], ['Situação', u.situacao_rotulo], ['Cadastro', fmtData(u.criado_em)]];
    if (u.papel === 'MEDICO') itens.push(['Registro', perfil.tipo === 'CRM' ? `CRM ${perfil.crm || '—'}/${perfil.uf || '—'} (conferência manual)` : `Aconselhador(a) sem CRM: ${perfil.formacao || '—'}, ${perfil.instituicao || '—'}`], ['Especialidade', perfil.especialidade || '—']);
    if (u.papel === 'PESQUISADOR') itens.push(['Tipo', perfil.tipo || '—'], ['Cargo', perfil.cargo || '—'], ['Linha de pesquisa', perfil.linha_pesquisa || '—'], ['Instituição / grupo', `${perfil.instituicao || '—'} / ${perfil.grupo || '—'}`], ['ORCID', perfil.orcid || '—'], ['Lattes', perfil.lattes_url || '—'], ['Projetos', perfil.projetos || '—'], ['Evidências', perfil.evidencias || '—']);
    if (u.encerramento_solicitado_em) itens.push(['Encerramento pedido em', fmtData(u.encerramento_solicitado_em)]);
    if (u.mensagem_admin) itens.push(['Mensagem do administrador', u.mensagem_admin]);
    if (u.resposta_usuario) itens.push([`Resposta do usuário (${fmtData(u.respondido_em)})`, u.resposta_usuario]);
    const dl = el('dl', { class: 'lista-definicao' }, itens.map(([k, v]) => [el('dt', { text: k }), el('dd', { text: v })]).flat());
    return el('div', { class: 'cartao' }, el('div', { class: 'cabecalho-tela' }, el('div', { class: 'titulos' }, el('h2', { text: u.nome }), el('div', { class: 'chips' }, chip(u.papel_rotulo, 'chip-azul'), chipSituacaoConta(u), chip(`id ${u.id}`, 'chip-neutro')))), dl, acoes ? acoes(u) : null);
  }
  async function telaPendentes(area) {
    definirTitulo('Cadastros pendentes');
    definirTrilha([['Administração'], ['Cadastros pendentes']]);
    const r = await api('GET', '/api/admin/cadastros/pendentes');
    area.append(cabecalhoTela({ titulo: 'Cadastros pendentes', subtitulo: 'Verificação manual, um cadastro por vez: confira os dados profissionais (CRM, formação, vínculo). ORCID, Lattes ou vínculo não aprovam automaticamente. O administrador não acessa registros, arquivos genéticos nem resultados.', chips: [chip(`${r.cadastros.length} pendente(s)`, r.cadastros.length ? 'chip-aviso' : 'chip-ok')] }));
    if (!r.cadastros.length) { area.append(vazio('Nenhum cadastro pendente.', 'check')); return; }
    const primeiro = r.cadastros[0].id;
    area.append(el('div', { class: 'cartao tabela-cartao' }, el('div', { class: 'cabecalho-tabela' }, el('strong', { text: 'Fila de verificação (mais antigos primeiro)' }), linkBotao('Analisar o primeiro', `#/admin/pendentes/${primeiro}`, { classe: 'botao-pequeno', icone: 'seta-dir' })), tabela([
      { rotulo: 'Nome', chave: 'nome' }, { rotulo: 'Papel', chave: 'papel_rotulo' }, { rotulo: 'Situação', valor: (u) => chipSituacaoConta(u) }, { rotulo: 'Cadastro', valor: (u) => fmtData(u.criado_em) },
      { rotulo: 'Resposta do usuário', valor: (u) => (u.resposta_usuario ? chip('respondeu', 'chip-azul') : '—') },
      { rotulo: 'Ações', valor: (u) => linkBotao('Analisar', `#/admin/pendentes/${u.id}`, { classe: 'botao-pequeno', icone: 'seta-dir' }) }], r.cadastros, { blocos: true })));
  }
  async function telaPendente(area, params) {
    const id = Number(params[0]);
    definirTitulo('Analisar cadastro');
    definirTrilha([['Administração'], ['Cadastros pendentes', '#/admin/pendentes'], ['Analisar']]);
    const [u, fila] = await Promise.all([api('GET', `/api/admin/usuarios/${id}`), api('GET', '/api/admin/cadastros/pendentes')]);
    const ids = fila.cadastros.map((x) => x.id);
    const pos = ids.indexOf(id);
    const proximo = pos >= 0 && pos < ids.length - 1 ? ids[pos + 1] : null;
    const pendente = ['PENDENTE', 'INFORMACOES_SOLICITADAS'].includes(u.situacao);
    area.append(cabecalhoTela({ titulo: 'Analisar cadastro', subtitulo: pendente ? `Cadastro ${pos + 1} de ${ids.length} na fila.` : 'Este cadastro já foi tratado.', chips: [chipSituacaoConta(u)], acoes: [linkBotao('Voltar à fila', '#/admin/pendentes', { classe: 'botao-secundario', icone: 'seta-esq' }), proximo ? linkBotao('Próximo pendente', `#/admin/pendentes/${proximo}`, { classe: 'botao-secundario', icone: 'seta-dir' }) : null] }));
    area.append(duasColunas(cartaoUsuario(u, pendente ? (u2) => acoesPendente(u2, proximo) : null), cartaoApoio('Como verificar', ['Confira o número do CRM e a UF no portal do conselho; para aconselhador sem CRM, a formação e a instituição.', 'Para pesquisador, confira ORCID, Lattes e vínculo. Nada disso aprova automaticamente.', 'Se faltar informação, use "Pedir informações": o usuário responde na tela "Situação do cadastro".', 'Reprovar exige justificativa, que o usuário lê.'])));
  }
  function acoesPendente(u, proximo) {
    const bloco = el('div');
    const mensagem = campo({ nome: `mensagem_${u.id}`, rotulo: 'Mensagem ao usuário (pedido de informações ou justificativa da reprovação)', tipo: 'textarea', linhas: 3 });
    const agir = async (acao, exigeMsg) => {
      if (exigeMsg && mensagem.valor().trim().length < 3) { mensagem.setErro('Escreva a mensagem.'); mensagem.input.focus(); return; }
      try { const r = await api('POST', `/api/admin/usuarios/${u.id}/${acao}`, { json: { mensagem: mensagem.valor().trim() } }); estado.avisoPendente = `${r.mensagem} Nova situação: ${r.situacao}.`; navegar(proximo ? `#/admin/pendentes/${proximo}` : '#/admin/pendentes'); }
      catch (e) { avisar('erro', e.message); }
    };
    bloco.append(mensagem.no, el('div', { class: 'acoes' }, botao('Aprovar', { icone: 'check', onclick: () => agir('aprovar', false) }), botao('Pedir informações', { classe: 'botao-secundario', icone: 'ajuda', onclick: () => agir('solicitar-informacoes', true) }), botao('Reprovar', { classe: 'botao-perigo', onclick: () => agir('reprovar', true) })));
    return bloco;
  }
  async function telaUsuarios(area) {
    definirTitulo('Usuários');
    definirTrilha([['Administração'], ['Usuários']]);
    const papel = campo({ nome: 'papel', rotulo: 'Papel', tipo: 'select', opcoes: [['', 'Todos'], ['MEDICO', 'Médico'], ['PESQUISADOR', 'Pesquisador'], ['ADMIN', 'Administrador']] });
    const situacao = campo({ nome: 'situacao', rotulo: 'Situação', tipo: 'select', opcoes: [['', 'Todas'], ['PENDENTE', 'Pendente'], ['INFORMACOES_SOLICITADAS', 'Informações solicitadas'], ['VERIFICADO', 'Verificado'], ['REPROVADO', 'Reprovado'], ['DESATIVADO', 'Desativado']] });
    const busca = campo({ nome: 'busca', rotulo: 'Buscar por nome ou e-mail', tipo: 'search', icone: 'lupa', opcional: true });
    const lista = el('div');
    const form = el('form', { novalidate: true, role: 'search', onsubmit: async (ev) => { ev.preventDefault(); await carregar(); } }, el('div', { class: 'grade-campos grade-campos-3' }, papel.no, situacao.no, busca.no), el('div', { class: 'acoes' }, botao('Filtrar', { tipo: 'submit', icone: 'filtro' })));
    area.append(cabecalhoTela({ titulo: 'Usuários', subtitulo: 'Médicos, aconselhadores, pesquisadores e administradores. Ninguém se cadastra nem é promovido a administrador: um administrador novo só é criado por outro, aqui.' }), el('div', { class: 'cartao' }, form), lista, cartaoNovoAdministrador(() => carregar()));
    async function carregar() {
      limpar(lista);
      let r;
      if (busca.valor().trim()) r = await api('POST', '/api/admin/usuarios/busca', { json: { texto: busca.valor().trim() } });
      else { const q = new URLSearchParams(); if (papel.valor()) q.set('papel', papel.valor()); if (situacao.valor()) q.set('situacao', situacao.valor()); r = await api('GET', `/api/admin/usuarios${q.toString() ? '?' + q.toString() : ''}`); }
      if (!r.usuarios.length) { lista.append(vazio('Nenhum usuário com esses filtros.', 'pacientes')); return; }
      lista.append(el('div', { class: 'cartao tabela-cartao' }, el('div', { class: 'cabecalho-tabela' }, el('strong', { text: `${r.total} usuário(s)` })), tabela([
        { rotulo: 'Id', chave: 'id', num: true }, { rotulo: 'Nome', chave: 'nome' }, { rotulo: 'E-mail', chave: 'email' }, { rotulo: 'Papel', chave: 'papel_rotulo' }, { rotulo: 'Situação', valor: (u) => chipSituacaoConta(u) },
        { rotulo: 'Encerramento', valor: (u) => (u.encerramento_solicitado_em ? chip('pedido', 'chip-aviso') : '—') },
        { rotulo: 'Ações', valor: (u) => u.id === estado.eu.usuario.id ? el('span', { class: 'texto-suave', text: 'você' }) : el('div', { class: 'acoes acoes-compactas' },
          u.situacao === 'DESATIVADO' ? botao('Reativar', { classe: 'botao-secundario botao-pequeno', ariaLabel: `Reativar ${u.nome}`, onclick: () => agirUsuario(u, 'reativar', carregar) }) : botao('Desativar', { classe: 'botao-perigo botao-pequeno', ariaLabel: `Desativar ${u.nome}`, onclick: () => agirUsuario(u, 'desativar', carregar) }),
          !['VERIFICADO', 'DESATIVADO'].includes(u.situacao) ? linkBotao('Analisar', `#/admin/pendentes/${u.id}`, { classe: 'botao-secundario botao-pequeno' }) : null) }], r.usuarios, { blocos: true })));
    }
    await carregar();
  }
  async function agirUsuario(u, acao, depois) {
    if (acao === 'desativar' && !window.confirm(`Desativar a conta de ${u.nome}? As sessões serão encerradas.`)) return;
    try { const r = await api('POST', `/api/admin/usuarios/${u.id}/${acao}`, { json: {} }); avisar('sucesso', `${r.mensagem} Situação: ${r.situacao}.`); await depois(); } catch (e) { avisar('erro', e.message); }
  }
  async function telaAuditoria(area) {
    definirTitulo('Auditoria');
    definirTrilha([['Administração'], ['Auditoria']]);
    const acoesLista = (await api('GET', '/api/admin/auditoria?por_pagina=1')).acoes;
    const usuarioId = campo({ nome: 'usuario_id', rotulo: 'Id do usuário', tipo: 'number', opcional: true, atributos: { min: 1 } });
    const acao = campo({ nome: 'acao', rotulo: 'Ação', tipo: 'select', opcoes: [['', 'Todas'], ...acoesLista.map((a) => [a, a])] });
    const resultado = campo({ nome: 'resultado', rotulo: 'Resultado', tipo: 'select', opcoes: [['', 'Todos'], ['OK', 'OK'], ['NEGADO', 'Negado'], ['FALHA', 'Falha']] });
    const de = campo({ nome: 'de', rotulo: 'De', tipo: 'date', opcional: true });
    const ate = campo({ nome: 'ate', rotulo: 'Até', tipo: 'date', opcional: true });
    let pagina = 1;
    const lista = el('div');
    const verif = el('div');
    const form = el('form', { novalidate: true, role: 'search', onsubmit: async (ev) => { ev.preventDefault(); pagina = 1; await carregar(); } }, el('div', { class: 'grade-campos' }, usuarioId.no, acao.no, resultado.no, de.no, ate.no),
      el('div', { class: 'acoes' }, botao('Filtrar', { tipo: 'submit', icone: 'filtro' }), botao('Verificar a cadeia de hash', { classe: 'botao-secundario', icone: 'escudo', onclick: async () => { const v = await api('GET', '/api/admin/auditoria/verificacao'); limpar(verif); verif.append(el('div', { class: `alerta ${v.ok ? 'alerta-sucesso' : 'alerta-erro'}`, role: 'status' }, icone(v.ok ? 'check' : 'alerta'), el('p', { text: v.ok ? `Cadeia íntegra: ${v.total} registros encadeados.` : `Adulteração detectada na sequência ${v.primeira_falha} (de ${v.total}).` }))); } })));
    area.append(cabecalhoTela({ titulo: 'Auditoria', subtitulo: 'Registro só de inclusão, encadeado por hash; sem nome de paciente, CPF completo ou senha. Toda consulta também é registrada.' }), el('div', { class: 'cartao' }, form), verif, lista);
    async function carregar() {
      limpar(lista);
      const q = new URLSearchParams({ pagina: String(pagina), por_pagina: '100' });
      if (usuarioId.valor()) q.set('usuario_id', usuarioId.valor()); if (acao.valor()) q.set('acao', acao.valor()); if (resultado.valor()) q.set('resultado', resultado.valor()); if (de.valor()) q.set('de', de.valor()); if (ate.valor()) q.set('ate', ate.valor());
      const r = await api('GET', `/api/admin/auditoria?${q.toString()}`);
      const paginas = Math.max(1, Math.ceil(r.total / r.por_pagina));
      lista.append(el('div', { class: 'cartao tabela-cartao' }, el('div', { class: 'cabecalho-tabela' }, el('strong', { text: `${r.total} registro(s); página ${r.pagina} de ${paginas}` }),
        el('div', { class: 'acoes acoes-compactas' }, botao('Página anterior', { classe: 'botao-secundario botao-pequeno', icone: 'seta-esq', desabilitado: pagina <= 1, onclick: async () => { pagina--; await carregar(); } }), botao('Próxima página', { classe: 'botao-secundario botao-pequeno', icone: 'seta-dir', desabilitado: pagina >= paginas, onclick: async () => { pagina++; await carregar(); } }))), tabelaAuditoria(r.registros)));
    }
    await carregar();
  }

  // ---------------------------------------------------------------------------------------------
  // Artefato: os comandos da linha de comando (reprodução, avaliação, cenários) executados pela interface
  // ---------------------------------------------------------------------------------------------
  const ESTADO_TAREFA = { executando: ['Em execução', 'chip-azul', 'relogio'], concluida: ['Concluída', 'chip-ok', 'check'], falhou: ['Falhou', 'chip-erro', 'alerta'], cancelada: ['Cancelada', 'chip-neutro', 'fechar'], interrompida: ['Interrompida', 'chip-aviso', 'alerta'] };
  const PAPEL_CURTO = { MEDICO: 'médico', PESQUISADOR: 'pesquisador', ADMIN: 'administrador' };
  let contadorAbas = 0;
  function chipEstadoTarefa(t) { const [rotulo, classe, ic] = ESTADO_TAREFA[t.estado] || [t.estado, 'chip-neutro', 'info']; return chip(rotulo, classe, ic); }
  function fmtDuracao(segundos) {
    if (segundos === null || segundos === undefined) return '—';
    const s = Math.round(Number(segundos));
    if (s < 60) return `${s} s`;
    const m = Math.floor(s / 60);
    return m < 60 ? `${m} min ${s % 60} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
  }
  function linhasDeTexto(texto) { return String(texto || '').split('\n').filter((l) => l.trim()).map((l) => el('p', { text: localizarNumeros(l.replace(/\*\*/g, '').replace(/`/g, '').replace(/^- /, '• ')) })); }
  function opcoesDeBase(ctx) { return [['padrao', ctx.base_em_uso ? `Base em uso (${ctx.base_em_uso})` : 'Base em uso (não há base real: só a tabela curada)'], ['so_tabela_curada', 'Só a tabela curada'], ...ctx.bases.map((b) => [b, b])]; }
  function formularioComando(cmd, ctx) { // campos desenhados a partir das opções do comando, as mesmas da linha de comando
    const campos = {};
    const grupos = new Map();
    for (const o of cmd.opcoes) {
      const flags = [o.flag, ...o.flags_extras].join(' ou ');
      const dicaCampo = [o.dica, `Linha de comando: ${flags}.`].filter(Boolean).join(' ');
      const atributos = {};
      let c;
      if (o.tipo === 'marcacao') c = marcacao({ nome: o.nome, rotulo: `${o.rotulo} (${o.flag})` });
      else if (o.tipo === 'escolha') c = campo({ nome: o.nome, rotulo: o.rotulo, tipo: 'select', valor: o.padrao, opcoes: o.opcoes.map((x) => [x, x]), dica: dicaCampo });
      else if (o.tipo === 'base') c = campo({ nome: o.nome, rotulo: o.rotulo, tipo: 'select', valor: 'padrao', opcoes: opcoesDeBase(ctx), dica: dicaCampo });
      else if (o.tipo === 'origem') c = campo({ nome: o.nome, rotulo: o.rotulo, tipo: 'select', valor: 'pacote', opcoes: [['pacote', 'Cenários sintéticos do artefato'], ...ctx.origens.map((x) => [x.id, `Cenários gerados em ${fmtData(x.iniciada_em)}`])], dica: dicaCampo });
      else if (o.tipo === 'arquivo') c = campo({ nome: o.nome, rotulo: o.rotulo, tipo: 'file', opcional: true, dica: dicaCampo, atributos: { accept: '.yaml,.yml' } });
      else if (o.tipo === 'inteiros') c = campo({ nome: o.nome, rotulo: o.rotulo, valor: (o.padrao || []).join(', '), opcional: !o.padrao, dica: dicaCampo, atributos: { inputmode: 'numeric' } });
      else if (o.tipo === 'data') c = campo({ nome: o.nome, rotulo: o.rotulo, opcional: true, dica: dicaCampo, atributos: { placeholder: 'AAAA-MM-DD', inputmode: 'numeric' } });
      else {
        if (o.minimo !== null) atributos.min = o.minimo;
        if (o.maximo !== null) atributos.max = o.maximo;
        atributos.step = o.tipo === 'decimal' ? 'any' : 1;
        c = campo({ nome: o.nome, rotulo: o.rotulo, tipo: 'number', valor: o.padrao, opcional: o.padrao === null, dica: dicaCampo, atributos });
      }
      campos[o.nome] = c;
      if (!grupos.has(o.grupo)) grupos.set(o.grupo, []);
      grupos.get(o.grupo).push(c.no);
    }
    const no = el('div', {}, [...grupos.entries()].map(([grupo, nos]) => (grupo ? el('fieldset', {}, el('legend', { text: grupo }), el('div', { class: 'grade-campos grade-campos-3' }, nos)) : el('div', { class: 'grade-campos grade-campos-3' }, nos))));
    return { no, campos, coletar() {
      const parametros = {};
      const fd = new FormData();
      for (const o of cmd.opcoes) {
        const c = campos[o.nome];
        if (o.tipo === 'arquivo') { if (c.input.files.length) fd.append(o.nome, c.input.files[0]); } else parametros[o.nome] = o.tipo === 'marcacao' ? c.valor() : String(c.valor()).trim();
      }
      fd.append('comando', cmd.nome);
      fd.append('parametros', JSON.stringify(parametros));
      return fd;
    } };
  }
  async function telaArtefato(area) {
    definirTitulo('Artefato');
    definirTrilha([[areaDoPapel()], ['Artefato']]);
    const [ctx, lista] = await Promise.all([api('GET', '/api/artefato/comandos'), api('GET', '/api/artefato/tarefas')]);
    area.append(cabecalhoTela({ titulo: 'Artefato: reprodução e avaliação', subtitulo: 'Os comandos da linha de comando, com as mesmas opções e as mesmas saídas, executados daqui. Rodam em segundo plano, um por vez, só com dados sintéticos e a base pública do ClinVar.' }));
    if (ctx.em_andamento) area.append(el('div', { class: 'alerta alerta-info' }, icone('relogio'), el('p', {}, 'Há uma execução em andamento. ', el('a', { href: `#/artefato/${ctx.em_andamento}`, text: 'Acompanhar' }), '. Uma nova só pode começar quando ela terminar.')));
    const corpo = el('div');
    const prog = caixaProgresso();
    let atual = null;
    const desenhar = (nome) => { atual = formularioComando(ctx.comandos.find((c) => c.nome === nome), ctx); limpar(corpo).append(atual.no); };
    const escolha = cartoesOpcao({ nome: 'comando', rotulo: 'Comando', valor: 'avaliar', onchange: desenhar, opcoes: ctx.comandos.map((c) => ({ valor: c.nome, titulo: c.titulo, descricao: `${c.descricao} Duração: ${c.duracao}. Linha de comando: ela-preditivo ${c.nome}.`, icone: c.nome === 'tudo' ? 'prancheta' : c.nome === 'avaliar' ? 'grafico' : 'dna' })) });
    const enviar = botao('Executar', { tipo: 'submit', icone: 'frasco', desabilitado: !!ctx.em_andamento });
    const form = el('form', { novalidate: true, onsubmit: async (ev) => {
      ev.preventDefault();
      enviar.disabled = true; prog.mostrar('Iniciando a execução…');
      try {
        const t = await api('POST', '/api/artefato/tarefas', { form: atual.coletar() });
        navegar(`#/artefato/${t.id}`);
      } catch (e) { aplicarErros(atual.campos, e.campos, Object.keys(e.campos).length ? null : e.message); enviar.disabled = false; } finally { prog.esconder(); }
    } }, escolha.no, corpo, prog.caixa, el('div', { class: 'acoes acoes-direita' }, enviar));
    desenhar('avaliar');
    area.append(el('div', { class: 'cartao' }, el('h2', { text: 'Nova execução' }), form));
    area.append(el('div', { class: 'cartao' }, el('h2', { text: 'Execuções' }), lista.tarefas.length ? tabela([
      { rotulo: 'Início', valor: (t) => fmtData(t.iniciada_em) }, { rotulo: 'Comando', valor: (t) => t.titulo }, { rotulo: 'Estado', valor: (t) => chipEstadoTarefa(t) },
      { rotulo: 'Duração', valor: (t) => fmtDuracao(t.estado === 'executando' ? t.decorrido_s : t.duracao_s) }, { rotulo: 'Disparada por', valor: (t) => (t.minha ? 'você' : PAPEL_CURTO[t.papel] || '—') },
      { rotulo: 'Ação', valor: (t) => linkBotao('Abrir', `#/artefato/${t.id}`, { classe: 'botao-secundario botao-pequeno', icone: 'seta-dir' }) }], lista.tarefas, { blocos: true, legenda: 'Execuções do artefato, da mais recente para a mais antiga' }) : el('p', { class: 'texto-suave', text: 'Nenhuma execução ainda.' })));
    area.append(el('details', {}, el('summary', { text: 'Equivalência com a linha de comando' }), el('p', { class: 'pequeno texto-suave', text: 'Onde a interface oferece cada comando e cada opção de ela-preditivo. Só subir o serviço (servir) e criar a chave de cifra (gerar-chave) ficam com o arranque: a chave é criada sozinha na primeira subida.' }),
      tabela([{ rotulo: 'Comando', chave: 'comando' }, { rotulo: 'Opção', chave: 'opcao' }, { rotulo: 'Na interface', chave: 'onde' }, { rotulo: 'Campo', valor: (x) => x.campo || '—' }], ctx.equivalencia, { legenda: 'Equivalência entre a linha de comando e a interface' })));
  }
  function corpoRelatorio(r, base, extras) { // relatório de uma pasta da saída: texto, tabelas, figuras e metadados
    const cartoes = [];
    const tabelas = () => {
      if (!r.tabelas.length) return el('p', { class: 'texto-suave', text: 'Este relatório não tem tabelas.' });
      const ir = campo({ nome: 'ir_para_tabela', rotulo: 'Ir para', tipo: 'select', opcoes: r.tabelas.map((t, i) => [String(i), t.legenda.split(' — ')[0] + (t.legenda.includes(' — ') ? `: ${t.legenda.split(' — ')[1].slice(0, 70)}` : '')]) });
      ir.input.addEventListener('change', () => { const alvo = cartoes[Number(ir.valor())]; if (alvo) alvo.scrollIntoView({ behavior: 'smooth', block: 'start' }); });
      for (const t of r.tabelas) cartoes.push(el('div', { class: 'cartao' }, tabelaRegistros(t), t.total_de_linhas > t.linhas.length ? el('p', { class: 'pequeno texto-suave', text: `Mostrando ${t.linhas.length} de ${t.total_de_linhas} linhas; o arquivo completo está no pacote.` }) : null));
      return el('div', {}, el('div', { class: 'grade-campos' }, ir.no), cartoes);
    };
    const figuras = () => (r.figuras.length ? el('div', {}, r.figuras.map((f) => el('figure', { class: 'figura' }, el('a', { href: `${base}/arquivo?caminho=${encodeURIComponent(f.caminho)}`, target: '_blank', rel: 'noopener', title: 'Abrir a figura em tamanho real' }, el('img', { src: `${base}/arquivo?caminho=${encodeURIComponent(f.caminho)}`, alt: f.legenda, loading: 'lazy' })), el('figcaption', { text: f.legenda })))) : el('p', { class: 'texto-suave', text: 'Este relatório não tem figuras.' }));
    const metadados = () => el('div', {}, Object.keys(r.metadados).length ? el('div', { class: 'cartao' }, el('h2', { text: 'Metadados da execução (reprodutibilidade)' }), el('dl', { class: 'lista-definicao' }, Object.entries(r.metadados).filter(([, v]) => v !== null).map(([k, v]) => [el('dt', { text: k }), el('dd', { text: typeof v === 'object' ? JSON.stringify(v) : String(v) })]).flat())) : null,
      el('details', {}, el('summary', { text: 'Relatório completo (Markdown)' }), el('pre', { text: r.relatorio_md })));
    contadorAbas += 1;
    return el('div', {}, el('h2', { text: r.titulo }), abas([
      { rotulo: 'Texto', icone: 'prancheta', conteudo: () => el('div', {}, r.secoes.map((s) => el('div', { class: 'cartao' }, el('h3', { text: s.titulo }), linhasDeTexto(s.texto)))) },
      { rotulo: `Tabelas (${r.tabelas.length})`, icone: 'grafico', conteudo: tabelas },
      { rotulo: `Figuras (${r.figuras.length})`, icone: 'degraus', conteudo: figuras },
      { rotulo: 'Metadados', icone: 'escudo', conteudo: metadados },
      ...(extras || []),
    ], `rel-${contadorAbas}`, { rotulo: 'Partes do relatório' }));
  }
  async function telaTarefa(area, params) {
    const id = params[0];
    const base = `/api/artefato/tarefas/${id}`;
    definirTitulo('Execução do artefato');
    definirTrilha([[areaDoPapel()], ['Artefato', '#/artefato'], ['Execução']]);
    const corpo = el('div');
    area.append(corpo);
    const desenhar = (t) => {
      limpar(corpo);
      const acoes = [];
      if (t.estado === 'concluida') acoes.push(el('a', { class: 'botao', href: `${base}/pacote.zip`, download: '' }, icone('baixar'), 'Baixar pacote (.zip)'));
      if (t.minha) acoes.push(botao(t.estado === 'executando' ? 'Cancelar' : 'Remover', { classe: 'botao-perigo', icone: t.estado === 'executando' ? 'fechar' : 'lixeira', onclick: async () => {
        if (!window.confirm(t.estado === 'executando' ? 'Cancelar esta execução? O que já foi calculado se perde.' : 'Remover esta execução e a saída dela?')) return;
        try { await api('DELETE', base); estado.avisoPendente = t.estado === 'executando' ? 'Execução cancelada.' : 'Execução removida.'; navegar('#/artefato'); } catch (e) { avisar('erro', e.message); }
      } }));
      acoes.push(linkBotao('Voltar', '#/artefato', { classe: 'botao-secundario', icone: 'seta-esq' }));
      corpo.append(cabecalhoTela({ titulo: t.titulo, subtitulo: `Iniciada em ${fmtData(t.iniciada_em)}${t.minha ? ' por você' : ` por ${PAPEL_CURTO[t.papel] || 'outro usuário'}`}${t.duracao_s !== null && t.duracao_s !== undefined ? `; durou ${fmtDuracao(t.duracao_s)}` : ''}.`, chips: [chipEstadoTarefa(t)], acoes }));
      if (t.estado === 'executando') corpo.append(el('div', { class: 'ocupado', role: 'status' }, el('span', { text: `Em execução há ${fmtDuracao(t.decorrido_s)}. A página se atualiza sozinha; você pode sair e voltar depois.` })));
      else if (t.mensagem) corpo.append(el('div', { class: `alerta ${t.estado === 'falhou' ? 'alerta-erro' : 'alerta-aviso'}` }, icone('alerta'), el('p', { text: t.mensagem })));
      const execucao = () => el('div', {}, el('div', { class: 'cartao' }, el('h2', { text: 'Comando equivalente' }), el('pre', { text: t.linha_de_comando }), el('p', { class: 'pequeno texto-suave', text: 'É o que a linha de comando rodaria com estas opções; os caminhos foram trocados por nomes.' })),
        el('div', { class: 'cartao' }, el('h2', { text: 'Registro da execução' }), el('pre', { text: t.registro || '(o comando ainda não escreveu nada)' })));
      if (t.estado !== 'concluida' || !t.saida) { corpo.append(execucao()); return; }
      const arquivos = () => el('div', { class: 'cartao' }, el('h2', { text: `Arquivos da saída (${t.saida.total_de_arquivos})` }), tabela([
        { rotulo: 'Arquivo', valor: (a) => el('a', { href: `${base}/arquivo?caminho=${encodeURIComponent(a.caminho)}`, download: a.caminho.split('/').pop(), text: a.caminho }) }, { rotulo: 'Tamanho', valor: (a) => fmtBytes(a.tamanho), num: true }], t.saida.arquivos, { legenda: 'Arquivos escritos pelo comando' }));
      const extras = [{ rotulo: 'Arquivos', icone: 'arquivo', conteudo: arquivos }, { rotulo: 'Execução', icone: 'relogio', conteudo: execucao }];
      const rels = t.saida.relatorios;
      if (!rels.length) { contadorAbas += 1; corpo.append(abas(extras, `exe-${contadorAbas}`, { rotulo: 'Saída da execução' })); return; }
      const painel = el('div');
      const abrir = async (pasta) => {
        limpar(painel).append(el('div', { class: 'ocupado', role: 'status' }, el('span', { text: 'Carregando o relatório…' })));
        try { const r = await api('GET', `${base}/relatorio?pasta=${encodeURIComponent(pasta)}`); if (area.isConnected) limpar(painel).append(corpoRelatorio(r, base, extras)); } catch (e) { limpar(painel).append(el('p', { text: e.message })); }
      };
      if (rels.length > 1) {
        const seletor = campo({ nome: 'relatorio', rotulo: 'Relatório', tipo: 'select', valor: rels[0].pasta, opcoes: rels.map((x) => [x.pasta, x.titulo]), dica: `${rels.length} relatórios nesta execução.` });
        seletor.input.addEventListener('change', () => abrir(seletor.valor()));
        corpo.append(el('div', { class: 'cartao' }, el('div', { class: 'grade-campos' }, seletor.no)));
      }
      corpo.append(painel);
      abrir(rels[0].pasta);
    };
    const carregar = async () => {
      const t = await api('GET', base);
      if (!area.isConnected) return;
      desenhar(t);
      if (t.estado === 'executando') setTimeout(() => { if (area.isConnected) carregar().catch(() => {}); }, 3000);
    };
    await carregar();
  }

  // ---------------------------------------------------------------------------------------------
  // Base de anotação: a base em uso, os arquivos da pasta de bases e o registro de versões
  // ---------------------------------------------------------------------------------------------
  async function telaBase(area) {
    definirTitulo('Base de anotação');
    definirTrilha([[areaDoPapel()], ['Base de anotação']]);
    const b = await api('GET', '/api/base');
    area.append(cabecalhoTela({ titulo: 'Base de anotação', subtitulo: 'Subconjunto do ClinVar dos quatro genes usado para classificar as variantes. Cada resultado guarda o arquivo, a release e o sha256 da base usada.', chips: [b.em_uso ? chip(`Em uso: ${b.em_uso.nome}`, 'chip-ok', 'check') : chip('Só a tabela curada', 'chip-aviso', 'alerta')] }));
    if (b.sem_base) area.append(el('div', { class: 'alerta alerta-aviso' }, icone('alerta'), el('p', { text: `${b.sem_base}${b.pode_gerir ? ' Envie a base abaixo ou baixe a release do ClinVar.' : ' O administrador pode enviar a base por esta tela.'}` })));
    if (b.anotacao) {
      const an = b.anotacao;
      area.append(el('div', { class: 'cartao' }, el('h2', { text: 'Base em uso na anotação' }),
        el('p', { text: `${fmtNum(an.anotaveis, 0)} variantes entram no cruzamento com os VCFs; ${fmtNum(an.de_risco, 0)} são de risco.` }),
        an.n_fora_da_anotacao
          ? [el('p', { text: `${fmtNum(an.n_fora_da_anotacao, 0)} linha(s) da base ficam fora da anotação, com o motivo abaixo. O arquivo da base não é alterado.` }),
            tabela([{ rotulo: 'Gene', chave: 'gene' }, { rotulo: 'Registro', valor: (l) => l.nome || '—' }, { rotulo: 'rs', valor: (l) => l.rs || '—' }, { rotulo: 'ClinVar', valor: (l) => l.clnsig || '—' }, { rotulo: 'Motivo', chave: 'motivo' }], an.fora_da_anotacao, { blocos: true })]
          : el('p', { class: 'texto-suave', text: 'Nenhuma linha da base fica fora da anotação.' })));
    }
    const curto = (h) => (h ? `${h.slice(0, 12)}…` : '—');
    const registrar = async (nome, campoRelease) => {
      try { const r = await api('POST', '/api/base/versoes', { json: { arquivo: nome, release: campoRelease ? campoRelease.valor().trim() || null : null } }); estado.avisoPendente = `Versão registrada: release ${r.atual.release}.`; aoMudarRota(); } catch (e) { if (campoRelease && e.campos.release) { campoRelease.setErro(e.campos.release); campoRelease.input.focus(); } else avisar('erro', Object.values(e.campos)[0] || e.message); }
    };
    const releaseRegistro = campo({ nome: 'release_registro', rotulo: 'Release para registrar', opcional: true, dica: 'AAAA-MM-DD. Só é preciso quando o arquivo não traz a data no cabeçalho nem no nome.', atributos: { placeholder: 'AAAA-MM-DD', inputmode: 'numeric' } });
    area.append(el('div', { class: 'cartao' }, el('h2', { text: `Arquivos na pasta de bases (${b.pasta}/)` }), b.arquivos.length ? tabela([
      { rotulo: 'Arquivo', chave: 'nome' }, { rotulo: 'Release', valor: (a) => a.release || 'não identificada' }, { rotulo: 'Tamanho', valor: (a) => fmtBytes(a.tamanho), num: true }, { rotulo: 'sha256', valor: (a) => curto(a.sha256) },
      { rotulo: 'Situação', valor: (a) => el('span', {}, a.em_uso ? chip('em uso', 'chip-ok', 'check') : null, ' ', a.registrada ? chip('versão registrada', 'chip-azul') : chip('sem registro', 'chip-neutro')) },
      ...(b.pode_gerir ? [{ rotulo: 'Ação', valor: (a) => (a.registrada ? '—' : botao('Registrar versão', { classe: 'botao-secundario botao-pequeno', ariaLabel: `Registrar a versão de ${a.nome}`, onclick: () => registrar(a.nome, releaseRegistro) })) }] : [])], b.arquivos, { blocos: true, legenda: 'Arquivos reconhecidos como base; a primeira da ordem de preferência é a base em uso' }) : el('p', { class: 'texto-suave', text: `Nenhum arquivo reconhecido. Nomes aceitos: ${b.nomes_aceitos.join(', ')}.` }),
      b.pode_gerir && b.arquivos.some((a) => !a.registrada) ? el('div', { class: 'grade-campos' }, releaseRegistro.no) : null));
    area.append(el('div', { class: 'cartao' }, el('h2', { text: 'Versões registradas' }), b.versoes.length ? tabela([
      { rotulo: 'Release', chave: 'release' }, { rotulo: 'Arquivo', chave: 'arquivo' }, { rotulo: 'Variantes', chave: 'n_variantes', num: true }, { rotulo: 'Por classe', valor: (v) => Object.entries(v.por_classe || {}).map(([k, n]) => `${k} ${n}`).join('; ') },
      { rotulo: 'sha256', valor: (v) => curto(v.sha256) }, { rotulo: 'Registrada em', valor: (v) => String(v.registrado_em || '').replace('T', ' ') }], b.versoes, { blocos: true, legenda: 'Versões da base registradas, da mais recente para a mais antiga' }) : el('p', { class: 'texto-suave', text: 'Nenhuma versão registrada ainda.' })));
    if (b.relatorios.length) {
      const texto = el('pre', { hidden: true });
      area.append(el('div', { class: 'cartao' }, el('h2', { text: 'O que mudou entre versões' }), el('div', { class: 'acoes' }, b.relatorios.map((nome) => botao(nome.replace('atualizacao_', '').replace('.md', '').replace('_', ' → '), { classe: 'botao-secundario botao-pequeno', ariaLabel: `Abrir o relatório ${nome}`, onclick: async () => { try { const r = await api('GET', `/api/base/relatorios/${encodeURIComponent(nome)}`); texto.textContent = r.texto; texto.hidden = false; } catch (e) { avisar('erro', e.message); } } }))), texto));
    }
    if (!b.pode_gerir) return;
    const arquivo = campo({ nome: 'arquivo', rotulo: 'Arquivo da base', tipo: 'file', obrigatorio: true, dica: `Nomes aceitos: ${b.nomes_aceitos.join(', ')}. Um arquivo de mesmo nome já na pasta é guardado em anteriores/ antes de ser substituído.`, atributos: { accept: '.csv,.txt,.vcf,.gz' } });
    const release = campo({ nome: 'release', rotulo: 'Release', opcional: true, dica: 'AAAA-MM-DD. Obrigatória quando o arquivo não traz a data (ex.: base_consolidada_ela.csv).', atributos: { placeholder: 'AAAA-MM-DD', inputmode: 'numeric' } });
    const camposEnvio = { arquivo, release };
    const progEnvio = caixaProgresso();
    const botaoEnvio = botao('Enviar e registrar', { tipo: 'submit', icone: 'upload' });
    area.append(el('div', { class: 'cartao' }, el('h2', { text: 'Enviar base' }), el('p', { class: 'pequeno texto-suave', text: 'O mesmo que copiar o arquivo para a pasta de bases e rodar ela-preditivo atualizar-base --base ARQUIVO.' }), el('form', { novalidate: true, onsubmit: async (ev) => {
      ev.preventDefault();
      if (!arquivo.input.files.length) { aplicarErros(camposEnvio, { arquivo: 'Envie o arquivo da base.' }); return; }
      const fd = new FormData();
      fd.append('arquivo', arquivo.input.files[0]);
      if (release.valor().trim()) fd.append('release', release.valor().trim());
      botaoEnvio.disabled = true; progEnvio.mostrar('Enviando e conferindo a base…');
      try { const r = await api('POST', '/api/base/arquivos', { form: fd }); estado.avisoPendente = `Base enviada: ${r.arquivo}, release ${r.atual.release}, ${r.variantes} variantes${r.em_uso ? '; é a base em uso' : ''}.`; aoMudarRota(); } catch (e) { aplicarErros(camposEnvio, e.campos, Object.keys(e.campos).length ? null : e.message); } finally { botaoEnvio.disabled = false; progEnvio.esconder(); }
    } }, el('div', { class: 'grade-campos' }, arquivo.no, release.no), progEnvio.caixa, el('div', { class: 'acoes acoes-direita' }, botaoEnvio))));
    const releaseDownload = campo({ nome: 'release_download', rotulo: 'Release', opcional: true, dica: 'AAAA-MM-DD de uma release do arquivo mensal. Vazio = a mais recente.', atributos: { placeholder: 'AAAA-MM-DD', inputmode: 'numeric' } });
    const situacao = el('div');
    const acompanhar = (t) => {
      limpar(situacao).append(el('div', { class: 'acoes' }, chipEstadoTarefa(t), el('span', { class: 'pequeno texto-suave', text: `Iniciado em ${fmtData(t.iniciada_em)}; ${t.estado === 'executando' ? `em andamento há ${fmtDuracao(t.decorrido_s)}` : `durou ${fmtDuracao(t.duracao_s)}`}.` })), el('pre', { text: t.registro || '(o comando ainda não escreveu nada)' }));
      if (t.estado === 'executando') setTimeout(async () => { if (!area.isConnected) return; try { const n = await api('GET', `/api/base/tarefas/${t.id}`); if (n.estado === 'concluida') { estado.avisoPendente = 'Download concluído: release registrada.'; aoMudarRota(); } else acompanhar(n); } catch (e) { /* a próxima visita mostra a situação */ } }, 3000);
    };
    area.append(el('div', { class: 'cartao' }, el('h2', { text: 'Baixar a release do ClinVar' }), el('p', { class: 'pequeno texto-suave', text: `${b.comando_baixar.descricao} Fonte: ${b.fonte_do_download}. O servidor precisa de acesso à internet. Linha de comando: ela-preditivo atualizar-base --baixar.` }),
      el('div', { class: 'grade-campos' }, releaseDownload.no), el('div', { class: 'acoes acoes-direita' }, botao('Baixar e registrar', { icone: 'baixar', onclick: async () => {
        try { const t = await api('POST', '/api/base/baixar', { json: { release: releaseDownload.valor().trim() || null } }); acompanhar(t); } catch (e) { if (e.campos.release) { releaseDownload.setErro(e.campos.release); releaseDownload.input.focus(); } else avisar('erro', e.message); }
      } })), situacao));
    if (b.tarefa) acompanhar(b.tarefa);
  }

  // ---------------------------------------------------------------------------------------------
  // Primeiro acesso: administrador e dados de demonstração criados pela interface
  // ---------------------------------------------------------------------------------------------
  function cartaoCredenciais(r) { // senhas geradas, mostradas uma única vez
    const texto = ['papel\tsituação\te-mail\tsenha', ...r.credenciais.map((c) => `${c.papel}\t${c.situacao}\t${c.email}\t${c.senha}`)].join('\n');
    return el('div', { class: 'cartao' }, el('h2', { text: 'Contas de demonstração criadas' }),
      el('div', { class: 'alerta alerta-aviso' }, icone('alerta'), el('p', {}, el('strong', { text: 'Copie as senhas agora. ' }), r.aviso)),
      el('p', { class: 'pequeno texto-suave', text: `${r.credenciais.length} usuários, ${r.registros} registros fictícios, ${r.vcfs} VCFs sintéticos anexados e ${r.analises} análises.` }),
      tabela([{ rotulo: 'Papel', valor: (c) => PAPEL_CURTO[c.papel] || c.papel }, { rotulo: 'Situação', valor: (c) => c.situacao.toLowerCase().replace(/_/g, ' ') }, { rotulo: 'E-mail', chave: 'email' }, { rotulo: 'Senha', valor: (c) => el('code', { text: c.senha }) }], r.credenciais, { blocos: true, legenda: 'Contas de demonstração e senhas geradas' }),
      el('div', { class: 'acoes' }, botao('Baixar como texto', { classe: 'botao-secundario', icone: 'baixar', onclick: () => baixarBlob(new Blob([`${texto}\n`], { type: 'text/plain;charset=utf-8' }), 'contas_de_demonstracao.txt') }), linkBotao('Ir para Entrar', '#/entrar', { icone: 'seta-dir' })));
  }
  function cartaoDemonstracao(rota, explicacao) { // botão que cria a demonstração e troca o cartão pelas credenciais
    const prog = caixaProgresso();
    const cartao = el('div', { class: 'cartao' });
    const criar = botao('Criar dados de demonstração', { icone: 'frasco', onclick: async () => {
      criar.disabled = true; prog.mostrar('Criando usuários, registros fictícios e análises de exemplo… leva cerca de um minuto.');
      try {
        const r = await api('POST', rota, { json: {}, semRedirecionar: true });
        estado.sistema = await api('GET', '/api/sistema');
        renderizarCasca();
        cartao.replaceWith(cartaoCredenciais(r));
      } catch (e) { avisar('erro', e.message); criar.disabled = false; } finally { prog.esconder(); }
    } });
    cartao.append(el('h2', { text: 'Dados de demonstração' }), el('p', { text: explicacao }), el('p', { class: 'pequeno texto-suave', text: 'São criados um administrador, um médico e um pesquisador verificados, dois cadastros pendentes e oito registros fictícios com VCFs sintéticos e análises. As senhas aparecem aqui, uma única vez.' }), prog.caixa, el('div', { class: 'acoes' }, criar));
    return cartao;
  }
  function camposDeAdministrador(sis) { // nome, CPF, e-mail, senha e aceites (nunca pré-marcados)
    const versoes = (sis && sis.versoes_termos) || {};
    const nome = campo({ nome: 'nome', rotulo: 'Nome completo', obrigatorio: true, icone: 'pessoa', atributos: { autocomplete: 'name' } });
    const cpf = campo({ nome: 'cpf', rotulo: 'CPF', obrigatorio: true, atributos: { inputmode: 'numeric', placeholder: '000.000.000-00' } });
    cpf.input.addEventListener('input', () => { cpf.input.value = mascararCpf(cpf.input.value); });
    const email = campo({ nome: 'email', rotulo: 'E-mail', tipo: 'email', obrigatorio: true, icone: 'email', atributos: { autocomplete: 'username' } });
    const senha = campo({ nome: 'senha', rotulo: 'Senha do novo administrador', tipo: 'password', obrigatorio: true, icone: 'cadeado', mostrarSenha: true, dica: 'Mínimo de 10 caracteres; não pode ser igual ao e-mail nem ao CPF.', atributos: { autocomplete: 'new-password' } });
    const confirma = campo({ nome: 'confirma', rotulo: 'Confirme a senha', tipo: 'password', obrigatorio: true, icone: 'cadeado', mostrarSenha: true, atributos: { autocomplete: 'new-password' } });
    const aceitePriv = marcacao({ nome: 'aceite_privacidade', rotulo: `O titular da conta leu e aceita o aviso de privacidade (versão ${versoes.aviso_privacidade || '—'}).` });
    const aceiteUso = marcacao({ nome: 'aceite_termo_uso', rotulo: `O titular da conta leu e aceita o termo de uso (versão ${versoes.termo_uso || '—'}).` });
    const campos = { nome, cpf, email, senha, confirma, aceite_privacidade: aceitePriv, aceite_termo_uso: aceiteUso };
    return { campos, no: el('div', {}, el('div', { class: 'grade-campos' }, nome.no, cpf.no, email.no), el('div', { class: 'grade-campos' }, senha.no, confirma.no), aceitePriv.no, aceiteUso.no,
      el('p', { class: 'pequeno' }, el('a', { href: '#/privacidade', text: 'Ler o aviso de privacidade' }))),
      validar() {
        const erros = {};
        if (nome.valor().trim().length < 3) erros.nome = 'Informe o nome completo.';
        if (!cpfValido(cpf.valor())) erros.cpf = 'CPF inválido: confira os dígitos.';
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email.valor().trim())) erros.email = 'Informe um e-mail válido.';
        if (senha.valor().length < 10) erros.senha = 'A senha precisa ter pelo menos 10 caracteres.';
        if (confirma.valor() !== senha.valor()) erros.confirma = 'As senhas não coincidem.';
        if (!aceitePriv.valor()) erros.aceite_privacidade = 'É preciso aceitar o aviso de privacidade.';
        if (!aceiteUso.valor()) erros.aceite_termo_uso = 'É preciso aceitar o termo de uso.';
        return erros;
      },
      dados() { return { nome: nome.valor().trim(), cpf: cpf.valor(), email: email.valor().trim(), senha: senha.valor(), aceite_privacidade: aceitePriv.valor(), aceite_termo_uso: aceiteUso.valor(), versao_privacidade: versoes.aviso_privacidade, versao_termo_uso: versoes.termo_uso }; } };
  }
  async function telaPrimeiroAcesso(area) {
    definirTitulo('Primeiro acesso');
    definirTrilha([['EloSense'], ['Primeiro acesso']]);
    estado.sistema = await api('GET', '/api/sistema');
    const pa = estado.sistema.primeiro_acesso || {};
    if (!pa.administrador && !pa.demonstracao) { estado.avisoPendente = 'O primeiro acesso já foi feito. Entre com a sua conta.'; navegar('#/entrar'); return; }
    area.append(cabecalhoTela({ titulo: 'Primeiro acesso', subtitulo: 'A plataforma acabou de ser instalada e ainda não tem administrador. Esta tela só existe até ele ser criado; depois disso, o acesso é por conta e senha.', chips: [chip(estado.sistema.demonstracao ? 'Ambiente de homologação' : 'Ambiente de produção', estado.sistema.demonstracao ? 'chip-aviso' : 'chip-azul')] }));
    if (pa.demonstracao) area.append(cartaoDemonstracao('/api/primeiro-acesso/demonstracao', 'Para testar a plataforma com dados fictícios, crie a demonstração: ela já traz um administrador, e você não precisa preencher o formulário abaixo.'));
    if (!pa.administrador) return;
    const adm = camposDeAdministrador(estado.sistema);
    const enviar = botao('Criar administrador', { tipo: 'submit', icone: 'cadeado' });
    area.append(el('div', { class: 'cartao' }, el('h2', { text: pa.demonstracao ? 'Ou criar só o administrador' : 'Criar o administrador' }), el('p', { class: 'pequeno texto-suave', text: 'O administrador aprova os cadastros de médicos e pesquisadores, gere a base de anotação e consulta a auditoria. Não vê registros de pacientes nem resultados.' }),
      el('form', { novalidate: true, onsubmit: async (ev) => {
        ev.preventDefault();
        const erros = adm.validar();
        if (Object.keys(erros).length) { aplicarErros(adm.campos, erros); return; }
        enviar.disabled = true;
        try {
          const r = await api('POST', '/api/primeiro-acesso/administrador', { json: adm.dados(), semRedirecionar: true });
          estado.sistema = await api('GET', '/api/sistema');
          estado.avisoPendente = `Conta criada: ${r.mensagem}`;
          navegar('#/entrar');
        } catch (e) { aplicarErros(adm.campos, e.campos, Object.keys(e.campos).length ? null : e.message); } finally { enviar.disabled = false; }
      } }, adm.no, el('div', { class: 'acoes acoes-direita' }, enviar))));
  }
  function cartaoNovoAdministrador(depois) { // um administrador cria outro; a senha é temporária e gerada pelo sistema
    const nome = campo({ nome: 'nome', rotulo: 'Nome completo', obrigatorio: true, icone: 'pessoa' });
    const cpf = campo({ nome: 'cpf', rotulo: 'CPF', obrigatorio: true, atributos: { inputmode: 'numeric', placeholder: '000.000.000-00' } });
    cpf.input.addEventListener('input', () => { cpf.input.value = mascararCpf(cpf.input.value); });
    const email = campo({ nome: 'email', rotulo: 'E-mail', tipo: 'email', obrigatorio: true, icone: 'email' });
    const senhaAtual = campo({ nome: 'senha_atual', rotulo: 'Sua senha atual', tipo: 'password', obrigatorio: true, icone: 'cadeado', mostrarSenha: true, dica: 'Confirma que é você quem está criando a conta.', atributos: { autocomplete: 'current-password' } });
    const campos = { nome, cpf, email, senha_atual: senhaAtual };
    const resultado = el('div', { role: 'status' });
    const enviar = botao('Criar administrador', { tipo: 'submit', icone: 'mais' });
    const form = el('form', { novalidate: true, onsubmit: async (ev) => {
      ev.preventDefault();
      const erros = {};
      if (nome.valor().trim().length < 3) erros.nome = 'Informe o nome completo.';
      if (!cpfValido(cpf.valor())) erros.cpf = 'CPF inválido: confira os dígitos.';
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email.valor().trim())) erros.email = 'Informe um e-mail válido.';
      if (!senhaAtual.valor()) erros.senha_atual = 'Informe a sua senha.';
      if (Object.keys(erros).length) { aplicarErros(campos, erros); return; }
      enviar.disabled = true;
      try {
        const r = await api('POST', '/api/admin/administradores', { json: { nome: nome.valor().trim(), cpf: cpf.valor(), email: email.valor().trim(), senha_atual: senhaAtual.valor() } });
        form.reset();
        limpar(resultado).append(el('div', { class: 'alerta alerta-aviso' }, icone('alerta'), el('div', {}, el('p', {}, el('strong', { text: `Administrador criado: ${r.usuario.email}. ` }), r.aviso), el('p', {}, 'Senha temporária: ', el('code', { text: r.senha_temporaria })))));
        if (depois) await depois();
      } catch (e) { aplicarErros(campos, e.campos, Object.keys(e.campos).length ? null : e.message); } finally { enviar.disabled = false; }
    } }, el('div', { class: 'grade-campos grade-campos-3' }, nome.no, cpf.no, email.no), el('div', { class: 'grade-campos' }, senhaAtual.no), el('div', { class: 'acoes acoes-direita' }, enviar));
    return el('details', {}, el('summary', { text: 'Novo administrador' }), el('p', { class: 'pequeno texto-suave', text: 'O sistema gera uma senha temporária, mostrada aqui uma única vez; o novo administrador é obrigado a trocá-la no primeiro login. Médicos e pesquisadores continuam se cadastrando pela tela Criar conta e passando pela sua aprovação.' }), form, resultado);
  }
  async function telaTrocarSenha(area) { // senha temporária: nada mais fica acessível até a pessoa definir a própria senha
    definirTitulo('Trocar a senha');
    definirTrilha([['EloSense'], ['Trocar a senha']]);
    if (!estado.eu.trocar_senha) { navegar(inicioPorPapel()); return; }
    const atual = campo({ nome: 'senha_atual', rotulo: 'Senha temporária', tipo: 'password', obrigatorio: true, icone: 'cadeado', mostrarSenha: true, atributos: { autocomplete: 'current-password' } });
    const nova = campo({ nome: 'senha_nova', rotulo: 'Nova senha', tipo: 'password', obrigatorio: true, icone: 'cadeado', mostrarSenha: true, dica: 'Mínimo de 10 caracteres; diferente da temporária, do e-mail e do CPF.', atributos: { autocomplete: 'new-password' } });
    const confirma = campo({ nome: 'confirma', rotulo: 'Confirme a nova senha', tipo: 'password', obrigatorio: true, icone: 'cadeado', mostrarSenha: true, atributos: { autocomplete: 'new-password' } });
    const campos = { senha_atual: atual, senha_nova: nova, confirma };
    const enviar = botao('Definir a senha e continuar', { tipo: 'submit', icone: 'check' });
    area.append(cabecalhoTela({ titulo: 'Defina a sua senha', subtitulo: 'Você entrou com uma senha temporária. Ela serve só para este passo: defina a sua senha para usar a plataforma.' }),
      el('div', { class: 'cartao' }, el('form', { novalidate: true, onsubmit: async (ev) => {
        ev.preventDefault();
        const erros = {};
        if (!atual.valor()) erros.senha_atual = 'Informe a senha temporária.';
        if (nova.valor().length < 10) erros.senha_nova = 'A senha precisa ter pelo menos 10 caracteres.';
        if (confirma.valor() !== nova.valor()) erros.confirma = 'As senhas não coincidem.';
        if (Object.keys(erros).length) { aplicarErros(campos, erros); return; }
        enviar.disabled = true;
        try {
          await api('POST', '/api/contas/minha/senha', { json: { senha_atual: atual.valor(), senha_nova: nova.valor() } });
          await carregarSessao();
          renderizarCasca();
          estado.avisoPendente = 'Conta pronta: senha definida.';
          navegar(inicioPorPapel());
        } catch (e) { aplicarErros(campos, e.campos, Object.keys(e.campos).length ? null : e.message); } finally { enviar.disabled = false; }
      } }, el('div', { class: 'grade-campos grade-campos-3' }, atual.no, nova.no, confirma.no), el('div', { class: 'acoes acoes-direita' }, enviar))));
    atual.input.focus();
  }

  // ---------------------------------------------------------------------------------------------
  // Arranque
  // ---------------------------------------------------------------------------------------------
  window.addEventListener('hashchange', aoMudarRota);
  (async function iniciar() {
    await carregarSessao();
    renderizarCasca();
    await aoMudarRota();
    // A expiração por inatividade (30 min) é decidida pelo servidor: a próxima ação após expirar recebe 401 e volta a "Entrar".
  })();
})();
