// Utilidades compartidas. Los cuerpos y errores se pintan siempre como texto.

function apiName(url) {
  const target = new URL(url, location.href);
  return target.origin === location.origin ? 'Python' : 'Java';
}

export async function request(url, options = {}, timeout = 20000) {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeout);
  const cancel = () => controller.abort();
  if (options.signal?.aborted) cancel();
  options.signal?.addEventListener('abort', cancel, {once: true});
  const start = performance.now();
  const api = apiName(url);
  try {
    const response = await fetch(url, {...options, signal: controller.signal});
    const text = await response.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { /* Métricas: texto, no JSON. */ }
    return {ok: response.ok, status: response.status, text, data, api,
      duration: Math.round(performance.now() - start),
      requestId: response.headers.get('x-request-id'),
      executionId: response.headers.get('x-execution-id'),
      contentType: response.headers.get('content-type')};
  } catch (error) {
    if (error.name === 'AbortError' && !timedOut) {
      const cancelled = new Error('Petición cancelada.'); cancelled.name = 'AbortError'; throw cancelled;
    }
    // El navegador no distingue un servicio apagado de un rechazo CORS: se nombran ambos.
    throw new Error(timedOut
      ? `La API ${api} no respondió dentro del plazo. Puedes volver a intentarlo.`
      : `No se pudo conectar con la API ${api}. Comprueba que el servicio esté iniciado y que acepte este origen (CORS), y vuelve a intentarlo.`);
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', cancel);
  }
}

const FIELD_LABELS = {name: 'Nombre', birth_date: 'Fecha de nacimiento', email: 'Correo', disease: 'Enfermedad',
  treatment: 'Tratamiento', medication: 'Medicamento', question: 'Consulta', note: 'Nota', patient_id: 'ID del paciente'};

export function errorMessage(result) {
  const detail = result.data?.detail;
  if (typeof detail === 'string' && detail) {
    return detail.replace(/^([a-z_]+): /, (prefix, field) => FIELD_LABELS[field] ? `${FIELD_LABELS[field]}: ` : prefix);
  }
  if (Array.isArray(detail)) return detail.map(item => {
    const field = item.field || item.loc?.slice(1).join('.') || 'Dato';
    return `${FIELD_LABELS[field] || field}: ${item.message || item.msg || 'Valor inválido'}`;
  }).join(' · ');
  const api = result.api ? `La API ${result.api}` : 'La API';
  if (result.status >= 500) return `${api} tuvo un error interno (HTTP ${result.status}). Reintenta en unos segundos; si se repite, revisa sus logs.`;
  if (result.status === 413) return `${api} rechazó el contenido por superar el tamaño permitido (HTTP 413).`;
  return `${api} respondió HTTP ${result.status}. Revisa los datos enviados.`;
}

export function notice(element, message, tone = 'error') {
  element.className = `notice ${tone}`;
  element.textContent = message;
  element.hidden = !message;
}

// crypto.randomUUID sólo existe en contextos seguros; por IP de la red se usa getRandomValues.
export function newId() {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40; bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map(byte => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

// Estado del índice RAG por paciente: ausente = al día; '' = pendiente sin error conocido; texto = último error.
const indexPending = new Map();
const indexRuns = new Map();

export function indexError(patientId) { return indexPending.get(Number(patientId)); }

export function indexSyncing(patientId) { return indexRuns.has(Number(patientId)); }

export function setIndexState(patientId, error) {
  const id = Number(patientId);
  if (error === undefined) indexPending.delete(id); else indexPending.set(id, error);
  document.dispatchEvent(new CustomEvent('index-sync-changed', {detail: {patient_id: id}}));
}

// Las sincronizaciones de un mismo paciente se encadenan: la última refleja el último cambio.
export function syncIndex(patientId) {
  const id = Number(patientId);
  const run = (indexRuns.get(id) || Promise.resolve()).catch(() => {}).then(async () => {
    try {
      const result = await request(`/clinical/patients/${id}/sync`, {method: 'POST'}, 180000);
      if (!result.ok) throw new Error(errorMessage(result));
      indexPending.delete(id);
      return result;
    } catch (error) {
      indexPending.set(id, error.message);
      throw error;
    } finally {
      if (indexRuns.get(id) === run) indexRuns.delete(id);
      document.dispatchEvent(new CustomEvent('index-sync-changed', {detail: {patient_id: id}}));
    }
  });
  // Se registra antes del aviso para que la vista lo vea «en curso» y no «pendiente».
  indexRuns.set(id, run);
  setIndexState(id, indexPending.get(id) || '');
  return run;
}

// <dialog> mantiene el foco y permite cancelar con Escape sin enviar DELETE.
export function confirmAction(description, {title = 'Confirmar cambios', label = 'Confirmar', danger = false, hint = ''} = {}) {
  const dialog = document.querySelector('#confirm-dialog');
  if (dialog.open) return Promise.resolve(false);
  document.querySelector('#confirm-title').textContent = title;
  document.querySelector('#confirm-description').textContent = description;
  document.querySelector('#confirm-hint').textContent = hint;
  const accept = document.querySelector('#confirm-accept');
  accept.textContent = label;
  accept.className = `button ${danger ? 'danger' : 'primary'}`;
  dialog.returnValue = 'cancel';
  document.querySelector('#confirm-cancel').onclick = () => dialog.close('cancel');
  accept.onclick = () => dialog.close('accept');
  return new Promise(resolve => {
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'accept'), {once: true});
    dialog.showModal();
    document.querySelector('#confirm-cancel').focus();
  });
}

export function confirmDelete(description) {
  return confirmAction(description, {title: 'Eliminar paciente', label: 'Eliminar', danger: true,
    hint: 'Se elimina el paciente, sus registros confirmados y su archivo clínico activo. Los respaldos SQL y el historial de transacciones se conservan.'});
}
