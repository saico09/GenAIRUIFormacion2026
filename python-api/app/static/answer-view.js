// Formato acotado del servidor: títulos conocidos y negrita; nunca se interpreta HTML.
const headings = new Map([
  ['Diagnóstico orientativo (sin confirmar)', 'answer-diagnosis'],
  ['Antecedentes relacionados', 'answer-related'],
  ['Otras posibles causas', 'answer-alternatives'],
  ['Antecedentes registrados del paciente (sin relación confirmada con este relato)', 'answer-background'],
  ['Para completar la orientación', 'answer-details'],
]);

function appendInline(element, text) {
  for (const part of text.split(/(\*\*[^*\n]+\*\*)/g)) {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      const strong = document.createElement('strong');
      strong.textContent = part.slice(2, -2);
      element.append(strong);
    } else element.append(part);
  }
}

export function renderAnswer(element, answer, {saved = false} = {}) {
  element.replaceChildren();
  element.classList.add('formatted-answer');
  let section = element;
  const detailSections = [];
  let relatedClosed = false;
  let paragraph = [];
  const flush = () => {
    if (!paragraph.length) return;
    const text = paragraph.join('\n');
    const node = document.createElement('p');
    node.className = 'answer-paragraph';
    if (text.startsWith('Busca atención urgente')) node.classList.add('answer-alert');
    if (text.startsWith('Respuesta generada por un chatbot')) node.classList.add('answer-disclaimer');
    appendInline(node, text);
    section.append(node);
    paragraph = [];
  };
  for (const raw of String(answer || 'Sin respuesta registrada.').split(/\r?\n/)) {
    const line = raw.trim();
    const kind = headings.get(line);
    // Los textos guardados antes de normalizar las citas pueden contener títulos dentro de un antecedente.
    if (kind && (kind !== 'answer-related' || !relatedClosed)) {
      flush();
      section = document.createElement('section');
      section.className = `answer-section ${kind}`;
      if (kind === 'answer-details') detailSections.push(section);
      if (kind === 'answer-background') relatedClosed = true;
      const heading = document.createElement(saved ? 'h4' : 'h3');
      heading.textContent = line;
      section.append(heading);
      element.append(section);
    } else if (line.startsWith('Fuente: ')) {
      flush();
      const source = document.createElement('p');
      source.className = 'answer-source';
      source.textContent = line;
      section.append(source);
    } else if (!line) flush();
    else {
      if (line.startsWith('Respuesta generada por un chatbot') ||
          (!section.className.includes('answer-details') && line.startsWith('Para afinar la orientación,'))) {
        flush();
        section = element;
      }
      paragraph.push(raw);
    }
  }
  flush();
  for (const details of detailSections) {
    if (details.children.length === 1) details.remove();
  }
}
