// Utilidades compartidas. Los cuerpos y errores se pintan siempre como texto.
export async function request(url, options = {}, timeout = 20000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const start = performance.now();
  try {
    const response = await fetch(url, {...options, signal: controller.signal});
    const text = await response.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { /* Métricas: texto, no JSON. */ }
    return {ok: response.ok, status: response.status, text, data,
      duration: Math.round(performance.now() - start),
      requestId: response.headers.get('x-request-id'),
      executionId: response.headers.get('x-execution-id'),
      contentType: response.headers.get('content-type')};
  } catch (error) {
    throw new Error(error.name === 'AbortError'
      ? 'La petición agotó el tiempo de espera. Puedes volver a intentarlo.'
      : 'No se pudo conectar con la API. Comprueba que el servicio esté iniciado y vuelve a intentarlo.');
  } finally { clearTimeout(timer); }
}

export function errorMessage(result) {
  const detail = result.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => {
    const field = item.field || item.loc?.slice(1).join('.') || 'Dato';
    return `${field}: ${item.message || item.msg || 'Valor inválido'}`;
  }).join(' · ');
  return `La API respondió HTTP ${result.status}. Revisa los datos enviados.`;
}

export function notice(element, message, tone = 'error') {
  element.className = `notice ${tone}`;
  element.textContent = message;
  element.hidden = !message;
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
