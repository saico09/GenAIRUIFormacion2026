import {request, notice} from './api.js';
import {initChat} from './chat.js';
import {initPatients} from './patients.js';
import {initExplorer} from './explorer.js';

const titles = {consultas: 'Consultas médicas', pacientes: 'Pacientes', 'api-python': 'API Python', 'api-java': 'API Java'};
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
}

window.addEventListener('hashchange', navigate);
document.querySelector('.skip-link').addEventListener('click', event => {
  event.preventDefault();
  document.querySelector('#main').focus();
});
navigate();

try {
  const result = await request('/ui-config');
  if (!result.ok || !Number.isInteger(result.data?.java_api_port)) throw new Error('No se pudo cargar la configuración de las APIs. Recarga la página para intentarlo de nuevo.');
  // El mismo hostname del navegador funciona tanto con localhost como con 127.0.0.1.
  const javaUrl = new URL(location.origin);
  javaUrl.port = String(result.data.java_api_port);
  const javaBase = javaUrl.origin;
  initChat(javaBase);
  patients = initPatients(javaBase);
  initExplorer('python', location.origin, result.data.metrics_enabled);
  initExplorer('java', javaBase, result.data.metrics_enabled);
  navigate();
} catch (error) {
  notice(document.querySelector('#config-error'), error.message);
  document.querySelectorAll('#view-pacientes button').forEach(button => { button.disabled = true; });
}
