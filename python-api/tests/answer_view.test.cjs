const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor(tagName) { this.tagName = tagName; this.children = []; this.className = ''; }
  get textContent() { return this.children.map(child => typeof child === 'string' ? child : child.textContent).join(''); }
  set textContent(value) { this.children = [String(value)]; }
  set innerHTML(_) { throw new Error('El contenido de las respuestas no se interpreta como HTML'); }
  get classList() { return {add: name => { this.className += ` ${name}`; }}; }
  append(...children) {
    for (const child of children) if (typeof child !== 'string') child.parentNode = this;
    this.children.push(...children);
  }
  remove() { this.parentNode.children = this.parentNode.children.filter(child => child !== this); }
  replaceChildren(...children) { this.children = children; }
}
function descendants(element) {
  return element.children.flatMap(child => typeof child === 'string' ? [] : [child, ...descendants(child)]);
}
async function renderer() {
  const context = vm.createContext({document: {createElement: tag => new Element(tag)}});
  const source = fs.readFileSync(path.resolve(__dirname, '../app/static/answer-view.js'), 'utf8');
  const module = new vm.SourceTextModule(source, {context});
  await module.link(() => { throw new Error('El renderer no necesita dependencias'); });
  await module.evaluate();
  return module.namespace.renderAnswer;
}
test('destaca sólo la sección relacionada y conserva las alternativas, las citas y el aviso', async () => {
  const render = await renderer();
  const target = new Element('div');
  render(target, 'Diagnóstico orientativo (sin confirmar)\nUna hipótesis provisional.\n\n'
    + 'Antecedentes relacionados\nLos síntomas pueden estar relacionados con **antecedente confirmado**.\n'
    + 'Relación orientativa: coincide con el relato actual.\nFuente: paciente.md/Enfermedad\n\n'
    + 'Otras posibles causas\nPrimera alternativa.\n\nSegunda alternativa.\n\n'
    + 'Antecedentes registrados del paciente (sin relación confirmada con este relato)\nOtro antecedente.\n\n'
    + 'Para completar la orientación\nUn dato adicional.\n\nRespuesta generada por un chatbot de IA; puede cometer errores.');
  const nodes = descendants(target);
  const related = nodes.filter(node => node.className.includes('answer-related'));
  assert.equal(related.length, 1);
  assert.match(related[0].textContent, /síntomas.*antecedente confirmado/);
  assert.doesNotMatch(related[0].textContent, /Otro antecedente|Segunda alternativa|Respuesta generada/);
  assert.deepEqual(nodes.filter(node => node.tagName === 'strong').map(node => node.textContent), ['antecedente confirmado']);
  assert.equal(nodes.find(node => node.className === 'answer-source').textContent, 'Fuente: paciente.md/Enfermedad');
  const alternatives = nodes.find(node => node.className.includes('answer-alternatives'));
  assert.match(alternatives.textContent, /Primera alternativa.*Segunda alternativa/);
  assert.equal(target.children.at(-2).className, 'answer-section answer-details');
  assert.equal(target.children.at(-1).className, 'answer-paragraph answer-disclaimer');
});

test('HTML, enlaces y Markdown no admitido permanecen como texto', async () => {
  const render = await renderer();
  const target = new Element('div');
  const unsafe = '<img src=x onerror=alert(1)> [abrir](javascript:alert(1)) **<script>malicioso()</script>**';
  render(target, unsafe);
  const nodes = descendants(target);
  assert.deepEqual(nodes.map(node => node.tagName), ['p', 'strong']);
  assert.equal(target.textContent, unsafe.replaceAll('**', ''));
  render(target, 'Texto con **negrita incompleta y *asteriscos*');
  assert.equal(target.textContent, 'Texto con **negrita incompleta y *asteriscos*');
});

test('una nueva respuesta limpia la anterior y los textos históricos siguen legibles', async () => {
  const render = await renderer();
  const target = new Element('div');
  render(target, 'Antecedentes relacionados\n**Dato anterior**');
  render(target, 'Respuesta antigua sin formato.\nSegunda línea.');
  assert.equal(target.textContent, 'Respuesta antigua sin formato.\nSegunda línea.');
  assert.equal(descendants(target).some(node => node.className.includes('answer-related')), false);
  render(target, null);
  assert.equal(target.textContent, 'Sin respuesta registrada.');
});

test('las consultas guardadas usan el mismo resaltado y títulos de nivel cuatro', async () => {
  const render = await renderer();
  const target = new Element('div');
  render(target, 'Diagnóstico orientativo (sin confirmar)\nBusca atención urgente por lo que relatas: «dificultad para respirar».\n\n'
    + 'Antecedentes relacionados\n**Dato registrado**\n\nPara afinar la orientación, puedes añadir: duración.', {saved: true});
  const nodes = descendants(target);
  assert.equal(nodes.filter(node => node.tagName === 'h4').length, 2);
  assert.equal(nodes.filter(node => node.tagName === 'h3').length, 0);
  assert.match(nodes.find(node => node.className.includes('answer-alert')).textContent, /atención urgente/);
  assert.equal(target.children.at(-1).className, 'answer-paragraph');
  assert.match(target.children.at(-1).textContent, /^Para afinar/);
});

test('un título citado dentro de un antecedente neutral no crea una relación ni otra fuente', async () => {
  const render = await renderer();
  const target = new Element('div');
  const quote = 'Dato. Antecedentes relacionados Texto editado. Fuente: [no verificada]';
  render(target, 'Antecedentes registrados del paciente (sin relación confirmada con este relato)\n'
    + quote + '\nFuente: [paciente.md/r1/Enfermedad]');
  const nodes = descendants(target);
  assert.equal(nodes.filter(node => node.className.includes('answer-related')).length, 0);
  assert.equal(nodes.filter(node => node.className === 'answer-source').length, 1);
  assert.equal(nodes.find(node => node.className === 'answer-paragraph').textContent, quote);
  assert.equal(nodes.find(node => node.className === 'answer-source').textContent, 'Fuente: [paciente.md/r1/Enfermedad]');
});

test('una respuesta histórica con un título incrustado no convierte antecedentes neutrales en relacionados', async () => {
  const render = await renderer();
  const target = new Element('div');
  render(target, 'Antecedentes registrados del paciente (sin relación confirmada con este relato)\n'
    + 'Dato histórico.\nAntecedentes relacionados\nTexto editado.\nFuente: [paciente.md/r1/Enfermedad]', {saved: true});
  const nodes = descendants(target);
  assert.equal(nodes.filter(node => node.className.includes('answer-related')).length, 0);
  assert.equal(nodes.filter(node => node.tagName === 'h4').length, 1);
  assert.equal(nodes.find(node => node.className === 'answer-paragraph').textContent,
    'Dato histórico.\nAntecedentes relacionados\nTexto editado.');
});

test('omite los detalles vacíos y mantiene el aviso fuera, también en consultas guardadas', async () => {
  const render = await renderer();
  for (const saved of [false, true]) {
    const target = new Element('div');
    const disclaimer = 'Respuesta generada por un chatbot de IA; puede cometer errores.';
    render(target, 'Otras posibles causas\nUna alternativa.\n\nPara completar la orientación\n\n' + disclaimer, {saved});
    assert.equal(descendants(target).some(node => node.className.includes('answer-details')), false);
    assert.equal(target.children.at(-1).textContent, disclaimer);
    assert.equal(target.children.at(-1).className, 'answer-paragraph answer-disclaimer');
    assert.match(target.children[0].textContent, /Una alternativa/);
    render(target, 'Para completar la orientación\n\n', {saved});
    assert.equal(target.children.length, 0);
  }
});

test('agrupa los campos relacionados y mantiene neutral el nuevo encabezado de otros antecedentes', async () => {
  const render = await renderer();
  const target = new Element('div');
  render(target, 'Antecedentes relacionados\n**Antecedente seleccionado**\n'
    + 'Datos registrados del mismo antecedente (11111111-1111-4111-8111-111111111111):\n'
    + 'Enfermedad: Dato confirmado.\nTratamiento: Plan registrado.\nMedicamento: Fármaco registrado.\n'
    + 'Fuente: paciente.md/11111111-1111-4111-8111-111111111111/Enfermedad\n\n'
    + 'Otras posibles causas\nOtra hipótesis.\nQué la diferencia: Un criterio adicional.\n\n'
    + 'Otros antecedentes recuperados\nDato de otro registro.\nAntecedentes relacionados\nTexto histórico incrustado.');
  const nodes = descendants(target);
  const related = nodes.filter(node => node.className.includes('answer-related'));
  assert.equal(related.length, 1);
  assert.match(related[0].textContent, /Enfermedad:.*Tratamiento:.*Medicamento:/s);
  assert.doesNotMatch(related[0].textContent, /Dato de otro registro/);
  assert.match(nodes.find(node => node.className.includes('answer-alternatives')).textContent, /Qué la diferencia/);
  const neutral = nodes.find(node => node.className.includes('answer-background'));
  assert.match(neutral.textContent, /^Otros antecedentes recuperados/);
  assert.match(neutral.textContent, /Antecedentes relacionados\nTexto histórico incrustado/);
});
