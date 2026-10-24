const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { test } = require('node:test');
const ts = require('typescript');

function savedFilterApi(initialRows = []) {
  let rows = initialRows;
  let written;
  const query = {
    insert(payload) { written = payload; rows = [{ id: 'filter-1', ...payload }]; return this; },
    update(payload) { return this.insert(payload); },
    select() { return this; }, eq() { return this; }, order() { return this; },
    async single() { return { data: rows[0], error: null }; },
    then(resolve) { return Promise.resolve({ data: rows, error: null }).then(resolve); },
  };
  const filename = path.join(__dirname, '../src/personalization.ts');
  const loaded = new Module(filename);
  loaded.require = id => {
    assert.equal(id, './supabase');
    return { requireSupabase: () => ({ from: table => { assert.equal(table, 'saved_filters'); return query; } }) };
  };
  loaded._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, filename);
  return { api: loaded.exports, payload: () => written };
}

test('numeric risk filters and new sort keys save and reload using the existing database schema', async () => {
  const { api, payload } = savedFilterApi();
  const expression = { operator: 'and', groups: [{ id: 'flags', operator: 'and', conditions: [
    { id: 'limit', field: 'red_flag_count', comparison: 'lte', value: '1' },
  ] }] };
  const saved = await api.saveFilter({ userId: 'user-1', name: 'Risk limit', expression, sortKey: 'red_flag_count', sortDirection: 'asc' });
  assert.equal(payload().sort_key, 'symbol', 'compatible with existing database constraints');
  assert.equal(saved.sort_key, 'red_flag_count');
  const [reloaded] = await api.fetchSavedFilters('user-1');
  assert.equal(reloaded.sort_key, 'red_flag_count');
  assert.deepEqual(reloaded.expression.groups, expression.groups);
  await api.saveFilter({ id: saved.id, userId: 'user-1', name: 'Edited risk limit', expression: reloaded.expression, sortKey: reloaded.sort_key, sortDirection: 'desc' });
  assert.equal(payload().expression.groups[0].conditions[0].comparison, 'lte');
  assert.equal(payload().expression.groups[0].conditions[0].value, '1');
});

test('legacy saved filters retain their existing sort and label rules', async () => {
  const legacy = { id: 'legacy', name: 'Growth', sort_key: 'revenue', expression: { operator: 'and', groups: [
    { id: 'growth', operator: 'or', conditions: [{ id: 'growing', field: 'revenue', value: 'Growing' }] },
  ] } };
  const { api } = savedFilterApi([legacy]);
  const [loaded] = await api.fetchSavedFilters('user-1');
  assert.equal(loaded.sort_key, 'revenue');
  assert.deepEqual(loaded.expression, legacy.expression);
});
