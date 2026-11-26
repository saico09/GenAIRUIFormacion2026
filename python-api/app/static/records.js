export const fields = {disease: 'Enfermedad', treatment: 'Tratamiento', medication: 'Medicamento'};

export function readEntry(form) {
  return Object.fromEntries(Object.keys(fields).map(key => [key, form.elements.namedItem(key).value.trim()]));
}

export function describeEntry(data) {
  return Object.entries(fields).map(([key, label]) => `${label}: ${data[key] || '(sin información)'}`).join('\n');
}

const ENTRY_HEADING = '\n## Registro ';
const JOURNAL_HEADING = '\n## Consultas registradas\n';

// Markdown que genera Java: cabecera, registros editables y diario de consultas, en ese orden.
export function splitMarkdown(text) {
  const value = String(text).replace(/\r\n/g, '\n');
  let journal = value.indexOf(JOURNAL_HEADING);
  if (journal < 0) journal = value.length;
  let records = value.indexOf(ENTRY_HEADING);
  if (records < 0 || records > journal) records = journal;
  return {header: value.slice(0, records), records: value.slice(records, journal), journal: value.slice(journal)};
}

export function rebuildDraft(draft, current) {
  const now = splitMarkdown(current);
  return now.header + splitMarkdown(draft).records + now.journal;
}

function recordBlocks(markdown) {
  const blocks = splitMarkdown(markdown).records.split(ENTRY_HEADING).slice(1);
  return new Map(blocks.map(block => [block.split('\n', 1)[0].trim(), block.trimEnd()]));
}

export function recordIds(markdown) {
  return [...recordBlocks(markdown).keys()];
}

export function missingRecords(current, draft) {
  const kept = new Set(recordIds(draft));
  return recordIds(current).filter(id => !kept.has(id));
}

// Registros cambiados o borrados en el archivo tras abrir el editor que guardar el borrador desharía.
export function changedRecords(base, current, draft) {
  const [before, now, mine] = [base, current, draft].map(recordBlocks);
  return [...mine.keys()].filter(id => before.has(id) && now.get(id) !== before.get(id) && mine.get(id) !== now.get(id));
}
