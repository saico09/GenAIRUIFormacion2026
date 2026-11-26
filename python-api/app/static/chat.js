import {request, errorMessage, notice, newId, syncIndex, indexError, indexSyncing, setIndexState} from './api.js';

// El peor caso del servidor (dos generaciones y el índice) supera los 7 minutos; «Cancelar» corta antes.
const CHAT_TIMEOUT = 900000;

function sourceItems(sources) {
  return sources.map(source => {
    const item = document.createElement('li');
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    const sourceType = source.kind === 'reported_consultation' || source.section === 'Consulta' ? 'Consulta reportada' : 'Registro confirmado';
    summary.textContent = `${source.source} / ${source.section}${source.record_id ? ` · ${sourceType} ${source.record_id}` : ''}`;
    const fragment = document.createElement('p'); fragment.className = 'source-fragment';
    fragment.textContent = source.text || 'La respuesta no incluyó el texto del fragmento.';
    details.append(summary, fragment); item.append(details); return item;
  });
}

export function initChat(javaBase) {
  const patient = document.querySelector('#patient');
  const question = document.querySelector('#question');
  const submit = document.querySelector('#submit');
  const cancel = document.querySelector('#cancel-chat');
  const reload = document.querySelector('#reload-patients');
  const error = document.querySelector('#error');
  const loading = document.querySelector('#loading');
  const announcer = document.querySelector('#chat-announcer');
  const answers = document.querySelector('.answers');
  const saveStatus = document.querySelector('#chat-save-status');
  const executionLabel = document.querySelector('#chat-execution-id');
  const retrySync = document.querySelector('#retry-chat-sync');
  let busy = false;
  let loadingPatients = false;
  let pendingReload = false;
  let lastConsultation = null;
  let pendingExecution = null;
  let controller = null;
  let focusOnShow = false;

  async function loadPatients() {
    if (busy || loadingPatients) { pendingReload = true; return; }
    loadingPatients = true;
    const previous = patient.value;
    submit.disabled = true;
    reload.disabled = true;
    patient.disabled = true;
    notice(error, '');
    try {
      const result = await request(`${javaBase}/patients`);
      if (!result.ok) throw new Error(errorMessage(result));
      // Opción fija: si el paciente elegido desaparece no se pasa a otro sin que se vea.
      const placeholder = document.createElement('option');
      placeholder.value = ''; placeholder.textContent = 'Selecciona un paciente';
      patient.replaceChildren(placeholder, ...result.data.map(row => {
        const option = document.createElement('option');
        option.value = row.id; option.textContent = row.name; return option;
      }));
      if (!result.data.length) throw new Error('No hay pacientes registrados. Agrega uno en «Pacientes» para consultar su historia.');
      const kept = result.data.some(row => String(row.id) === previous);
      patient.value = kept ? previous : '';
      if (previous && !kept) notice(error, `El paciente elegido (ID ${previous}) ya no está en el registro. Selecciona otro antes de consultar.`, 'warning');
      submit.disabled = false;
    } catch (failure) { notice(error, failure.message); }
    finally {
      reload.disabled = false; patient.disabled = false; loadingPatients = false;
      if (pendingReload) { pendingReload = false; await loadPatients(); }
    }
  }

  document.querySelector('#chat-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || loadingPatients) return;
    notice(error, '');
    const sentQuestion = question.value;
    if (!sentQuestion.trim()) { notice(error, 'Escribe una consulta'); question.focus(); return; }
    if (!patient.value) { notice(error, 'Selecciona un paciente'); patient.focus(); return; }
    const sentPatientName = patient.selectedOptions[0].textContent;
    const sentPatientId = Number(patient.value);
    // Mismo paciente y misma consulta: se reutiliza el UUID para reintentar sin duplicar.
    if (!pendingExecution || pendingExecution.patient_id !== sentPatientId || pendingExecution.question !== sentQuestion) {
      pendingExecution = {patient_id: sentPatientId, question: sentQuestion, id: newId()};
    }
    lastConsultation = null;
    document.querySelector('#chat-record-actions').hidden = true;
    notice(saveStatus, ''); executionLabel.hidden = true; retrySync.hidden = true;
    busy = true;
    submit.disabled = patient.disabled = question.disabled = reload.disabled = true;
    controller = new AbortController();
    cancel.hidden = false; cancel.disabled = false;
    loading.hidden = false;
    announcer.textContent = '';
    answers.setAttribute('aria-busy', 'true');
    // Una respuesta anterior no debe parecer el resultado de una consulta que falló.
    for (const id of ['direct', 'rag']) {
      const area = document.getElementById(id);
      area.textContent = 'Esperando la respuesta de esta consulta…';
      area.classList.add('empty-answer');
    }
    document.querySelector('#sources').replaceChildren();
    document.querySelector('#sources-empty').hidden = false;
    document.querySelector('#used-question').hidden = true;
    let cancelled = false;
    try {
      const result = await request('/chat', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Execution-ID': pendingExecution.id},
        body: JSON.stringify({patient_id: sentPatientId, question: sentQuestion}), signal: controller.signal}, CHAT_TIMEOUT);
      // Un 409 indica que ese UUID ya pertenece a otra consulta: la próxima usa uno nuevo.
      if (result.status === 409) pendingExecution = null;
      if (!result.ok) throw new Error(errorMessage(result));
      const data = result.data;
      for (const [id, text] of [['direct', data.direct_answer], ['rag', data.rag_answer]]) {
        document.getElementById(id).textContent = text;
        document.getElementById(id).classList.remove('empty-answer');
      }
      document.querySelector('#used-question').textContent = `Paciente consultado: ${sentPatientName}. Consulta enviada: ${sentQuestion}`;
      document.querySelector('#used-question').hidden = false;
      document.querySelector('#sources').replaceChildren(...sourceItems(data.sources));
      document.querySelector('#sources-empty').hidden = data.sources.length > 0;
      lastConsultation = {patient_id: sentPatientId, note: sentQuestion, name: sentPatientName};
      document.querySelector('#chat-record-actions').hidden = false;
      announcer.textContent = `Respuestas recibidas para ${sentPatientName}.`;
      if (data.consultation?.saved === true) {
        const syncPending = data.index_synced === false;
        notice(saveStatus, `Consulta guardada en el informe de ${sentPatientName} y en PostgreSQL.${syncPending ? ' Falta actualizar el índice RAG; puedes reintentarlo sin repetir la consulta.' : ''}`, syncPending ? 'warning' : 'success');
        executionLabel.textContent = `ID de la consulta: ${data.consultation.id}${data.model ? ` · Modelo: ${data.model}` : ''}`;
        executionLabel.hidden = false;
        retrySync.hidden = !syncPending;
        // /chat ya reindexó al paciente: un pendiente anterior queda resuelto.
        if (syncPending) setIndexState(sentPatientId, '');
        else if (!indexSyncing(sentPatientId)) setIndexState(sentPatientId, undefined);
        pendingExecution = null;
        document.dispatchEvent(new CustomEvent('clinical-history-changed', {detail: {patient_id: sentPatientId}}));
      } else {
        notice(saveStatus, 'Se recibieron las respuestas, pero la API no confirmó que se guardaran. Revisa el informe antes de repetir.', 'warning');
      }
    } catch (failure) {
      cancelled = failure.name === 'AbortError';
      if (cancelled) {
        notice(error, 'Consulta cancelada en el navegador. Si el servidor ya la estaba procesando puede terminar de guardarse: repite la misma consulta sin cambiarla para recuperarla con el mismo ID, sin duplicarla.', 'warning');
      } else notice(error, failure.message);
      const retryHint = pendingExecution
        ? 'Reintenta la misma consulta sin recargar la página para conservar su ID y evitar duplicados.'
        : 'Puedes enviarla de nuevo; se usará un ID nuevo.';
      for (const id of ['direct', 'rag']) {
        document.getElementById(id).textContent = `${cancelled ? 'Consulta cancelada.' : 'No se recibió una respuesta completa.'} ${retryHint}`;
      }
      announcer.textContent = cancelled ? 'Consulta cancelada.' : 'La consulta no se completó.';
    } finally {
      busy = false; controller = null; cancel.hidden = true;
      submit.disabled = patient.disabled = question.disabled = reload.disabled = false;
      loading.hidden = true;
      answers.setAttribute('aria-busy', 'false');
      if (cancelled) submit.focus();
      if (pendingReload) { pendingReload = false; await loadPatients(); }
    }
  });
  cancel.addEventListener('click', () => controller?.abort());
  reload.addEventListener('click', loadPatients);
  document.querySelector('#prepare-chat-record').addEventListener('click', () => {
    if (lastConsultation && !busy) document.dispatchEvent(new CustomEvent('prepare-clinical-record', {detail: lastConsultation}));
  });
  document.querySelector('#open-chat-history').addEventListener('click', () => {
    if (lastConsultation && !busy) document.dispatchEvent(new CustomEvent('open-clinical-history', {detail: lastConsultation}));
  });
  retrySync.addEventListener('click', async () => {
    if (!lastConsultation || busy) return;
    busy = true; retrySync.disabled = true; submit.disabled = true;
    try {
      await syncIndex(lastConsultation.patient_id);
      retrySync.hidden = true;
      notice(saveStatus, `Consulta guardada en el informe de ${lastConsultation.name} y en PostgreSQL. Índice RAG actualizado.`, 'success');
    } catch (failure) {
      notice(saveStatus, `La consulta sigue guardada. No se pudo actualizar el índice RAG: ${failure.message}`, 'warning');
    } finally {
      busy = false; retrySync.disabled = false; submit.disabled = false;
      if (pendingReload) { pendingReload = false; await loadPatients(); }
    }
  });
  document.addEventListener('index-sync-changed', event => {
    const id = event.detail.patient_id;
    if (!retrySync.hidden && lastConsultation?.patient_id === id && indexError(id) === undefined) {
      retrySync.hidden = true;
      notice(saveStatus, `Consulta guardada en el informe de ${lastConsultation.name} y en PostgreSQL. Índice RAG actualizado.`, 'success');
    }
  });
  document.addEventListener('select-clinical-patient', async event => {
    if (busy) return;
    const selectedId = String(event.detail.patient_id);
    if (![...patient.options].some(option => option.value === selectedId)) await loadPatients();
    patient.value = selectedId;
    // La vista de Consultas puede seguir oculta mientras cambia el hash: se enfoca al mostrarse.
    if (document.querySelector('#view-consultas').hidden) focusOnShow = true;
    else question.focus();
  });
  document.addEventListener('view-shown', event => {
    if (event.detail.view === 'consultas' && focusOnShow) question.focus();
    focusOnShow = false;
  });
  document.addEventListener('patients-changed', loadPatients);
  loadPatients().catch(failure => notice(error, failure.message));
}
