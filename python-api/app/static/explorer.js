import {request, notice, confirmDelete, confirmAction} from './api.js';

const samplePatient = {name: 'Paciente de prueba', birth_date: '1990-05-15', email: 'prueba@example.com'};
const sampleDisease = {disease: 'Rinitis alérgica', treatment: 'Evitar la exposición al polen', medication: 'Cetirizina'};
const operations = [
  {method: 'GET', path: '/health', title: 'Comprobar disponibilidad'},
  {method: 'GET', path: '/patients', title: 'Listar pacientes'},
  {method: 'POST', path: '/patients', title: 'Crear un paciente', body: samplePatient},
  {method: 'GET', path: '/patients/{id}', title: 'Consultar un paciente por ID'},
  {method: 'PUT', path: '/patients/{id}', title: 'Actualizar los datos de un paciente', body: samplePatient},
  {method: 'DELETE', path: '/patients/{id}', title: 'Eliminar un paciente'},
  {method: 'GET', path: '/patients/{id}/diseases', title: 'Listar los registros confirmados de un paciente'},
  {method: 'POST', path: '/patients/{id}/diseases', title: 'Agregar enfermedad, tratamiento y medicamento', body: sampleDisease, clinicalRecord: true},
  {method: 'GET', path: '/patients/{id}/diseases/{uuid}', title: 'Consultar un registro por UUID', recordUuid: true},
  {method: 'PUT', path: '/patients/{id}/diseases/{uuid}', title: 'Editar un registro conservando su UUID', body: sampleDisease, clinicalRecord: true, recordUuid: true},
  {method: 'DELETE', path: '/patients/{id}/diseases/{uuid}', title: 'Eliminar un registro confirmado', recordUuid: true},
];

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

export function initExplorer(api, baseUrl, metricsEnabled) {
  const root = document.querySelector(`#explorer-${api}`);
  const base = node('div', 'api-base');
  base.append(node('span', 'eyebrow', 'URL BASE'), node('code', '', baseUrl));
  root.append(base, node('p', 'api-intro', 'Python y Java usan los mismos pacientes y registros. POST agrega, PUT modifica y DELETE elimina. Los cambios clínicos actualizan la tabla y el Markdown del paciente.'));
  const entries = [...operations];
  if (api === 'python') entries.push(
    {method: 'POST', path: '/chat', title: 'Comparar respuestas y guardar la consulta en el informe', timeout: 420000,
      body: {patient_id: 1, question: '¿Qué enfermedad tiene Ana Demo?'}},
    {method: 'POST', path: '/clinical/proposals', title: 'Preparar un borrador clínico sin guardarlo', timeout: 420000,
      body: {patient_id: 1, note: 'Enfermedad: Enfermedad ficticia de prueba. Tratamiento: Tratamiento ficticio de prueba.'}},
    {method: 'POST', path: '/clinical/patients/{id}/sync', title: 'Actualizar o retirar el índice RAG del paciente', timeout: 180000},
  );
  else entries.push(
    {method: 'GET', path: '/patients/{id}/history', title: 'Leer informe, registros y revisión vigente'},
    {method: 'GET', path: '/patients/{id}/history.md', title: 'Leer el archivo Markdown'},
    {method: 'GET', path: '/patients/{id}/consultations/{uuid}', title: 'Consultar una ejecución guardada por UUID'},
    {method: 'POST', path: '/patients/{id}/consultations', title: 'Guardar una comparación en el informe', confirmHistory: true,
      body: {id: crypto.randomUUID(), question: 'Consulta ficticia de prueba', direct_answer: 'Respuesta directa ficticia',
        rag_answer: 'Respuesta contextual ficticia', model: 'prueba-manual', sources: []}},
    {method: 'PUT', path: '/patients/{id}/history', title: 'Reemplazar el Markdown con revisión y confirmación', confirmHistory: true,
      body: {revision: 'COPIA_LA_REVISION_DEL_GET', markdown: 'PEGA_EL_MARKDOWN_DEL_GET_Y_EDITA_SUS_CAMPOS', confirmed: true}},
    {method: 'POST', path: '/patients/{id}/history/entries', title: 'Añadir un registro con UUID asignado por Java', confirmHistory: true,
      body: {revision: 'COPIA_LA_REVISION_DEL_GET', disease: 'Enfermedad ficticia de prueba', treatment: '', medication: '', confirmed: true}},
  );
  if (metricsEnabled) {
    if (api === 'java') entries.push({method: 'GET', path: '/actuator/health', title: 'Consultar salud del servicio'});
    entries.push({method: 'GET', path: api === 'java' ? '/actuator/prometheus' : '/metrics', title: 'Consultar métricas Prometheus'});
  }
  entries.forEach((operation, index) => root.append(endpoint(api, baseUrl, operation, index)));
}

function endpoint(api, base, operation, index) {
  const {method, path, title} = operation;
  const prefix = `${api}-endpoint-${index}`;
  const details = node('details', 'endpoint');
  details.dataset.method = method; details.dataset.path = path;
  const summary = node('summary');
  summary.append(node('span', `method ${method.toLowerCase()}`, method), node('span', 'endpoint-path', path), node('span', 'endpoint-description', title));
  details.append(summary);
  const content = node('div', 'endpoint-body');
  const columns = node('div', 'endpoint-columns');
  const form = node('form', 'endpoint-form');
  const requestTitle = node('h3', '', 'Petición');
  const urlDisplay = node('code', 'endpoint-url', `${base}${path}`);
  form.append(requestTitle, urlDisplay);
  let idInput = null;
  let uuidInput = null;
  function resolvedPath() {
    return path.replace('{id}', idInput?.value || '{id}').replace('{uuid}', uuidInput?.value || '{uuid}');
  }
  if (path.includes('{id}')) {
    const label = node('label', '', 'ID del paciente'); label.htmlFor = `${prefix}-id`;
    idInput = node('input', 'id-input');
    idInput.id = label.htmlFor; idInput.name = 'id'; idInput.type = 'number'; idInput.min = '1'; idInput.step = '1'; idInput.required = true;
    idInput.placeholder = 'Indica un ID';
    idInput.addEventListener('input', () => { urlDisplay.textContent = `${base}${resolvedPath()}`; });
    form.append(label, idInput);
  }
  if (path.includes('{uuid}')) {
    const label = node('label', '', operation.recordUuid ? 'UUID del registro confirmado' : 'UUID de la consulta'); label.htmlFor = `${prefix}-uuid`;
    uuidInput = node('input'); uuidInput.id = label.htmlFor; uuidInput.name = 'uuid'; uuidInput.required = true;
    uuidInput.placeholder = operation.recordUuid ? 'Copia el ID de GET diseases' : 'Copia el ID de una consulta guardada';
    uuidInput.addEventListener('input', () => { urlDisplay.textContent = `${base}${resolvedPath()}`; });
    form.append(label, uuidInput);
  }
  let bodyInput = null;
  if (operation.body) {
    const label = node('label', '', 'Cuerpo JSON'); label.htmlFor = `${prefix}-body`;
    bodyInput = node('textarea'); bodyInput.id = label.htmlFor; bodyInput.name = 'body'; bodyInput.spellcheck = false;
    bodyInput.value = JSON.stringify(operation.body, null, 2); bodyInput.required = true;
    form.append(label, bodyInput);
    if (operation.clinicalRecord) form.append(node('p', 'helper', 'Ejemplo de formación. Completa al menos un campo; deja vacío lo que no sepas. El ID une los tres campos y se asigna al crear el registro.'));
    if (operation.confirmHistory) form.append(node('p', 'helper', path.endsWith('/consultations')
      ? 'Guarda estos textos como una consulta, sin ejecutar un modelo. Reutiliza el mismo UUID sólo para reintentar el mismo contenido. Confirmarás antes de enviar.'
      : 'Copia la revisión de GET history. Para editar Markdown conserva los UUID existentes y el historial de consultas. Las altas usan POST entries. Confirmarás antes de enviar.'));
  } else form.append(node('p', 'helper', 'Esta operación no necesita un cuerpo JSON.'));
  const run = node('button', 'button primary', 'Ejecutar petición'); run.type = 'submit';
  const formNotice = node('p', 'notice error'); formNotice.hidden = true; formNotice.setAttribute('role', 'alert');
  const retrySync = node('button', 'button secondary', 'Reintentar sincronización'); retrySync.type = 'button'; retrySync.hidden = true;
  form.append(run, formNotice, retrySync);
  const response = node('div', 'endpoint-response'); response.setAttribute('aria-live', 'polite');
  const responseHeading = node('div', 'response-heading');
  const status = node('span', 'http-status'); status.hidden = true;
  const duration = node('span', 'helper');
  responseHeading.append(node('h3', '', 'Respuesta'), status, duration);
  const output = node('pre', 'response-body', 'Ejecuta una petición para ver su respuesta.');
  const metadata = node('p', 'response-meta');
  response.append(responseHeading, output, metadata); columns.append(form, response); content.append(columns); details.append(content);
  let busy = false;
  let pendingSyncId = null;
  async function synchronize() {
    try {
      const result = await request(`/clinical/patients/${pendingSyncId}/sync`, {method: 'POST'}, 180000);
      if (!result.ok) throw new Error('No se pudo actualizar el índice RAG.');
      pendingSyncId = null; retrySync.hidden = true; notice(formNotice, 'Índice RAG sincronizado.', 'success');
    } catch (error) {
      notice(formNotice, `El cambio está guardado, pero el índice del paciente ${pendingSyncId} sigue pendiente. Reintentar no repite ${method}. ${error.message}`, 'warning');
      retrySync.hidden = false;
    }
  }
  retrySync.addEventListener('click', async () => {
    if (busy || pendingSyncId === null) return;
    busy = true; run.disabled = true; retrySync.disabled = true;
    try { await synchronize(); }
    finally { busy = false; run.disabled = pendingSyncId !== null; retrySync.disabled = false; }
  });
  function clearResponse() {
    status.hidden = true; duration.textContent = ''; metadata.textContent = '';
    output.textContent = 'Ejecuta esta petición para ver su respuesta.';
  }
  // Una respuesta anterior no debe parecer el resultado del cuerpo o ID recién editado.
  for (const input of [bodyInput, idInput, uuidInput].filter(Boolean)) input.addEventListener('input', clearResponse);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || pendingSyncId !== null) return;
    notice(formNotice, '');
    clearResponse();
    if (bodyInput) {
      try { JSON.parse(bodyInput.value); } catch { notice(formNotice, 'El cuerpo no es JSON válido. Revisa las comillas y las comas.'); bodyInput.focus(); return; }
    }
    if (idInput && (!Number.isSafeInteger(Number(idInput.value)) || Number(idInput.value) < 1)) {
      notice(formNotice, 'El ID debe ser un número entero positivo.'); return;
    }
    if (uuidInput && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(uuidInput.value)) {
      notice(formNotice, 'El identificador debe tener formato UUID.'); return;
    }
    const endpointPath = resolvedPath();
    if (method === 'DELETE') {
      const description = `¿Quieres ejecutar DELETE ${endpointPath} en la API ${api === 'java' ? 'Java' : 'Python'}?`;
      const accepted = operation.recordUuid
        ? await confirmAction(description, {title: 'Eliminar registro', label: 'Eliminar registro', danger: true, hint: 'Sólo se elimina este registro confirmado. El paciente y las consultas guardadas se conservan.'})
        : await confirmDelete(description);
      if (!accepted) return;
    }
    if (operation.confirmHistory && !await confirmAction(`¿Enviar ${method} ${endpointPath} y guardar estos cambios en la historia clínica?`,
      {title: 'Guardar historia clínica', label: 'Confirmar y enviar', hint: 'Revisa el JSON, los datos y la revisión vigente. Esta operación modifica el informe del paciente.'})) return;
    if (operation.clinicalRecord && !await confirmAction(`¿Guardar estos datos en el registro de ${endpointPath}?`,
      {title: 'Guardar registro confirmado', label: 'Confirmar y enviar', hint: 'Revisa los tres campos del JSON. El cambio se reflejará en el Markdown.'})) return;
    busy = true; run.disabled = true; run.textContent = 'Ejecutando…';
    if (bodyInput) bodyInput.disabled = true;
    if (idInput) idInput.disabled = true;
    if (uuidInput) uuidInput.disabled = true;
    status.hidden = true; duration.textContent = ''; metadata.textContent = '';
    output.textContent = 'Esperando respuesta…'; response.setAttribute('aria-busy', 'true');
    try {
      const options = {method};
      if (bodyInput) { options.headers = {'Content-Type': 'application/json'}; options.body = bodyInput.value; }
      const result = await request(`${base}${endpointPath}`, options, operation.timeout || 20000);
      const state = result.status >= 500 ? 'server-error' : result.status >= 400 ? 'client-error' : 'ok';
      const description = result.status >= 500 ? 'Error del servidor' : result.status >= 400 ? 'Petición rechazada' : 'Correcto';
      status.className = `http-status ${state}`; status.textContent = `${result.status} · ${description}`; status.hidden = false;
      duration.textContent = `${result.duration} ms`;
      output.textContent = result.status === 204 ? 'Sin contenido (204). El registro fue eliminado.'
        : result.data !== null ? JSON.stringify(result.data, null, 2) : result.text || '(Respuesta vacía)';
      metadata.textContent = [result.contentType, result.requestId && `Request ID: ${result.requestId}`, result.executionId && `Ejecución: ${result.executionId}`].filter(Boolean).join(' · ');
      if (result.ok && path.startsWith('/patients') && method !== 'GET') {
        document.dispatchEvent(new Event('patients-changed'));
        const patientId = Number(idInput?.value || result.data?.id);
        document.dispatchEvent(new CustomEvent('clinical-history-changed', {detail: {patient_id: patientId}}));
        if (Number.isSafeInteger(patientId) && patientId > 0) {
          pendingSyncId = patientId;
          await synchronize();
        }
      }
    } catch (error) {
      status.className = 'http-status network-error'; status.textContent = 'Error de conexión'; status.hidden = false;
      output.textContent = error.message;
    } finally {
      busy = false; run.disabled = pendingSyncId !== null; run.textContent = 'Ejecutar petición';
      if (bodyInput) bodyInput.disabled = false;
      if (idInput) idInput.disabled = false;
      if (uuidInput) uuidInput.disabled = false;
      response.setAttribute('aria-busy', 'false');
    }
  });
  return details;
}
