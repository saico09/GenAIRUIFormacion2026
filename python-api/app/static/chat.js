import {request, errorMessage, notice} from './api.js';

export function initChat(javaBase) {
  const patient = document.querySelector('#patient');
  const question = document.querySelector('#question');
  const submit = document.querySelector('#submit');
  const reload = document.querySelector('#reload-patients');
  const error = document.querySelector('#error');
  const loading = document.querySelector('#loading');
  const answers = document.querySelector('.answers');
  const saveStatus = document.querySelector('#chat-save-status');
  const executionLabel = document.querySelector('#chat-execution-id');
  const retrySync = document.querySelector('#retry-chat-sync');
  let busy = false;
  let loadingPatients = false;
  let pendingReload = false;
  let lastConsultation = null;
  let pendingExecution = null;

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
      patient.replaceChildren(...result.data.map(row => {
        const option = document.createElement('option');
        option.value = row.id; option.textContent = row.name; return option;
      }));
      if (!result.data.length) throw new Error('No hay pacientes registrados. Agrega uno en «Pacientes» para consultar su historia.');
      if (result.data.some(row => String(row.id) === previous)) patient.value = previous;
      submit.disabled = false;
    } catch (failure) { notice(error, failure.message); }
    finally {
      reload.disabled = false; patient.disabled = false; loadingPatients = false;
      if (pendingReload) { pendingReload = false; loadPatients(); }
    }
  }

  document.querySelector('#chat-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || loadingPatients) return;
    notice(error, '');
    const sentQuestion = question.value;
    if (!sentQuestion.trim()) { notice(error, 'Escribe una consulta'); question.focus(); return; }
    if (!patient.value) { notice(error, 'Selecciona un paciente'); return; }
    const sentPatientName = patient.selectedOptions[0].textContent;
    const sentPatientId = Number(patient.value);
    if (!pendingExecution || pendingExecution.patient_id !== sentPatientId || pendingExecution.question !== sentQuestion) {
      pendingExecution = {patient_id: sentPatientId, question: sentQuestion, id: crypto.randomUUID()};
    }
    lastConsultation = null;
    document.querySelector('#chat-record-actions').hidden = true;
    notice(saveStatus, ''); executionLabel.hidden = true; retrySync.hidden = true;
    busy = true;
    submit.disabled = patient.disabled = question.disabled = reload.disabled = true;
    loading.hidden = false;
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
    try {
      const result = await request('/chat', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Execution-ID': pendingExecution.id},
        body: JSON.stringify({patient_id: sentPatientId, question: sentQuestion})}, 420000);
      if (!result.ok) throw new Error(errorMessage(result));
      const data = result.data;
      for (const [id, text] of [['direct', data.direct_answer], ['rag', data.rag_answer]]) {
        document.getElementById(id).textContent = text;
        document.getElementById(id).classList.remove('empty-answer');
      }
      document.querySelector('#used-question').textContent = `Paciente consultado: ${sentPatientName}. Consulta enviada: ${sentQuestion}`;
      document.querySelector('#used-question').hidden = false;
      document.querySelector('#sources').replaceChildren(...data.sources.map(source => {
        const item = document.createElement('li');
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        const sourceType = source.kind === 'reported_consultation' || source.section === 'Consulta' ? 'Consulta reportada' : 'Registro confirmado';
        summary.textContent = `${source.source} / ${source.section}${source.record_id ? ` · ${sourceType} ${source.record_id}` : ''}`;
        const fragment = document.createElement('p'); fragment.className = 'source-fragment';
        fragment.textContent = source.text || 'La respuesta no incluyó el texto del fragmento.';
        details.append(summary, fragment); item.append(details); return item;
      }));
      document.querySelector('#sources-empty').hidden = data.sources.length > 0;
      lastConsultation = {patient_id: sentPatientId, note: sentQuestion, name: sentPatientName};
      document.querySelector('#chat-record-actions').hidden = false;
      if (data.consultation?.saved === true) {
        const syncPending = data.index_synced === false;
        notice(saveStatus, `Consulta guardada en el informe de ${sentPatientName} y en PostgreSQL.${syncPending ? ' Falta actualizar el índice RAG; puedes reintentarlo sin repetir la consulta.' : ''}`, syncPending ? 'warning' : 'success');
        executionLabel.textContent = `ID de la consulta: ${data.consultation.id}${data.model ? ` · Modelo: ${data.model}` : ''}`;
        executionLabel.hidden = false;
        retrySync.hidden = !syncPending;
        pendingExecution = null;
        document.dispatchEvent(new CustomEvent('clinical-history-changed', {detail: {patient_id: sentPatientId}}));
      } else {
        notice(saveStatus, 'Se recibieron las respuestas, pero la API no confirmó que se guardaran. Revisa el informe antes de repetir.', 'warning');
      }
    } catch (failure) {
      notice(error, failure.message);
      for (const id of ['direct', 'rag']) document.getElementById(id).textContent = 'No se recibió una respuesta completa. Reintenta la misma consulta sin recargar la página para conservar su ID y evitar duplicados.';
    } finally {
      busy = false;
      submit.disabled = patient.disabled = question.disabled = reload.disabled = false;
      loading.hidden = true;
      answers.setAttribute('aria-busy', 'false');
      if (pendingReload) { pendingReload = false; loadPatients(); }
    }
  });
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
      const result = await request(`/clinical/patients/${lastConsultation.patient_id}/sync`, {method: 'POST'}, 180000);
      if (!result.ok) throw new Error(errorMessage(result));
      retrySync.hidden = true;
      notice(saveStatus, `Consulta guardada en el informe de ${lastConsultation.name} y en PostgreSQL. Índice RAG actualizado.`, 'success');
    } catch (failure) {
      notice(saveStatus, `La consulta sigue guardada. No se pudo actualizar el índice RAG: ${failure.message}`, 'warning');
    } finally { busy = false; retrySync.disabled = false; submit.disabled = false; }
  });
  document.addEventListener('select-clinical-patient', async event => {
    if (busy) return;
    const selectedId = String(event.detail.patient_id);
    if (![...patient.options].some(option => option.value === selectedId)) await loadPatients();
    patient.value = selectedId;
    question.focus();
  });
  document.addEventListener('java-patients-changed', loadPatients);
  document.addEventListener('clinical-patients-changed', loadPatients);
  loadPatients();
}
