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
export function confirmDelete(description) {
  const dialog = document.querySelector('#confirm-dialog');
  document.querySelector('#confirm-description').textContent = description;
  dialog.returnValue = 'cancel';
  document.querySelector('#confirm-cancel').onclick = () => dialog.close('cancel');
  document.querySelector('#confirm-accept').onclick = () => dialog.close('delete');
  return new Promise(resolve => {
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'delete'), {once: true});
    dialog.showModal();
    document.querySelector('#confirm-cancel').focus();
  });
}
