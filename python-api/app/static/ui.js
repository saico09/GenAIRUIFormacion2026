import {request, notice} from './api.js';

const titles = {consultas: 'Consultas médicas', pacientes: 'Pacientes', 'api-python': 'API Python', 'api-java': 'API Java'};
const configError = document.querySelector('#config-error');
let patients = null;

function navigate() {
  const section = location.hash.slice(1);
  const active = Object.hasOwn(titles, section) ? section : 'consultas';
  document.querySelectorAll('[data-view]').forEach(view => { view.hidden = view.dataset.view !== active; });
  document.querySelectorAll('[data-nav]').forEach(link => {
    if (link.dataset.nav === active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  document.title = `${titles[active]} · GenAI Clínica`;
  if (active === 'pacientes' && patients) patients.loadPatients();
  document.dispatchEvent(new CustomEvent('view-shown', {detail: {view: active}}));
}

window.addEventListener('hashchange', navigate);
document.querySelector('.skip-link').addEventListener('click', event => {
  event.preventDefault();
  document.querySelector('#main').focus();
});
navigate();

const disablePatients = () => document.querySelectorAll('#view-pacientes button').forEach(button => { button.disabled = true; });
let config = null;
try {
  const result = await request('/ui-config');
  if (!result.ok || !Number.isInteger(result.data?.java_api_port)) throw new Error('No se pudo cargar la configuración de las APIs. Recarga la página para intentarlo de nuevo.');
  config = result.data;
} catch (error) {
  notice(configError, error.message);
  disablePatients();
}

if (config) {
  // El mismo hostname del navegador funciona tanto con localhost como con 127.0.0.1.
  const javaUrl = new URL(location.origin);
  javaUrl.port = String(config.java_api_port);
  const javaBase = javaUrl.origin;
  // Cada sección se carga y arranca por separado: si una falla, las demás siguen disponibles.
  const failed = [];
  for (const [name, file, start] of [
    ['Consultas médicas', './chat.js', module => module.initChat(javaBase)],
    ['Pacientes', './patients.js', module => { patients = module.initPatients(javaBase); }],
    ['API Python', './explorer.js', module => module.initExplorer('python', location.origin, config.metrics_enabled)],
    ['API Java', './explorer.js', module => module.initExplorer('java', javaBase, config.metrics_enabled)],
  ]) {
    try { start(await import(file)); } catch (error) {
      failed.push(name); console.error(error);
      if (name === 'Pacientes') disablePatients();
    }
  }
  if (failed.length) notice(configError, `No se pudo iniciar: ${failed.join(', ')}. Las demás secciones siguen disponibles; recarga la página para reintentar.`);
  navigate();
}
