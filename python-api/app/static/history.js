import {request, errorMessage, notice, confirmAction} from './api.js';

const fields = {disease: 'Enfermedad', treatment: 'Tratamiento', medication: 'Medicamento'};
const jsonOptions = (method, data) => ({method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});

export function initHistory(javaBase, onChanged) {
  const detail = document.querySelector('#patient-detail');
  const list = document.querySelector('#patient-list');
  const message = document.querySelector('#history-notice');
  const editor = document.querySelector('#consultation-editor');
  const note = document.querySelector('#consultation-note');
  note.maxLength = 6000;
  const proposals = document.querySelector('#proposed-entries');
  const proposalNotice = document.querySelector('#proposal-notice');
  const markdownForm = document.querySelector('#history-markdown-form');
  const markdownInput = document.querySelector('#history-markdown-input');
  const diseaseForm = document.querySelector('#disease-form');
  const diseaseNotice = document.querySelector('#disease-form-notice');
  const pendingSync = new Set();
  let patient = null;
  let history = null;
  let busy = false;
  let conflict = false;
  let nextDraft = 0;
  let editingDiseaseId = null;
  let markdownRevision = null;

  function updateControls() {
    detail.setAttribute('aria-busy', String(busy));
    detail.querySelectorAll('button, textarea').forEach(control => {
      control.disabled = busy || (!history && !['history-back', 'refresh-history'].includes(control.id));
    });
    if (conflict) detail.querySelectorAll('[data-save-entry], #save-markdown, #save-disease').forEach(button => { button.disabled = true; });
  }

  function syncStatus() {
    const pending = pendingSync.has(patient?.id);
    document.querySelector('#history-sync').hidden = !pending;
    if (pending) notice(document.querySelector('#history-sync-message'), 'La historia está guardada, pero su índice RAG sigue pendiente. Puedes reintentar la sincronización.', 'warning');
  }

  function renderHistory(data) {
    history = data;
    document.querySelector('#history-body').replaceChildren(...data.entries.map(entry => {
      const row = document.createElement('tr');
      row.dataset.diseaseId = entry.id;
      for (const value of [entry.id, ...Object.keys(fields).map(key => entry[key])]) {
        const cell = document.createElement('td'); cell.textContent = value || '—'; row.append(cell);
      }
      const cell = document.createElement('td');
      const actions = document.createElement('div'); actions.className = 'row-actions';
      for (const [action, label] of [['edit', 'Editar'], ['delete', 'Eliminar']]) {
        const button = document.createElement('button'); button.type = 'button'; button.className = `${action}-action`;
        button.dataset.diseaseAction = action; button.textContent = label;
        button.setAttribute('aria-label', `${label} registro ${entry.id}`);
        button.addEventListener('click', () => action === 'edit' ? openDiseaseForm(entry) : deleteDisease(entry));
        actions.append(button);
      }
      cell.append(actions); row.append(cell);
      return row;
    }));
    document.querySelector('#history-count').textContent = data.entries.length;
    document.querySelector('#history-empty').hidden = data.entries.length > 0;
    document.querySelector('#history-markdown-text').textContent = data.markdown;
    document.querySelector('#history-filename').textContent = data.filename;
    const consultations = [...(data.consultations || [])].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
    document.querySelector('#consultations-count').textContent = consultations.length;
    document.querySelector('#consultations-empty').hidden = consultations.length > 0;
    document.querySelector('#consultations-body').replaceChildren(...consultations.map(consultation => {
      const row = document.createElement('tr');
      const dateCell = document.createElement('td');
      const date = new Date(consultation.created_at);
      const time = document.createElement('time');
      if (Number.isNaN(date.getTime())) time.textContent = 'Fecha no disponible';
      else {
        time.dateTime = date.toISOString();
        time.textContent = date.toLocaleString('es-CL', {dateStyle: 'short', timeStyle: 'short'});
        time.title = date.toISOString();
      }
      dateCell.append(time);
      const content = document.createElement('td');
      const question = document.createElement('p'); question.className = 'consultation-question'; question.textContent = consultation.question;
      const identifier = document.createElement('p'); identifier.className = 'helper execution-id'; identifier.textContent = `ID: ${consultation.id}`;
      const details = document.createElement('details'); details.className = 'saved-consultation';
      const summary = document.createElement('summary'); summary.textContent = 'Ver las dos respuestas'; details.append(summary);
      if (consultation.model) {
        const model = document.createElement('p'); model.className = 'helper'; model.textContent = `Modelo: ${consultation.model}`; details.append(model);
      }
      for (const [title, answer] of [['Sin RAG', consultation.direct_answer], ['Con RAG', consultation.rag_answer]]) {
        const heading = document.createElement('h3'); heading.textContent = title;
        const text = document.createElement('p'); text.className = 'saved-answer'; text.textContent = answer || 'Sin respuesta registrada.';
        details.append(heading, text);
      }
      content.append(question, identifier, details); row.append(dateCell, content); return row;
    }));
    syncStatus();
  }

  async function readHistory() {
    const [report, records] = await Promise.all([
      request(`${javaBase}/patients/${patient.id}/history`),
      request(`${javaBase}/patients/${patient.id}/diseases`),
    ]);
    if (!report.ok) throw new Error(errorMessage(report));
    if (!records.ok) throw new Error(errorMessage(records));
    renderHistory({...report.data, entries: records.data});
  }

  async function loadHistory() {
    if (busy || !patient) return;
    busy = true; updateControls(); notice(message, 'Cargando historia…', 'loading');
    try {
      await readHistory();
      const hadConflict = conflict;
      conflict = false;
      if (hadConflict && !markdownForm.hidden) markdownRevision = history.revision;
      notice(message, hadConflict ? 'Historia actualizada. Conservamos tu borrador: compáralo con el archivo actual antes de confirmar de nuevo.' : '', 'warning');
    } catch (error) { notice(message, error.message); }
    finally { busy = false; updateControls(); }
  }

  async function synchronize() {
    pendingSync.add(patient.id); syncStatus();
    try {
      const result = await request(`/clinical/patients/${patient.id}/sync`, {method: 'POST'}, 180000);
      if (!result.ok) throw new Error(errorMessage(result));
      pendingSync.delete(patient.id); syncStatus();
      notice(message, 'Historia guardada y disponible para las consultas RAG.', 'success');
    } catch (error) {
      notice(message, 'La historia está guardada; su sincronización quedó pendiente.', 'warning');
      notice(document.querySelector('#history-sync-message'), `La historia está guardada, pero falta actualizar su índice RAG. ${error.message}`, 'warning');
    }
  }

  async function saveHistory(method, path, data, description, afterSave) {
    if (busy || !history || conflict) return;
    busy = true; updateControls();
    let saved = false;
    try {
      if (!await confirmAction(description, {title: 'Guardar en la historia', label: 'Confirmar y guardar', hint: 'Revisa los datos antes de confirmar. Esto modifica el archivo clínico del paciente.'})) return;
      notice(message, 'Guardando historia…', 'loading');
      const result = await request(`${javaBase}/patients/${patient.id}/history${path}`, jsonOptions(method, {revision: history.revision, ...data, confirmed: true}));
      if (result.status === 409) {
        conflict = true;
        throw new Error('Otra operación cambió la historia. Pulsa «Actualizar historia» y revisa tu borrador antes de volver a guardar.');
      }
      if (!result.ok) throw new Error(errorMessage(result));
      saved = true;
      afterSave();
      await readHistory();
      document.querySelector('#history-patient-name').focus({preventScroll: true});
      notice(message, 'Historia guardada. Actualizando el índice RAG…', 'loading');
      await onChanged();
      await synchronize();
    } catch (error) {
      if (saved) savedReadFailed(error);
      else notice(message, error.message);
    }
    finally { busy = false; updateControls(); }
  }

  function savedReadFailed(error) {
    conflict = true;
    pendingSync.add(patient.id); syncStatus();
    notice(message, `El cambio quedó guardado, pero no se pudo actualizar la vista. Pulsa «Actualizar historia». ${error.message}`, 'warning');
  }

  function openDiseaseForm(entry = null) {
    if (busy || !history) return;
    editingDiseaseId = entry?.id ?? null;
    diseaseForm.reset(); notice(diseaseNotice, '');
    document.querySelector('#disease-form-title').textContent = entry ? 'Editar registro confirmado' : 'Agregar registro confirmado';
    document.querySelector('#disease-record-id').textContent = entry ? `ID: ${entry.id}` : 'El ID se asigna al guardar.';
    for (const key of Object.keys(fields)) diseaseForm.elements.namedItem(key).value = entry?.[key] || '';
    diseaseForm.hidden = false;
    diseaseForm.elements.namedItem('disease').focus();
    diseaseForm.scrollIntoView({behavior: 'smooth', block: 'center'});
  }

  async function saveDisease(method, id, data, description, afterSave = () => {}) {
    if (busy || !history || conflict) return;
    busy = true; updateControls();
    let saved = false;
    try {
      if (!await confirmAction(description, {title: method === 'DELETE' ? 'Eliminar registro' : 'Guardar registro',
        label: method === 'DELETE' ? 'Eliminar registro' : 'Confirmar y guardar', danger: method === 'DELETE',
        hint: 'El cambio se reflejará en la tabla y en el Markdown de este paciente.'})) return;
      notice(message, 'Guardando registro…', 'loading');
      const result = await request(`${javaBase}/patients/${patient.id}/diseases${id ? `/${id}` : ''}`,
        data ? jsonOptions(method, data) : {method});
      if (!result.ok) throw new Error(errorMessage(result));
      saved = true;
      afterSave();
      // Una lectura fallida no debe dejar el formulario listo para repetir un alta ya guardada.
      await readHistory();
      document.querySelector('#history-patient-name').focus({preventScroll: true});
      await onChanged();
      await synchronize();
    } catch (error) {
      if (saved) savedReadFailed(error);
      else notice(message, error.message);
    } finally { busy = false; updateControls(); }
  }

  function deleteDisease(entry) {
    return saveDisease('DELETE', entry.id, null,
      `¿Eliminar el registro ${entry.id} de ${patient.name}?\n\n${entry.disease || 'Sin enfermedad indicada'}\n\nLas consultas guardadas se conservan.`,
      () => { if (editingDiseaseId === entry.id) diseaseForm.hidden = true; });
  }

  function addDraft(entry = {}) {
    const id = ++nextDraft;
    const form = document.createElement('form'); form.className = 'entry-draft';
    const heading = document.createElement('h3'); heading.textContent = 'Propuesta para revisar'; form.append(heading);
    const columns = document.createElement('div'); columns.className = 'entry-fields';
    for (const [key, labelText] of Object.entries(fields)) {
      const group = document.createElement('div');
      const label = document.createElement('label'); label.htmlFor = `draft-${id}-${key}`; label.textContent = labelText;
      const input = document.createElement('textarea'); input.id = label.htmlFor; input.name = key; input.rows = 2; input.maxLength = 2000; input.value = typeof entry[key] === 'string' ? entry[key] : '';
      group.append(label, input);
      const evidence = document.createElement('p'); evidence.className = 'field-evidence';
      const quote = entry.evidence?.[key];
      evidence.textContent = `Texto de la nota: ${typeof quote === 'string' && quote ? quote : Array.isArray(quote) && quote.length ? quote.join(' · ') : 'No identificado; se deja vacío.'}`;
      group.append(evidence); columns.append(group);
    }
    const localError = document.createElement('p'); localError.className = 'notice error'; localError.hidden = true; localError.setAttribute('role', 'alert');
    const actions = document.createElement('div'); actions.className = 'dialog-actions';
    const discard = document.createElement('button'); discard.type = 'button'; discard.className = 'button secondary'; discard.textContent = 'Descartar'; discard.addEventListener('click', () => form.remove());
    const save = document.createElement('button'); save.type = 'submit'; save.className = 'button primary'; save.dataset.saveEntry = ''; save.textContent = 'Guardar este registro';
    actions.append(discard, save); form.append(columns, localError, actions);
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (busy) return;
      const data = Object.fromEntries(Object.keys(fields).map(key => [key, form.elements.namedItem(key).value.trim()]));
      notice(localError, '');
      if (!Object.values(data).some(Boolean)) { notice(localError, 'Completa al menos un campo con un hecho de la consulta.'); return; }
      if (history.entries.length >= 50) { notice(localError, 'La historia ya tiene 50 registros. Revisa su Markdown antes de añadir otro.'); return; }
      const summary = Object.entries(fields).map(([key, label]) => `${label}: ${data[key] || '(sin información)'}`).join('\n');
      await saveDisease('POST', null, data, `¿Guardar este registro para ${patient.name}?\n\n${summary}`, () => {
        form.remove();
        notice(proposalNotice, proposals.children.length ? 'Registro guardado. Quedan propuestas por revisar.' : 'Registro guardado. No quedan propuestas pendientes.', 'success');
      });
    });
    proposals.append(form); updateControls();
  }

  function showConsultation(draft = '') {
    editor.hidden = false; note.value = draft; proposals.replaceChildren(); notice(proposalNotice, '');
    note.focus(); editor.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  async function open(row, draft = null) {
    if (busy) return false;
    patient = row; history = null; conflict = false;
    list.hidden = true; detail.hidden = false; editor.hidden = true; markdownForm.hidden = true; diseaseForm.hidden = true;
    document.querySelector('#history-markdown').open = false;
    document.querySelector('#history-body').replaceChildren();
    document.querySelector('#history-markdown-text').textContent = '';
    document.querySelector('#history-count').textContent = '—';
    document.querySelector('#history-filename').textContent = '';
    document.querySelector('#history-empty').hidden = true;
    document.querySelector('#consultations-body').replaceChildren();
    document.querySelector('#consultations-count').textContent = '—';
    document.querySelector('#consultations-empty').hidden = true;
    document.querySelector('#history-patient-name').textContent = row.name;
    document.querySelector('#history-patient-info').textContent = `Paciente #${row.id} · ${row.email || ''}`;
    document.querySelector('#history-patient-name').focus(); syncStatus();
    await loadHistory();
    if (draft !== null && history) showConsultation(draft);
    return true;
  }

  document.querySelector('#history-back').addEventListener('click', () => {
    if (busy) return;
    detail.hidden = true; list.hidden = false;
    list.querySelector(`[data-patient-id="${patient.id}"] [data-action="history"]`)?.focus();
  });
  document.querySelector('#refresh-history').addEventListener('click', loadHistory);
  document.querySelector('#new-consultation').addEventListener('click', () => showConsultation());
  document.querySelector('#new-disease').addEventListener('click', () => openDiseaseForm());
  document.querySelector('#cancel-disease').addEventListener('click', () => { diseaseForm.hidden = true; });
  diseaseForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    const data = Object.fromEntries(Object.keys(fields).map(key => [key, diseaseForm.elements.namedItem(key).value.trim()]));
    notice(diseaseNotice, '');
    if (!Object.values(data).some(Boolean)) { notice(diseaseNotice, 'Completa al menos un campo.'); return; }
    if (!editingDiseaseId && history.entries.length >= 50) { notice(diseaseNotice, 'Este paciente ya tiene 50 registros. Edita o elimina uno antes de agregar otro.'); return; }
    const summary = Object.entries(fields).map(([key, label]) => `${label}: ${data[key] || '(sin información)'}`).join('\n');
    await saveDisease(editingDiseaseId ? 'PUT' : 'POST', editingDiseaseId, data,
      `¿Guardar este registro para ${patient.name}?\n\n${summary}`, () => { diseaseForm.hidden = true; });
  });
  document.querySelector('#consult-patient').addEventListener('click', () => {
    if (patient) document.dispatchEvent(new CustomEvent('select-clinical-patient', {detail: {patient_id: patient.id}}));
  });
  document.querySelector('#close-consultation').addEventListener('click', () => { editor.hidden = true; });
  document.querySelector('#manual-entry').addEventListener('click', () => {
    openDiseaseForm();
  });
  document.querySelector('#proposal-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    if (!note.value.trim()) { notice(proposalNotice, 'Escribe una nota o usa «Crear registro manual».'); note.focus(); return; }
    if (proposals.children.length && !await confirmAction('¿Reemplazar las propuestas sin guardar por una nueva extracción?', {label: 'Preparar de nuevo'})) return;
    busy = true; updateControls(); notice(proposalNotice, 'Preparando una propuesta a partir de tu nota…', 'loading');
    try {
      const result = await request('/clinical/proposals', jsonOptions('POST', {patient_id: patient.id, note: note.value}), 420000);
      if (!result.ok) throw new Error(errorMessage(result));
      if (result.data.patient_id !== patient.id) throw new Error('La propuesta corresponde a otro paciente. No se preparó ningún registro.');
      proposals.replaceChildren();
      for (const entry of result.data.entries) addDraft(entry);
      notice(proposalNotice, result.data.message || (result.data.entries.length ? 'Revisa los campos y el texto de origen antes de guardar.' : 'No se identificaron datos para registrar. Puedes crear un registro manual.'), result.data.entries.length ? 'neutral' : 'warning');
    } catch (error) { notice(proposalNotice, `${error.message} Puedes crear un registro manual.`); }
    finally { busy = false; updateControls(); }
  });
  document.querySelector('#edit-history').addEventListener('click', () => {
    markdownInput.value = history.markdown; markdownRevision = history.revision; markdownForm.hidden = false; markdownInput.focus();
  });
  document.querySelector('#cancel-markdown').addEventListener('click', () => { markdownForm.hidden = true; });
  markdownForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (new TextEncoder().encode(markdownInput.value).length > 1048576) { notice(message, 'El Markdown supera el límite de 1 MiB.'); return; }
    await saveHistory('PUT', '', {markdown: markdownInput.value, revision: markdownRevision}, `¿Reemplazar el Markdown de ${patient.name} con el contenido editado? Los cambios pueden modificar o eliminar registros existentes.`, () => { markdownForm.hidden = true; });
  });
  document.querySelector('#download-history').addEventListener('click', async () => {
    if (busy) return;
    busy = true; updateControls();
    try {
      const result = await request(`${javaBase}/patients/${patient.id}/history.md`);
      if (!result.ok) throw new Error(errorMessage(result));
      const url = URL.createObjectURL(new Blob([result.text], {type: 'text/markdown;charset=utf-8'}));
      const link = document.createElement('a'); link.href = url; link.download = history.filename; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { notice(message, error.message); }
    finally { busy = false; updateControls(); }
  });
  document.querySelector('#retry-history-sync').addEventListener('click', async () => {
    if (busy) return;
    busy = true; updateControls();
    try { await synchronize(); }
    finally { busy = false; updateControls(); }
  });
  document.addEventListener('clinical-history-changed', async event => {
    if (patient?.id === event.detail.patient_id && history) {
      // La consulta puede haberse guardado mientras había un borrador de Markdown.
      // Conservamos ese borrador y pedimos recargar antes de sobrescribir su revisión.
      if (!markdownForm.hidden || !diseaseForm.hidden || proposals.children.length) {
        conflict = true; updateControls();
        notice(message, 'La historia cambió en otra operación. Actualízala antes de guardar tu borrador.', 'warning');
      } else await loadHistory();
    }
  });
  return {open};
}
