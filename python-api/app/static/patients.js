import {request, errorMessage, notice, confirmDelete} from './api.js';

export function initPatients(javaBase) {
  const body = document.querySelector('#patients-body');
  const search = document.querySelector('#patient-search');
  const status = document.querySelector('#patient-table-status');
  const message = document.querySelector('#patient-notice');
  const dialog = document.querySelector('#patient-dialog');
  const form = document.querySelector('#patient-form');
  const save = document.querySelector('#save-patient');
  const formError = document.querySelector('#patient-form-error');
  const name = document.querySelector('#patient-name');
  const birth = document.querySelector('#patient-birth');
  const email = document.querySelector('#patient-email');
  let rows = [];
  let editingId = null;
  let loading = false;
  let busy = false;

  function updateButtons() {
    document.querySelectorAll('#view-pacientes button').forEach(button => { button.disabled = busy || loading; });
    form.querySelectorAll('button, input').forEach(input => { input.disabled = busy; });
  }

  function renderRows() {
    const filter = search.value.trim().toLocaleLowerCase('es');
    const shown = rows.filter(row => `${row.id} ${row.name} ${row.email}`.toLocaleLowerCase('es').includes(filter));
    body.replaceChildren(...shown.map(row => {
      const tr = document.createElement('tr');
      tr.dataset.patientId = row.id;
      const date = row.birth_date.split('-').reverse().join('/');
      for (const value of [`#${row.id}`, row.name, date, row.email]) {
        const td = document.createElement('td'); td.textContent = value; tr.append(td);
      }
      const actionsCell = document.createElement('td');
      const actions = document.createElement('div'); actions.className = 'row-actions';
      for (const [action, label] of [['edit', 'Editar'], ['delete', 'Eliminar']]) {
        const button = document.createElement('button');
        button.type = 'button'; button.textContent = label;
        button.dataset.action = action; button.className = `${action}-action`;
        button.setAttribute('aria-label', `${label} a ${row.name}`);
        button.addEventListener('click', () => action === 'edit' ? editPatient(row.id) : deletePatient(row));
        actions.append(button);
      }
      actionsCell.append(actions); tr.append(actionsCell); return tr;
    }));
    document.querySelector('#patient-count').textContent = rows.length;
    document.querySelector('#patient-empty').hidden = shown.length > 0 || loading;
    status.textContent = `${shown.length} de ${rows.length} pacientes`;
    updateButtons();
  }

  async function loadPatients({keepNotice = false} = {}) {
    if (loading) return;
    loading = true; updateButtons();
    if (!keepNotice) notice(message, '');
    status.textContent = 'Cargando pacientes…';
    document.querySelector('#patient-empty').hidden = true;
    try {
      const result = await request(`${javaBase}/patients`);
      if (!result.ok) throw new Error(errorMessage(result));
      rows = result.data;
      renderRows();
    } catch (failure) {
      // Se conserva la última tabla visible, pero nunca se presenta como actualizada.
      notice(message, failure.message);
      status.textContent = rows.length ? 'No se pudo actualizar el listado' : 'No se pudo cargar el listado';
    } finally {
      loading = false; updateButtons();
      if (rows.length === 0 && !message.textContent) document.querySelector('#patient-empty').hidden = false;
    }
  }

  function openForm(row = null) {
    editingId = row?.id ?? null;
    form.reset(); name.setCustomValidity(''); notice(formError, '');
    document.querySelector('#patient-dialog-title').textContent = row ? 'Editar paciente' : 'Agregar paciente';
    if (row) { name.value = row.name; birth.value = row.birth_date; email.value = row.email; }
    save.textContent = row ? 'Guardar cambios' : 'Guardar paciente';
    dialog.showModal(); name.focus();
  }

  async function editPatient(id) {
    if (busy || loading) return;
    busy = true; updateButtons(); notice(message, '');
    try {
      const result = await request(`${javaBase}/patients/${id}`);
      if (!result.ok) throw new Error(errorMessage(result));
      openForm(result.data);
    } catch (failure) { notice(message, failure.message); }
    finally { busy = false; updateButtons(); if (dialog.open) name.focus(); }
  }

  async function deletePatient(row) {
    if (busy || loading) return;
    if (!await confirmDelete(`¿Quieres eliminar a ${row.name} (ID ${row.id}) del registro Java?`)) return;
    busy = true; updateButtons(); notice(message, '');
    try {
      const result = await request(`${javaBase}/patients/${row.id}`, {method: 'DELETE'});
      if (!result.ok) throw new Error(errorMessage(result));
      notice(message, `Paciente ${row.name} eliminado.`, 'success');
      await loadPatients({keepNotice: true});
    } catch (failure) { notice(message, failure.message); }
    finally { busy = false; updateButtons(); }
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    name.setCustomValidity(name.value.trim() ? '' : 'Escribe un nombre.');
    if (!form.reportValidity()) return;
    busy = true; updateButtons(); notice(formError, '');
    save.textContent = 'Guardando…';
    const isEdit = editingId !== null;
    try {
      const result = await request(`${javaBase}/patients${isEdit ? `/${editingId}` : ''}`, {
        method: isEdit ? 'PUT' : 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: name.value.trim(), birth_date: birth.value, email: email.value.trim()}),
      });
      if (!result.ok) throw new Error(errorMessage(result));
      dialog.close();
      notice(message, `Paciente ${result.data.name} ${isEdit ? 'actualizado' : 'agregado'}.`, 'success');
      await loadPatients({keepNotice: true});
    } catch (failure) { notice(formError, failure.message); }
    finally { busy = false; updateButtons(); save.textContent = isEdit ? 'Guardar cambios' : 'Guardar paciente'; }
  });
  name.addEventListener('input', () => name.setCustomValidity(''));
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.querySelectorAll('[data-close-dialog]').forEach(button => button.addEventListener('click', () => dialog.close()));
  document.querySelector('#new-patient').addEventListener('click', () => openForm());
  document.querySelector('#refresh-java').addEventListener('click', () => loadPatients());
  search.addEventListener('input', renderRows);
  document.addEventListener('java-patients-changed', () => {
    if (!document.querySelector('#view-pacientes').hidden) loadPatients();
  });
  return {loadPatients};
}
