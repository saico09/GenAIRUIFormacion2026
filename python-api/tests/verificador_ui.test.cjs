const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

for (const failCleanup of [false, true]) {
  test(`el verificador conserva el error original${failCleanup ? ' y el de limpieza' : ''}`, async () => {
    const file = path.resolve(__dirname, '../../scripts/verificar_consultas_ui_real.cjs');
    let patient;
    let saved;
    let failure;
    const processStub = {env: {}, exitCode: 0};
    const fetchStub = async (url, options) => {
      if (options.method === 'POST' && url.endsWith('/patients')) patient = {id: 99, ...JSON.parse(options.body)};
      if (options.method === 'DELETE') {
        if (failCleanup) throw new Error('Fallo de limpieza');
        patient = null;
      }
      const status = options.method === 'DELETE' ? 204 : options.method === 'POST' && url.endsWith('/patients') ? 201 : url.endsWith('/patients/99') && !patient ? 404 : 200;
      return {status, text: async () => JSON.stringify(url.endsWith('/patients') && options.method !== 'POST' ? [] : patient)};
    };
    const context = {__dirname: path.dirname(file), process: processStub, fetch: fetchStub, AbortSignal,
      console: {log() {}, error(error) { failure = error; }},
      require(name) {
        if (name === 'playwright') return {chromium: {async launch() { throw new Error('Fallo original'); }}};
        if (name === 'node:fs') return {existsSync: () => false, mkdirSync() {}, writeFileSync(destination, body) { saved = JSON.parse(body); }};
        return require(name);
      },
    };
    await vm.runInNewContext(fs.readFileSync(file, 'utf8'), context, {filename: file});
    assert.equal(processStub.exitCode, 1);
    assert.equal(saved.error, 'Fallo original');
    assert.equal(saved.result, 'failed');
    assert.equal(failure.name, 'AggregateError');
    assert.equal(failure.errors[0].message, 'Fallo original');
    assert.equal(failure.errors.length, failCleanup ? 2 : 1);
    if (failCleanup) assert.equal(saved.cleanup_error, 'Fallo de limpieza');
    else assert.equal(saved.cleanup.patient_deleted, true);
  });
}
