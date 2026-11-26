import {fields} from './records.js';
import {renderAnswer} from './answer-view.js';

export function entryRows(entries, onEdit, onDelete) {
  return entries.map(entry => {
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
      button.addEventListener('click', () => action === 'edit' ? onEdit(entry) : onDelete(entry));
      actions.append(button);
    }
    cell.append(actions); row.append(cell);
    return row;
  });
}

export function consultationRows(consultations) {
  const sorted = [...(consultations || [])].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  return sorted.map(consultation => {
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
      const text = document.createElement('div'); text.className = 'saved-answer';
      renderAnswer(text, answer, {saved: true});
      details.append(heading, text);
    }
    content.append(question, identifier, details); row.append(dateCell, content);
    return row;
  });
}

export function draftForm(id, entry = {}) {
  const form = document.createElement('form'); form.className = 'entry-draft';
  const heading = document.createElement('h3'); heading.textContent = 'Propuesta para revisar'; form.append(heading);
  const columns = document.createElement('div'); columns.className = 'entry-fields';
  for (const [key, labelText] of Object.entries(fields)) {
    const group = document.createElement('div');
    const label = document.createElement('label'); label.htmlFor = `draft-${id}-${key}`; label.textContent = labelText;
    const input = document.createElement('textarea'); input.id = label.htmlFor; input.name = key; input.rows = 2; input.maxLength = 2000;
    input.value = typeof entry[key] === 'string' ? entry[key] : '';
    group.append(label, input);
    const evidence = document.createElement('p'); evidence.className = 'field-evidence';
    const quote = entry.evidence?.[key];
    evidence.textContent = `Texto de la nota: ${typeof quote === 'string' && quote ? quote : Array.isArray(quote) && quote.length ? quote.join(' · ') : 'No identificado; se deja vacío.'}`;
    group.append(evidence); columns.append(group);
  }
  const localError = document.createElement('p'); localError.className = 'notice error'; localError.hidden = true; localError.setAttribute('role', 'alert');
  const actions = document.createElement('div'); actions.className = 'dialog-actions';
  const discard = document.createElement('button'); discard.type = 'button'; discard.className = 'button secondary'; discard.textContent = 'Descartar';
  discard.addEventListener('click', () => form.remove());
  const save = document.createElement('button'); save.type = 'submit'; save.className = 'button primary'; save.dataset.saveEntry = ''; save.textContent = 'Guardar este registro';
  actions.append(discard, save); form.append(columns, localError, actions);
  return {form, localError};
}
