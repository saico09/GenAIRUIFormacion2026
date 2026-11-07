import {request, errorMessage, notice} from './api.js';

export function initChat() {
  const patient = document.querySelector('#patient');
  const question = document.querySelector('#question');
  const submit = document.querySelector('#submit');
  const reload = document.querySelector('#reload-patients');
  const error = document.querySelector('#error');
  const loading = document.querySelector('#loading');
  const answers = document.querySelector('.answers');
  let busy = false;

  async function loadPatients() {
    if (busy) return;
    const previous = patient.value;
    submit.disabled = true;
    reload.disabled = true;
    patient.disabled = true;
    notice(error, '');
    try {
      const result = await request('/patients');
      if (!result.ok) throw new Error(errorMessage(result));
      patient.replaceChildren(...result.data.map(row => {
        const option = document.createElement('option');
        option.value = row.id; option.textContent = row.name; return option;
      }));
      if (!result.data.length) throw new Error('No hay pacientes en la API Python para consultar.');
      if (result.data.some(row => String(row.id) === previous)) patient.value = previous;
      submit.disabled = false;
    } catch (failure) { notice(error, failure.message); }
    finally { reload.disabled = false; patient.disabled = false; }
  }

  document.querySelector('#chat-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    notice(error, '');
    const sentQuestion = question.value;
    if (!sentQuestion.trim()) { notice(error, 'Escribe una pregunta'); question.focus(); return; }
    if (!patient.value) { notice(error, 'Selecciona un paciente'); return; }
    const sentPatientName = patient.selectedOptions[0].textContent;
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
      const result = await request('/chat', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({patient_id: Number(patient.value), question: sentQuestion})}, 420000);
      if (!result.ok) throw new Error(errorMessage(result));
      const data = result.data;
      for (const [id, text] of [['direct', data.direct_answer], ['rag', data.rag_answer]]) {
        document.getElementById(id).textContent = text;
        document.getElementById(id).classList.remove('empty-answer');
      }
      document.querySelector('#used-question').textContent = `Paciente consultado: ${sentPatientName}. Pregunta enviada: ${sentQuestion}`;
      document.querySelector('#used-question').hidden = false;
      document.querySelector('#sources').replaceChildren(...data.sources.map(source => {
        const item = document.createElement('li');
        item.textContent = `${source.source} / ${source.section}`; return item;
      }));
      document.querySelector('#sources-empty').hidden = data.sources.length > 0;
    } catch (failure) {
      notice(error, failure.message);
      for (const id of ['direct', 'rag']) document.getElementById(id).textContent = 'No se obtuvo una respuesta. Puedes volver a consultar.';
    } finally {
      busy = false;
      submit.disabled = patient.disabled = question.disabled = reload.disabled = false;
      loading.hidden = true;
      answers.setAttribute('aria-busy', 'false');
    }
  });
  reload.addEventListener('click', loadPatients);
  document.addEventListener('python-patients-changed', loadPatients);
  loadPatients();
}
