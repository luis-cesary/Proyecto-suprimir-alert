'use strict';
const $ = id => document.getElementById(id);
const severityNames = ['Sin clasificar', 'Información', 'Warning', 'Average', 'High', 'Disaster'];
let config = null, groups = [], hosts = [], visibleHosts = [], problems = [], snapshot = '';
let selectedHosts = new Set(), selectedEvents = new Set(), onlyEligible = true, busy = false;
let activityPending = false;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function message(text, error = false) {
  $('message').textContent = text;
  $('message').classList.toggle('error', error);
  $('message').hidden = !text;
}
async function api(path, data) {
  const options = {credentials: 'same-origin', cache: 'no-store'};
  if (data !== undefined) {
    options.method = 'POST';
    options.headers = {'Content-Type': 'application/json', 'X-CSRF-Token': config.csrf};
    options.body = JSON.stringify(data);
  }
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'No se pudo completar la solicitud.');
  return result;
}
async function action(fn) {
  if (busy) return;
  busy = true;
  const controls = [...document.querySelectorAll('button, input, select')];
  const previous = controls.map(el => el.disabled);
  controls.forEach(el => { el.disabled = true; });
  document.body.setAttribute('aria-busy', 'true');
  message('Procesando…');
  try { await fn(); }
  catch (error) { message(error.message, true); }
  finally {
    controls.forEach((el, i) => { if (el.isConnected) el.disabled = previous[i]; });
    busy = false;
    document.body.removeAttribute('aria-busy');
    updateControls();
    await activity();
  }
}
function updateControls() {
  if (!config || busy) return;
  $('query').disabled = !selectedHosts.size || !$('group').value;
  $('refresh').disabled = !selectedHosts.size || !$('group').value;
  $('review').disabled = !snapshot || !selectedEvents.size;
  $('export').disabled = !problems.length;
  $('all-events').disabled = !snapshot || !problems.some(p => p.eligible);
  $('all-events').checked = selectedEvents.size > 0 && selectedEvents.size === problems.filter(p => p.eligible).length;
  $('all-events').indeterminate = selectedEvents.size > 0 && ! $('all-events').checked;
  $('stat-hosts').textContent = selectedHosts.size;
  $('severity-caption').textContent = `${severityNames[Number($('severity').value)]} · F5 Pool / Virtual Server`;
  $('selected-count').textContent = selectedEvents.size;
  $('apply').disabled = $('confirmation').value !== 'APLICAR' || (!config.dry_run && $('permissions').value !== 'PERMISOS VERIFICADOS');
}
function showConfig() {
  $('api-version').textContent = config.version;
  $('mode').textContent = config.demo ? 'DEMO · SIN CONEXIÓN' : config.dry_run ? 'SOLO LECTURA' : 'SUPRESIÓN MANUAL REAL';
  $('mode').classList.toggle('real', !config.dry_run);
  $('notice').classList.toggle('real', !config.dry_run);
  $('notice').textContent = config.demo
    ? 'Modo demostración. Los clientes, equipos y alertas son ficticios. Puedes recorrer el flujo completo sin conectar con Zabbix ni modificar eventos.'
    : config.dry_run
      ? 'Modo solo lectura. Los datos provienen de Zabbix; las operaciones de supresión se registran como simulaciones y no modifican eventos.'
      : 'Modo real habilitado. Solo se suprimen los eventos que selecciones y confirmes. El límite de intentos se comparte entre todas las pestañas.';
  $('stat-budget').textContent = config.dry_run ? '0' : config.remaining;
  $('budget-caption').textContent = config.dry_run ? 'Escrituras reales deshabilitadas' : `De ${config.limit} intentos por ejecución`;
}
function renderGroups() {
  const current = $('group').value, term = $('group-search').value.toLocaleLowerCase();
  const filtered = groups.filter(g => g.name.toLocaleLowerCase().includes(term) || g.groupid === current);
  $('group').replaceChildren(new Option(filtered.length ? 'Selecciona un cliente' : 'Sin grupos coincidentes', ''));
  for (const group of filtered) $('group').add(new Option(`${group.name} · ${group.groupid}`, group.groupid));
  $('group').value = current;
}
function renderHosts() {
  $('hosts').replaceChildren();
  $('host-count').textContent = `${visibleHosts.length} de ${hosts.length} equipos`;
  if (!visibleHosts.length) $('hosts').append(node('div', hosts.length ? 'Sin coincidencias para este filtro.' : 'Sin equipos visibles en el grupo.', 'empty compact'));
  for (const host of visibleHosts) {
    const row = node('div', undefined, 'host-row');
    const check = node('input'); check.type = 'checkbox'; check.id = `host-${host.hostid}`; check.checked = selectedHosts.has(host.hostid);
    const label = node('label'); label.htmlFor = check.id;
    label.append(node('strong', host.host), node('small', `${host.name} · ID ${host.hostid}${host.status !== '0' ? ' · Deshabilitado' : ''}`));
    const interfaces = host.interfaces.map(i => `${i.ip || 'Sin IP'}${i.useip === '0' ? ` · DNS: ${i.dns || 'sin configurar'}` : ''}`).join(' / ');
    label.append(node('small', interfaces || 'Sin interfaces'));
    check.addEventListener('change', () => {
      if (check.checked) selectedHosts.add(host.hostid); else selectedHosts.delete(host.hostid);
      action(async () => { await invalidate(); message('Selección actualizada. Consulta para ver las alertas.'); });
    });
    row.append(check, label); $('hosts').append(row);
  }
  updateControls();
}
function clearResults() {
  problems = []; snapshot = ''; selectedEvents.clear();
  $('stat-open').textContent = '—'; $('stat-eligible').textContent = '—'; $('query-time').textContent = 'Sin consultar';
  renderProblems();
}
async function invalidate() {
  clearResults();
  await api('/api/invalidate', {});
}
function renderProblems() {
  $('problems').replaceChildren();
  const eligible = problems.filter(p => p.eligible);
  $('eligible-count').textContent = eligible.length;
  $('all-count').textContent = problems.length;
  const rows = onlyEligible ? eligible : problems;
  $('empty-results').hidden = rows.length > 0;
  if (!rows.length) {
    $('empty-results').replaceChildren(node('span', '▤', 'empty-icon'), node('h3', snapshot ? 'Sin alertas para este filtro' : 'Prepara tu consulta'),
      node('p', snapshot ? 'Revisa la pestaña Todas y los motivos de descarte. Puedes ajustar equipos, días o los patrones F5 de configuración.' : 'Selecciona el cliente y sus equipos, luego pulsa Consultar alertas.'));
  }
  for (const problem of rows) {
    const row = node('tr'), selectCell = node('td'), check = node('input'); check.type = 'checkbox';
    check.setAttribute('aria-label', `Seleccionar evento ${problem.eventid}`);
    check.disabled = !problem.eligible || !snapshot; check.checked = selectedEvents.has(problem.eventid);
    check.addEventListener('change', () => { if (check.checked) selectedEvents.add(problem.eventid); else selectedEvents.delete(problem.eventid); updateControls(); });
    selectCell.append(check);
    const event = node('td', undefined, 'problem-name');
    event.append(node('div', `#${problem.eventid}`, 'event-id'), node('strong', problem.name), node('small', `Inicio ${new Date(problem.started).toLocaleString()} · ${problem.acknowledged ? 'Reconocido' : 'Sin reconocer'}`));
    const host = node('td', problem.hosts);
    const age = node('td'); age.append(node('strong', `${problem.days} días`), node('span', severityNames[problem.severity], problem.severity === 4 ? 'tag high' : 'tag'));
    const state = node('td'); state.append(node('span', problem.suppressed ? 'Suprimido' : problem.eligible ? 'Elegible' : 'Descartado', problem.eligible ? 'tag good' : 'tag'));
    if (!problem.eligible) state.append(node('small', problem.reason));
    row.append(selectCell, event, host, age, state); $('problems').append(row);
  }
  updateControls();
}
async function query() {
  clearResults();
  const result = await api('/api/query', {groupid: $('group').value, hostids: [...selectedHosts], days: Number($('days').value), severity: Number($('severity').value)});
  problems = result.problems; snapshot = result.snapshot;
  $('stat-open').textContent = problems.length;
  $('stat-eligible').textContent = problems.filter(p => p.eligible).length;
  $('query-time').textContent = `Consulta ${new Date(result.queried_at).toLocaleTimeString()}`;
  renderProblems();
  message(`${problems.length} problemas abiertos consultados. ${problems.filter(p => p.eligible).length} cumplen el criterio.`);
}
async function activity() {
  if (!config || activityPending) return;
  activityPending = true;
  try {
    const result = await api('/api/activity');
    $('history').replaceChildren(); $('empty-history').hidden = result.history.length > 0;
    for (const item of result.history) {
      const row = node('tr'), time = node('td');
      time.append(node('strong', new Date(item.time).toLocaleString()), node('small', item.mode));
      const event = node('td'); event.append(node('strong', item.group || '—'), node('small', item.eventid ? `#${item.eventid} · ${item.host}` : 'Consulta de alertas'));
      if (item.problem) event.append(node('small', item.problem));
      row.append(time, event, node('td', item.operation), node('td', item.result)); $('history').append(row);
    }
    $('logs').textContent = result.logs.join('\n') || 'Sin logs disponibles. Ejecuta con --debug para ver filtros y descartes.';
  } catch (error) { $('logs').textContent = `Registro no actualizado: ${error.message}`; }
  finally { activityPending = false; }
}
function review() {
  $('review-list').replaceChildren();
  for (const p of problems.filter(p => selectedEvents.has(p.eventid))) {
    const item = node('div', `#${p.eventid} · ${p.name}`, 'review-item');
    item.append(node('small', `${p.hosts} · ${p.days} días · ${severityNames[p.severity]}`)); $('review-list').append(item);
  }
  $('confirm-mode').textContent = config.dry_run ? 'SIMULACIÓN: se registrará la prueba sin modificar Zabbix.' : `REAL: ${config.remaining} intento(s) disponible(s). Se validará el estado actual de cada evento.`;
  $('confirm-mode').textContent += ` Mensaje en Zabbix: ${config.suppression_message} Plazo aplicado: ${Number($('days').value)} días.`;
  $('permissions-label').hidden = config.dry_run;
  $('permissions').value = ''; $('confirmation').value = '';
  $('apply').textContent = config.dry_run ? 'Registrar simulación' : 'Suprimir eventos';
  $('confirm-dialog').showModal(); updateControls(); $('confirmation').focus();
}

$('group-search').addEventListener('input', renderGroups);
$('group').addEventListener('change', () => action(async () => {
  selectedHosts.clear(); hosts = []; visibleHosts = []; $('ip-filter').value = ''; renderHosts(); await invalidate();
  if ($('group').value) hosts = await api(`/api/hosts?groupid=${encodeURIComponent($('group').value)}`);
  visibleHosts = [...hosts]; renderHosts(); message(hosts.length ? 'Selecciona los equipos que quieres consultar.' : 'No hay equipos visibles para este grupo.');
}));
$('filter-hosts').addEventListener('click', () => action(async () => {
  if (!$('group').value) throw new Error('Selecciona un cliente primero.');
  const result = await api('/api/filter-hosts', {groupid: $('group').value, filter: $('ip-filter').value});
  visibleHosts = hosts.filter(h => result.hostids.includes(h.hostid));
  selectedHosts = new Set(result.hostids); await invalidate(); renderHosts(); message(`${selectedHosts.size} equipos coinciden y quedaron seleccionados.`);
}));
$('clear-filter').addEventListener('click', () => { $('ip-filter').value = ''; visibleHosts = [...hosts]; renderHosts(); });
$('all-hosts').addEventListener('click', () => action(async () => { selectedHosts = new Set(visibleHosts.map(h => h.hostid)); await invalidate(); renderHosts(); message('Equipos visibles seleccionados.'); }));
$('none-hosts').addEventListener('click', () => action(async () => { selectedHosts.clear(); await invalidate(); renderHosts(); message('Selección de equipos vacía.'); }));
$('days').addEventListener('change', () => action(async () => { await invalidate(); message('Antigüedad actualizada. Vuelve a consultar.'); }));
$('severity').addEventListener('change', () => action(async () => { await invalidate(); message('Severidad actualizada. Vuelve a consultar para seleccionar alertas.'); }));
document.querySelectorAll('[data-days]').forEach(button => button.addEventListener('click', () => action(async () => { $('days').value = button.dataset.days; await invalidate(); message('Antigüedad actualizada. Vuelve a consultar.'); })));
$('query').addEventListener('click', () => action(query));
$('refresh').addEventListener('click', () => action(query));
$('eligible-tab').addEventListener('click', () => { onlyEligible = true; $('eligible-tab').classList.add('selected'); $('all-tab').classList.remove('selected'); renderProblems(); });
$('all-tab').addEventListener('click', () => { onlyEligible = false; $('all-tab').classList.add('selected'); $('eligible-tab').classList.remove('selected'); renderProblems(); });
$('all-events').addEventListener('change', () => { selectedEvents = $('all-events').checked ? new Set(problems.filter(p => p.eligible).map(p => p.eventid)) : new Set(); renderProblems(); });
$('export').addEventListener('click', () => { window.location.assign('/api/export'); });
$('review').addEventListener('click', review);
['close-dialog', 'cancel-dialog'].forEach(id => $(id).addEventListener('click', () => $('confirm-dialog').close()));
['confirmation', 'permissions'].forEach(id => $(id).addEventListener('input', updateControls));
$('confirm-dialog').addEventListener('cancel', event => { if (busy) event.preventDefault(); });
$('apply').addEventListener('click', () => action(async () => {
  const payload = {snapshot, eventids: [...selectedEvents], confirmation: $('confirmation').value, permissions: $('permissions').value};
  snapshot = ''; selectedEvents.clear();
  try {
    const result = await api('/api/suppress', payload); config = result.state; showConfig();
    message(Object.entries(result.results).map(([id, text]) => `Evento #${id}: ${text}`).join('\n') + '\nConsulta nuevamente antes de otra operación.');
  } finally { $('confirm-dialog').close(); renderProblems(); }
}));

action(async () => {
  config = await api('/api/state'); $('days').value = config.days; $('severity').value = String(config.severity); showConfig();
  groups = await api('/api/groups'); renderGroups(); renderProblems();
  message(groups.length ? 'Conexión lista. Selecciona un cliente para comenzar.' : 'No hay grupos visibles para el token configurado.');
});
setInterval(() => { if (!document.hidden && !busy) activity(); }, 5000);
