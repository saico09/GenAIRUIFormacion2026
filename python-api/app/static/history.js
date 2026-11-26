import {request, errorMessage, notice, confirmAction, syncIndex, indexError, indexSyncing, setIndexState} from './api.js';
import {fields, readEntry, describeEntry, rebuildDraft, missingRecords, changedRecords} from './records.js';
import {entryRows, consultationRows, draftForm} from './history-view.js';

const PROPOSAL_TIMEOUT = 420000;
const jsonOptions = (method, data, signal) => ({method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data), signal});

export function initHistory(javaBase) {
  const detail = document.querySelector('#patient-detail');
  const list = document.querySelector('#patient-list');
  const message = document.querySelector('#history-notice');
  const editor = document.querySelector('#consultation-editor');
  const note = document.querySelector('#consultation-note');
  note.maxLength = 6000;
  const proposals = document.querySelector('#proposed-entries');
  const proposalNotice = document.querySelector('#proposal-notice');
  const cancelProposal = document.querySelector('#cancel-proposal');
  const markdownForm = document.querySelector('#history-markdown-form');
  const markdownInput = document.querySelector('#history-markdown-input');
  const diseaseForm = document.querySelector('#disease-form');
  const diseaseNotice = document.querySelector('#disease-form-notice');
  let patient = null;
  let history = null;
  let busy = false;
  let conflict = false;   // El archivo cambió con el editor Markdown abierto: sólo bloquea ese editor.
  let stale = false;      // Un cambio guardado no se pudo releer: se bloquean las escrituras hasta actualizar.
  let nextDraft = 0;
  let editingDiseaseId = null;
  let diseaseBase = '';
  let markdownRevision = null;
  let markdownBase = '';
  let proposalRequest = null;

  const canWrite = () => !busy && history && !stale;
  const diseaseDirty = () => !diseaseForm.hidden && JSON.stringify(readEntry(diseaseForm)) !== diseaseBase;
  const noteDirty = () => !editor.hidden && (note.value.trim() !== '' || proposals.children.length > 0);
  const hasDrafts = () => (!markdownForm.hidden && markdownInput.value !== markdownBase) || diseaseDirty() || noteDirty();

  function updateControls() {
    detail.setAttribute('aria-busy', String(busy));
    detail.querySelectorAll('button, textarea').forEach(control => {
      control.disabled = busy || (!history && !['history-back', 'refresh-history'].includes(control.id));
    });
    cancelProposal.disabled = !proposalRequest;
    if (stale) detail.querySelectorAll('[data-save-entry], #save-markdown, #save-disease').forEach(button => { button.disabled = true; });
    else if (conflict) document.querySelector('#save-markdown').disabled = true;
  }

  // Si el control que inició la acción perdió el foco al deshabilitarse, se le devuelve.
  function restoreFocus(element) {
    const active = document.activeElement;
    if (element?.isConnected && !element.disabled && (!active || active === document.body)) element.focus({preventScroll: true});
  }

  function syncStatus() {
    const error = patient && !indexSyncing(patient.id) ? indexError(patient.id) : undefined;
    document.querySelector('#history-sync').hidden = error === undefined;
    if (error !== undefined) notice(document.querySelector('#history-sync-message'),
      `La historia está guardada, pero su índice RAG sigue pendiente.${error ? ` ${error.trimEnd().replace(/\.$/, '')}.` : ''} Puedes reintentar la sincronización.`, 'warning');
  }

  function renderHistory(data) {
    history = data;
    document.querySelector('#history-body').replaceChildren(...entryRows(data.entries, openDiseaseForm, deleteDisease));
    document.querySelector('#history-count').textContent = data.entries.length;
    document.querySelector('#history-empty').hidden = data.entries.length > 0;
    document.querySelector('#history-markdown-text').textContent = data.markdown;
    document.querySelector('#history-filename').textContent = data.filename;
    const consultations = consultationRows(data.consultations);
    document.querySelector('#consultations-count').textContent = consultations.length;
    document.querySelector('#consultations-empty').hidden = consultations.length > 0;
    document.querySelector('#consultations-body').replaceChildren(...consultations);
    syncStatus();
    // Las filas nuevas nacen habilitadas: se ajustan al estado actual.
    updateControls();
  }

  function draftRisks() {
    const missing = missingRecords(history.markdown, markdownInput.value);
    const changed = changedRecords(markdownBase, history.markdown, markdownInput.value);
    return {missing, changed};
  }

  function refreshDraft() {
    if (markdownForm.hidden || markdownRevision === history.revision) return '';
    markdownInput.value = rebuildDraft(markdownInput.value, history.markdown);
    markdownRevision = history.revision;
    const {missing, changed} = draftRisks();
    return 'Historia actualizada. Tu borrador conserva sus registros con la cabecera y las consultas vigentes; revísalo antes de guardar.'
      + (missing.length ? ` El archivo tiene registros que tu borrador no incluye y se eliminarían al guardar: ${missing.join(', ')}.` : '')
      + (changed.length ? ` Estos registros cambiaron en el archivo y tu borrador conserva su versión anterior: ${changed.join(', ')}.` : '');
  }

  // /history ya incluye los registros: una sola lectura auditada por refresco.
  async function readHistory() {
    const report = await request(`${javaBase}/patients/${patient.id}/history`);
    if (!report.ok) throw new Error(errorMessage(report));
    renderHistory(report.data);
    return refreshDraft();
  }

  async function loadHistory() {
    if (busy || !patient) return;
    const focused = document.activeElement;
    busy = true; updateControls(); notice(message, 'Cargando historia…', 'loading');
    try {
      const draftNote = await readHistory();
      conflict = false; stale = false;
      notice(message, draftNote, 'warning');
    } catch (error) { notice(message, error.message); }
    finally { busy = false; updateControls(); restoreFocus(focused); }
  }

  async function synchronize() {
    const id = patient.id;
    try {
      await syncIndex(id);
      if (patient?.id === id) notice(message, 'Historia guardada y disponible para las consultas RAG.', 'success');
    } catch {
      if (patient?.id === id) notice(message, 'La historia está guardada; su sincronización quedó pendiente.', 'warning');
    } finally { syncStatus(); }
  }

  async function afterWrite() {
    const draftNote = await readHistory();
    document.querySelector('#history-patient-name').focus({preventScroll: true});
    notice(message, 'Historia guardada. Actualizando el índice RAG…', 'loading');
    await synchronize();
    if (draftNote) notice(message, draftNote, 'warning');
  }

  function savedReadFailed(error) {
    stale = true;
    setIndexState(patient.id, ''); syncStatus();
    notice(message, `El cambio quedó guardado, pero no se pudo actualizar la vista. Pulsa «Actualizar historia». ${error.message}`, 'warning');
  }

  // Confirmar antes de bloquear: al cancelar, el foco vuelve a un botón todavía habilitado.
  async function write(url, options, description, confirmOptions, afterSave, canSave = canWrite, errorTarget = message) {
    if (!canSave()) return;
    const trigger = document.activeElement;
    if (!await confirmAction(description, confirmOptions) || !canSave()) return;
    busy = true; updateControls();
    let saved = false;
    let focusTarget = trigger;
    try {
      notice(message, url.includes('/diseases') ? 'Guardando registro…' : 'Guardando historia…', 'loading');
      const result = await request(url, options);
      if (result.status === 409 && options.method === 'PUT' && url.endsWith('/history')) {
        conflict = true; focusTarget = document.querySelector('#refresh-history');
        throw new Error(`${errorMessage(result)} Pulsa «Actualizar historia»: tu borrador se conserva y se combina con la versión actual antes de volver a guardar.`);
      }
      if (!result.ok) throw new Error(errorMessage(result));
      saved = true;
      afterSave();
      // Una lectura fallida no debe dejar el formulario listo para repetir un alta ya guardada.
      await afterWrite();
    } catch (error) {
      if (saved) savedReadFailed(error);
      else {
        if (errorTarget !== message) notice(message, '');
        notice(errorTarget, error.message);
      }
    } finally { busy = false; updateControls(); restoreFocus(focusTarget); }
  }

  function saveDisease(method, id, data, description, afterSave = () => {}, errorTarget = message) {
    return write(`${javaBase}/patients/${patient?.id}/diseases${id ? `/${id}` : ''}`, data ? jsonOptions(method, data) : {method}, description,
      {title: method === 'DELETE' ? 'Eliminar registro' : 'Guardar registro', label: method === 'DELETE' ? 'Eliminar registro' : 'Confirmar y guardar',
        danger: method === 'DELETE', hint: 'El cambio se reflejará en la tabla y en el Markdown de este paciente.'}, afterSave, canWrite, errorTarget);
  }

  async function openDiseaseForm(entry = null) {
    if (busy || !history) return;
    const id = entry?.id ?? null;
    if (!diseaseForm.hidden && editingDiseaseId === id) { diseaseForm.elements.namedItem('disease').focus(); return; }
    if (diseaseDirty() && !await confirmAction('¿Descartar los cambios sin guardar del registro que estás editando?',
      {title: 'Cambios sin guardar', label: 'Descartar cambios'})) return;
    editingDiseaseId = id;
    diseaseForm.reset(); notice(diseaseNotice, '');
    document.querySelector('#disease-form-title').textContent = entry ? 'Editar registro confirmado' : 'Agregar registro confirmado';
    document.querySelector('#disease-record-id').textContent = entry ? `ID: ${entry.id}` : 'El ID se asigna al guardar.';
    for (const key of Object.keys(fields)) diseaseForm.elements.namedItem(key).value = entry?.[key] || '';
    diseaseBase = JSON.stringify(readEntry(diseaseForm));
    diseaseForm.hidden = false;
    diseaseForm.elements.namedItem('disease').focus();
    diseaseForm.scrollIntoView({behavior: 'smooth', block: 'center'});
  }

  function deleteDisease(entry) {
    return saveDisease('DELETE', entry.id, null,
      `¿Eliminar el registro ${entry.id} de ${patient.name}?\n\n${entry.disease || 'Sin enfermedad indicada'}\n\nLas consultas guardadas se conservan.`,
      () => { if (editingDiseaseId === entry.id) diseaseForm.hidden = true; });
  }

  function addDraft(entry = {}) {
    const {form, localError} = draftForm(++nextDraft, entry);
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (busy) return;
      const data = readEntry(form);
      notice(localError, '');
      if (!Object.values(data).some(Boolean)) { notice(localError, 'Completa al menos un campo con un hecho de la consulta.'); return; }
      if (history.entries.length >= 50) { notice(localError, 'La historia ya tiene 50 registros. Revisa su Markdown antes de añadir otro.'); return; }
      await saveDisease('POST', null, data, `¿Guardar este registro para ${patient.name}?\n\n${describeEntry(data)}`, () => {
        form.remove();
        notice(proposalNotice, proposals.children.length ? 'Registro guardado. Quedan propuestas por revisar.' : 'Registro guardado. No quedan propuestas pendientes.', 'success');
      }, localError);
    });
    proposals.append(form); updateControls();
  }

  async function showConsultation(draft = '') {
    if (noteDirty() && note.value !== draft && !await confirmAction('¿Descartar la nota y las propuestas sin guardar para empezar de nuevo?',
      {title: 'Borrador sin guardar', label: 'Descartar borrador'})) { note.focus(); return; }
    editor.hidden = false; note.value = draft; proposals.replaceChildren(); notice(proposalNotice, '');
    note.focus(); editor.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  async function open(row, draft = null) {
    if (busy) {
      notice(message, `Espera a que termine la operación en curso en la historia de ${patient?.name || 'otro paciente'} antes de abrir otra.`, 'warning');
      return false;
    }
    list.hidden = true; detail.hidden = false;
    const showIdentity = () => {
      document.querySelector('#history-patient-name').textContent = row.name;
      document.querySelector('#history-patient-info').textContent = `Paciente #${row.id} · ${row.email || ''}`;
    };
    if (patient?.id === row.id && history) {
      patient = row; showIdentity();
      await loadHistory();
      if (draft !== null) await showConsultation(draft);
      else document.querySelector('#history-patient-name').focus();
      return true;
    }
    if (patient && hasDrafts() && !await confirmAction(`¿Descartar los borradores sin guardar de ${patient.name} y abrir la historia de ${row.name}?`,
      {title: 'Borradores sin guardar', label: 'Descartar y abrir', hint: 'Se pierden el Markdown, el registro o la nota que no guardaste.'})) return false;
    if (busy) return false;
    patient = row; history = null; conflict = false; stale = false;
    editingDiseaseId = null; markdownRevision = null; markdownInput.value = markdownBase = ''; note.value = '';
    proposals.replaceChildren(); notice(proposalNotice, '');
    editor.hidden = true; markdownForm.hidden = true; diseaseForm.hidden = true;
    document.querySelector('#history-markdown').open = false;
    document.querySelector('#history-body').replaceChildren();
    document.querySelector('#history-markdown-text').textContent = '';
    document.querySelector('#history-count').textContent = '—';
    document.querySelector('#history-filename').textContent = '';
    document.querySelector('#history-empty').hidden = true;
    document.querySelector('#consultations-body').replaceChildren();
    document.querySelector('#consultations-count').textContent = '—';
    document.querySelector('#consultations-empty').hidden = true;
    showIdentity();
    syncStatus();
    await loadHistory();
    // El foco se mueve cuando la vista ya está visible (al abrir desde Consultas cambia el hash antes).
    if (draft !== null && history) await showConsultation(draft);
    else document.querySelector('#history-patient-name').focus();
    return true;
  }

  document.querySelector('#history-back').addEventListener('click', () => {
    if (busy) return;
    detail.hidden = true; list.hidden = false;
    list.querySelector(`[data-patient-id="${patient.id}"] [data-action="history"]`)?.focus();
  });
  document.querySelector('#refresh-history').addEventListener('click', () => void loadHistory());
  document.querySelector('#new-consultation').addEventListener('click', () => {
    if (editor.hidden) void showConsultation();
    else { note.focus(); editor.scrollIntoView({behavior: 'smooth', block: 'start'}); }
  });
  document.querySelector('#new-disease').addEventListener('click', () => openDiseaseForm());
  document.querySelector('#cancel-disease').addEventListener('click', () => { diseaseForm.hidden = true; });
  diseaseForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    const data = readEntry(diseaseForm);
    notice(diseaseNotice, '');
    if (!Object.values(data).some(Boolean)) { notice(diseaseNotice, 'Completa al menos un campo.'); return; }
    if (!editingDiseaseId && history.entries.length >= 50) { notice(diseaseNotice, 'Este paciente ya tiene 50 registros. Edita o elimina uno antes de agregar otro.'); return; }
    await saveDisease(editingDiseaseId ? 'PUT' : 'POST', editingDiseaseId, data,
      `¿Guardar este registro para ${patient.name}?\n\n${describeEntry(data)}`, () => { diseaseForm.hidden = true; }, diseaseNotice);
  });
  document.querySelector('#consult-patient').addEventListener('click', () => {
    if (patient) document.dispatchEvent(new CustomEvent('select-clinical-patient', {detail: {patient_id: patient.id}}));
  });
  document.querySelector('#close-consultation').addEventListener('click', async () => {
    if (noteDirty() && !await confirmAction('¿Cerrar y descartar la nota y las propuestas sin guardar?',
      {title: 'Borrador sin guardar', label: 'Descartar borrador'})) return;
    editor.hidden = true; note.value = ''; proposals.replaceChildren(); notice(proposalNotice, '');
    document.querySelector('#new-consultation').focus();
  });
  document.querySelector('#manual-entry').addEventListener('click', () => openDiseaseForm());
  document.querySelector('#proposal-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    if (!note.value.trim()) { notice(proposalNotice, 'Escribe una nota o usa «Crear registro manual».'); note.focus(); return; }
    if (proposals.children.length && !await confirmAction('¿Reemplazar las propuestas sin guardar por una nueva extracción?', {label: 'Preparar de nuevo'})) return;
    if (busy) return;
    const controller = new AbortController();
    proposalRequest = controller; cancelProposal.hidden = false;
    busy = true; updateControls(); notice(proposalNotice, 'Preparando una propuesta a partir de tu nota…', 'loading');
    let cancelled = false;
    try {
      const result = await request('/clinical/proposals', jsonOptions('POST', {patient_id: patient.id, note: note.value}, controller.signal), PROPOSAL_TIMEOUT);
      if (!result.ok) throw new Error(errorMessage(result));
      if (result.data.patient_id !== patient.id) throw new Error('La propuesta corresponde a otro paciente. No se preparó ningún registro.');
      proposals.replaceChildren();
      for (const entry of result.data.entries) addDraft(entry);
      notice(proposalNotice, result.data.message || (result.data.entries.length ? 'Revisa los campos y el texto de origen antes de guardar.' : 'No se identificaron datos para registrar. Puedes crear un registro manual.'), result.data.entries.length ? 'neutral' : 'warning');
    } catch (error) {
      cancelled = error.name === 'AbortError';
      if (cancelled) notice(proposalNotice, 'Preparación cancelada. Tu nota se conserva: puedes prepararla de nuevo o crear un registro manual.', 'warning');
      else notice(proposalNotice, `${error.message} Puedes crear un registro manual.`);
    } finally {
      proposalRequest = null; cancelProposal.hidden = true;
      busy = false; updateControls();
      if (cancelled) note.focus();
    }
  });
  cancelProposal.addEventListener('click', () => proposalRequest?.abort());
  document.querySelector('#edit-history').addEventListener('click', () => {
    if (!history) return;
    if (markdownForm.hidden) {
      markdownInput.value = markdownBase = history.markdown; markdownRevision = history.revision; markdownForm.hidden = false;
    }
    markdownInput.focus();
  });
  document.querySelector('#cancel-markdown').addEventListener('click', () => { markdownForm.hidden = true; });
  markdownForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (new TextEncoder().encode(markdownInput.value).length > 1048576) { notice(message, 'El Markdown supera el límite de 1 MiB.'); return; }
    const {missing, changed} = history ? draftRisks() : {missing: [], changed: []};
    const removal = missing.length
      ? `\n\nSe eliminarán del archivo actual ${missing.length === 1 ? 'este registro' : 'estos registros'}: ${missing.join(', ')}.`
      : ' Los cambios pueden modificar o eliminar registros existentes.';
    const reverted = changed.length
      ? `\n\nVolverán a la versión de tu borrador (cambiaron en el archivo después de abrir el editor): ${changed.join(', ')}.` : '';
    await write(`${javaBase}/patients/${patient?.id}/history`,
      jsonOptions('PUT', {revision: markdownRevision, markdown: markdownInput.value, confirmed: true}),
      `¿Reemplazar el Markdown de ${patient?.name} con el contenido editado?${removal}${reverted}`,
      {title: 'Guardar en la historia', label: 'Confirmar y guardar', hint: 'Revisa los datos antes de confirmar. Esto modifica el archivo clínico del paciente.'},
      () => { markdownForm.hidden = true; }, () => canWrite() && !conflict);
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
    if (busy || !patient) return;
    busy = true; updateControls();
    notice(message, 'Reintentando la sincronización del índice RAG…', 'loading');
    try { await synchronize(); }
    finally { busy = false; updateControls(); }
  });
  document.addEventListener('clinical-history-changed', async event => {
    if (patient?.id !== event.detail.patient_id || !history) return;
    // Recargar cambiaría un borrador Markdown abierto: se rearma sólo al pulsar «Actualizar historia».
    if (!markdownForm.hidden) {
      conflict = true; updateControls();
      notice(message, 'La historia cambió en otra operación. Pulsa «Actualizar historia»: tu borrador Markdown se conserva y se combina con la versión actual.', 'warning');
    } else await loadHistory();
  });
  document.addEventListener('index-sync-changed', event => { if (event.detail.patient_id === patient?.id) syncStatus(); });
  return {open};
}
