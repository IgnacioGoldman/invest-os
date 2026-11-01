(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('playground-data').textContent);
  const $ = id => document.getElementById(id);
  const fieldByKey = new Map(data.fields.map(field => [field.key, field]));
  const comparisons = { lt: '<', lte: '≤', eq: '=', gte: '≥', gt: '>' };
  const storageKey = `invest-os:filter-playground:v1:${location.pathname}`;
  const clone = value => JSON.parse(JSON.stringify(value));
  const rows = new Map(Array.from(document.querySelectorAll('tbody tr'), row => [row.dataset.symbol, row]));
  const searches = new Map(Array.from(rows, ([symbol, row]) => [symbol, row.textContent.toLowerCase()]));
  const normalizeRule = rule => ({ ...rule, field: rule.field.startsWith('support_') ? 'support' : rule.field });
  const presets = data.presets.map(preset => ({ ...preset, builtin: true, rules: preset.rules.map(normalizeRule) }));
  const all = { id: 'all', name: 'All stocks', builtin: true, rules: [], operator: 'and',
    description: 'The complete universe in its original rank order.' };
  let customFilters = [], activeId = 'all', draft = null, editingId = null, visibleStocks = [];

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function option(value, label) {
    const node = element('option', label);
    node.value = value;
    return node;
  }
  function metricMatches(metric, rule) {
    if (rule.comparison) {
      const value = metric?.value, target = Number(rule.values[0]);
      if (typeof value !== 'number' || !Number.isFinite(value)) return false;
      return rule.comparison === 'lt' ? value < target : rule.comparison === 'lte' ? value <= target
        : rule.comparison === 'gt' ? value > target : rule.comparison === 'gte' ? value >= target : value === target;
    }
    return rule.values.some(value => metric?.label === (rule.field === 'revenue' && value === 'Flat growth' ? 'Flat' : value));
  }
  function ruleMatches(stock, rule) {
    return rule.field === 'support'
      ? rule.timeframes.some(field => metricMatches(stock.metrics[field], rule))
      : metricMatches(stock.metrics[rule.field], rule);
  }
  function matches(stock, filter) {
    if (!filter.rules.length) return true;
    const checks = filter.rules.map(rule => ruleMatches(stock, rule));
    return filter.operator === 'or' ? checks.some(Boolean) : checks.every(Boolean);
  }
  function selected(filter) { return data.stocks.filter(stock => matches(stock, filter)); }
  function validate(filter) {
    if (!filter || !['and', 'or'].includes(filter.operator) || !Array.isArray(filter.rules)
        || !filter.rules.length || filter.rules.length > 20) return 'Add between 1 and 20 conditions.';
    for (const [index, rule] of filter.rules.entries()) {
      const field = fieldByKey.get(rule?.field);
      if (!field || !Array.isArray(rule.values) || rule.values.length === 0) return `Choose a value for condition ${index + 1}.`;
      if (rule.comparison) {
        const target = rule.values[0];
        if (!field.numeric || !Object.hasOwn(comparisons, rule.comparison) || rule.values.length !== 1
            || typeof target !== 'string' || !/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(target.trim())
            || !Number.isFinite(Number(target))) return `Enter a finite number for condition ${index + 1}.`;
        if (field.unit === 'count' && (!Number.isInteger(Number(target)) || Number(target) < 0))
          return `Use a non-negative whole number for condition ${index + 1}.`;
      } else if (!rule.values.every(value => field.options.some(o => o.value === value))) {
        return `Choose valid values for condition ${index + 1}.`;
      }
      if (rule.field === 'support' && (!Array.isArray(rule.timeframes) || !rule.timeframes.length
          || !rule.timeframes.every(key => data.timeframes.some(t => t.key === key))))
        return `Choose at least one timeframe for condition ${index + 1}.`;
    }
    return '';
  }
  function storageMessage(message) {
    $('storage-message').hidden = false;
    $('storage-message').textContent = message;
  }
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || '[]');
    const seen = new Set();
    if (!Array.isArray(saved)) throw new Error('Invalid saved filters');
    customFilters = saved.slice(0, 30).filter(filter => {
      const valid = typeof filter?.id === 'string' && filter.id.startsWith('custom:') && !seen.has(filter.id)
        && typeof filter.name === 'string' && filter.name.trim().length > 0 && filter.name.length <= 80 && !validate(filter);
      if (valid) seen.add(filter.id);
      return valid;
    }).map(filter => ({ id: filter.id, name: filter.name, operator: filter.operator, rules: filter.rules }));
  } catch {
    storageMessage('Browser storage is unavailable or could not be read. You can still experiment in this tab.');
  }
  function persist() {
    try { localStorage.setItem(storageKey, JSON.stringify(customFilters)); }
    catch { storageMessage('Browser storage is unavailable. Your filters are available in this tab until it closes.'); }
  }
  const filters = () => [all, ...presets, ...customFilters];
  const active = () => filters().find(filter => filter.id === activeId) || all;
  function stats(stocks) {
    return { count: stocks.length, top20: stocks.filter(s => s.rank <= 20).length,
      top50: stocks.filter(s => s.rank <= 50).length,
      avg: stocks.length ? (stocks.reduce((sum, s) => sum + s.rank, 0) / stocks.length).toFixed(1) : '—',
      tags: stocks.filter(s => ['Strong', 'Solid'].includes(s.business_quality) && ['Cheap', 'Fair'].includes(s.valuation)).length };
  }
  function renderCapture() {
    const chart = $('capture-chart');
    chart.replaceChildren();
    const filter = draft || active(), error = draft && validate(draft);
    $('capture-legend').hidden = !!error;
    if (error) {
      $('capture-summary').textContent = 'Draft preview · Complete the conditions to see capture by rank.';
      $('capture-detail').textContent = error;
      return;
    }
    const cohort = selected(filter), retained = new Set(cohort.map(stock => stock.symbol));
    const rate = cohort.length / data.stocks.length * 100;
    const name = draft ? `Draft: ${$('filter-name').value.trim() || 'New filter'}` : filter.name;
    const percentage = value => `${Number(value.toFixed(1))}%`;
    $('capture-summary').textContent = `${name} · ${cohort.length} of ${data.stocks.length} stocks retained (${percentage(rate)} overall)`;
    $('capture-detail').textContent = 'Hover, tap or focus a bar to inspect retained stocks.';
    const svgNode = (tag, attributes = {}, text) => {
      const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
      for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
      if (text != null) node.textContent = text;
      return node;
    };
    const svg = svgNode('svg', { viewBox: '0 0 1120 330', role: 'img', 'aria-labelledby': 'capture-svg-title capture-svg-description' });
    svg.append(svgNode('title', { id: 'capture-svg-title' }, `Ranked filter capture for ${name}`),
      svgNode('desc', { id: 'capture-svg-description' }, 'Ten groups of twenty stocks, ordered from rank 1 to rank 200. Bar height is the percentage retained in each group. The dashed line shows overall retention.'));
    const left = 56, top = 30, width = 1044, height = 220, bottom = top + height;
    for (const tick of [0, 25, 50, 75, 100]) {
      const y = bottom - tick / 100 * height;
      svg.append(svgNode('line', { x1: left, x2: left + width, y1: y, y2: y, class: 'capture-grid' }),
        svgNode('text', { x: left - 12, y: y + 4, 'text-anchor': 'end', class: 'capture-axis' }, `${tick}%`));
    }
    const baselineY = bottom - rate / 100 * height;
    svg.append(svgNode('line', { x1: left, x2: left + width, y1: baselineY, y2: baselineY, class: 'capture-overall' }));
    for (let index = 0; index < 10; index++) {
      const start = index * 20 + 1, end = start + 19;
      const group = data.stocks.filter(stock => stock.rank >= start && stock.rank <= end);
      const captured = group.filter(stock => retained.has(stock.symbol)), pct = captured.length / group.length * 100;
      const center = left + (index + 0.5) * width / 10, barHeight = pct / 100 * height;
      const label = `Ranks ${start}–${end}: ${captured.length} of ${group.length} retained (${percentage(pct)})`;
      const details = `${label}${captured.length ? ' · ' + captured.map(stock => stock.symbol).join(', ') : ' · No stocks retained'}`;
      const bar = svgNode('g', { class: 'capture-bar', tabindex: '0', role: 'img', 'aria-label': details,
        'data-start': start, 'data-total': group.length, 'data-retained': captured.length, 'data-percent': pct });
      bar.append(svgNode('title', {}, details),
        svgNode('rect', { x: center - 39, y: top - 16, width: 78, height: height + 50, class: 'capture-hit-area' }),
        svgNode('rect', { x: center - 25, y: bottom - barHeight, width: 50, height: barHeight, rx: 5, class: 'capture-column' }),
        svgNode('text', { x: center, y: bottom - barHeight - 10, 'text-anchor': 'middle', class: 'capture-value' }, percentage(pct)),
        svgNode('text', { x: center, y: bottom + 26, 'text-anchor': 'middle', class: 'capture-axis' }, `${start}–${end}`));
      const inspect = () => { $('capture-detail').textContent = details; };
      bar.addEventListener('pointerenter', inspect);
      bar.addEventListener('focus', inspect);
      bar.addEventListener('click', inspect);
      svg.append(bar);
    }
    svg.append(svgNode('text', { x: left + width / 2, y: 316, 'text-anchor': 'middle', class: 'capture-axis' }, 'Original rank · Higher ranked → Lower ranked'));
    chart.append(svg);
  }
  function renderCards() {
    $('filter-cards').replaceChildren();
    for (const filter of filters()) {
      const s = stats(selected(filter));
      const button = element('button', null, 'filter-card');
      button.type = 'button';
      button.dataset.filterId = filter.id;
      button.setAttribute('aria-pressed', String(activeId === filter.id));
      const title = element('b', filter.name);
      title.append(element('span', filter.id === 'all' ? 'UNIVERSE' : filter.builtin ? 'APP DEFAULT' : 'CUSTOM', 'badge'));
      const count = element('span', String(s.count), 'card-count');
      count.append(element('small', 'stocks'));
      button.append(title, count, element('small', `${s.top20} in top 20 · ${s.top50} in top 50 · Avg rank ${s.avg}`));
      button.addEventListener('click', () => { activeId = filter.id; renderCards(); update(); });
      $('filter-cards').append(button);
    }
  }
  function describeRule(rule) {
    const field = fieldByKey.get(rule.field);
    if (rule.comparison) return `${field.label} ${comparisons[rule.comparison]} ${rule.values[0]}${field.unit === 'percent' ? '%' : field.unit === 'pp' ? ' pp' : ''}`;
    const values = rule.values.map(value => field.options.find(o => o.value === value)?.label || value).join(' / ');
    const timeframes = rule.field === 'support' ? ` (any ${rule.timeframes.map(key => data.timeframes.find(t => t.key === key).label).join(', ')})` : '';
    return `${field.label}: ${values}${timeframes}`;
  }
  function update() {
    const filter = active();
    const cohort = selected(filter), s = stats(cohort);
    $('active-name').textContent = filter.name;
    $('active-description').textContent = filter.rules.length
      ? filter.rules.map(describeRule).join(filter.operator === 'or' ? ' OR ' : ' · ')
      : all.description;
    $('edit-filter').hidden = $('delete-filter').hidden = !!filter.builtin;
    $('result-stats').replaceChildren();
    for (const [value, label] of [[s.count, 'Matching stocks'], [s.top20, 'Of original top 20'], [s.top50, 'Of original top 50'],
      [s.avg, 'Average original rank ↓'], [s.tags, 'Strong/Solid + Cheap/Fair']]) {
      const stat = element('div', null, 'stat');
      stat.append(element('b', String(value)), element('small', label));
      $('result-stats').append(stat);
    }
    const query = $('search').value.trim().toLowerCase();
    visibleStocks = cohort.filter(stock => searches.get(stock.symbol).includes(query));
    const sort = $('sort').value;
    visibleStocks.sort((a, b) => sort === 'symbol' ? a.symbol.localeCompare(b.symbol)
      : sort === 'rank-desc' ? b.rank - a.rank : a.rank - b.rank);
    for (const row of rows.values()) row.hidden = true;
    const tbody = document.querySelector('tbody');
    for (const stock of visibleStocks) { const row = rows.get(stock.symbol); row.hidden = false; tbody.append(row); }
    $('count').textContent = `${visibleStocks.length} of ${s.count} matching stocks · ${data.stocks.length} total`;
    $('empty-results').hidden = visibleStocks.length > 0;
    $('export-results').disabled = !visibleStocks.length;
    renderCapture();
  }
  function newRule(fieldKey = 'revenue') {
    const field = fieldByKey.get(fieldKey);
    return { field: fieldKey, values: field.options.length ? [field.options[0].value] : ['0'],
      ...(!field.options.length ? { comparison: 'gte' } : {}),
      ...(fieldKey === 'support' ? { values: ['At Support', 'Near Support'], timeframes: data.timeframes.map(t => t.key) } : {}) };
  }
  function preview() {
    const error = validate(draft);
    $('preview-count').textContent = error || `${selected(draft).length} of ${data.stocks.length} stocks match these conditions`;
    $('form-error').hidden = true;
    renderCapture();
  }
  function checkboxGroup(legend, options, checkedValues, onChange, name) {
    const group = element('fieldset', null, 'check-options');
    group.append(element('legend', legend));
    for (const item of options) {
      const label = element('label'), input = document.createElement('input');
      input.type = 'checkbox'; input.checked = checkedValues.includes(item.value); input.value = item.value;
      input.setAttribute('aria-label', `${name}: ${item.label}`);
      input.addEventListener('change', () => {
        onChange(Array.from(group.querySelectorAll('input:checked'), node => node.value)); preview();
      });
      label.append(input, document.createTextNode(item.label)); group.append(label);
    }
    return group;
  }
  function renderRules() {
    $('rules').replaceChildren();
    draft.rules.forEach((rule, index) => {
      const field = fieldByKey.get(rule.field), condition = element('div', null, 'condition');
      const heading = element('div', null, 'condition-heading');
      const fieldLabel = element('label', `Condition ${index + 1}`), fieldSelect = element('select');
      fieldSelect.setAttribute('aria-label', `Condition ${index + 1} metric`);
      for (const item of data.fields) fieldSelect.append(option(item.key, item.label));
      fieldSelect.value = rule.field;
      fieldSelect.addEventListener('change', () => { draft.rules[index] = newRule(fieldSelect.value); renderRules(); preview(); });
      fieldLabel.append(fieldSelect);
      const remove = element('button', 'Remove'); remove.type = 'button';
      remove.setAttribute('aria-label', `Remove condition ${index + 1}`);
      remove.addEventListener('click', () => { draft.rules.splice(index, 1); renderRules(); preview(); });
      heading.append(fieldLabel, remove); condition.append(heading);
      if (field.numeric) {
        const values = element('div', null, 'condition-value'), modeLabel = element('label', 'Comparison'), mode = element('select');
        mode.setAttribute('aria-label', `Condition ${index + 1} comparison`);
        if (field.options.length) mode.append(option('label', 'Matches label'));
        for (const [key, label] of Object.entries(comparisons)) mode.append(option(key, label));
        mode.value = rule.comparison || 'label';
        mode.addEventListener('change', () => {
          if (mode.value === 'label') { delete rule.comparison; rule.values = [field.options[0].value]; }
          else { const previous = rule.comparison ? rule.values[0] : '0'; rule.comparison = mode.value; rule.values = [previous]; }
          renderRules(); preview();
        });
        modeLabel.append(mode); values.append(modeLabel);
        if (rule.comparison) {
          const valueLabel = element('label', `Value${field.unit === 'percent' ? ' (%)' : field.unit === 'pp' ? ' (pp)' : ''}`);
          const input = document.createElement('input'); input.type = 'number';
          input.step = field.unit === 'count' ? '1' : 'any';
          if (field.unit === 'count') input.min = '0';
          input.required = true; input.value = rule.values[0];
          input.setAttribute('aria-label', `Condition ${index + 1} value`);
          input.addEventListener('input', () => { rule.values = [input.value]; preview(); });
          valueLabel.append(input); values.append(valueLabel);
        }
        condition.append(values);
      }
      if (!rule.comparison) condition.append(checkboxGroup('Match any selected value', field.options, rule.values,
        values => { rule.values = values; }, `Condition ${index + 1} value`));
      if (rule.field === 'support') condition.append(checkboxGroup('Match any selected timeframe',
        data.timeframes.map(t => ({ value: t.key, label: t.label })), rule.timeframes,
        values => { rule.timeframes = values; }, `Condition ${index + 1} timeframe`));
      $('rules').append(condition);
    });
    $('add-rule').disabled = draft.rules.length >= 20;
  }
  function openBuilder(source, editing = false) {
    editingId = editing ? source.id : null;
    draft = source ? clone(source) : { operator: 'and', rules: [newRule()] };
    $('filter-name').value = editing ? source.name : source && source.id !== 'all' ? `${source.name} copy` : '';
    $('rule-logic').value = draft.operator;
    $('builder-title').textContent = editing ? 'Edit filter' : 'Create filter';
    $('filter-builder').hidden = false;
    renderRules(); preview(); $('filter-name').focus();
  }
  function closeBuilder() { $('filter-builder').hidden = true; draft = null; editingId = null; renderCapture(); }
  $('filter-name').addEventListener('input', () => { if (draft) renderCapture(); });
  $('new-filter').addEventListener('click', () => openBuilder());
  $('customize-filter').addEventListener('click', () => openBuilder(active().id === 'all' ? null : active()));
  $('edit-filter').addEventListener('click', () => openBuilder(active(), true));
  $('close-builder').addEventListener('click', closeBuilder);
  $('add-rule').addEventListener('click', () => { draft.rules.push(newRule()); renderRules(); preview(); });
  $('rule-logic').addEventListener('change', () => { draft.operator = $('rule-logic').value; preview(); });
  $('filter-form').addEventListener('submit', event => {
    event.preventDefault();
    const name = $('filter-name').value.trim();
    const error = !name ? 'Enter a filter name.' : validate(draft)
      || (filters().some(f => f.id !== editingId && f.name.toLowerCase() === name.toLowerCase()) ? 'Choose a unique filter name.' : '')
      || (!editingId && customFilters.length >= 30 ? 'You can save up to 30 custom filters. Delete one to make room.' : '');
    if (error) { $('form-error').textContent = error; $('form-error').hidden = false; return; }
    const id = editingId || `custom:${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
    const saved = { id, name, operator: draft.operator, rules: clone(draft.rules) };
    customFilters = editingId ? customFilters.map(f => f.id === editingId ? saved : f) : [...customFilters, saved];
    persist(); activeId = id; closeBuilder(); renderCards(); update();
  });
  $('delete-filter').addEventListener('click', () => {
    const filter = active();
    if (filter.builtin || !window.confirm(`Delete “${filter.name}”?`)) return;
    customFilters = customFilters.filter(f => f.id !== filter.id);
    persist(); activeId = 'all'; closeBuilder(); renderCards(); update();
  });
  $('search').addEventListener('input', update);
  $('sort').addEventListener('change', update);
  $('export-results').addEventListener('click', () => {
    const csvCell = value => `"${String(value ?? '').replace(/"/g, '""')}"`;
    const csvRows = [['Original rank', 'Stock', 'Business quality', 'Valuation', 'Revenue growth YoY (%)', 'Operating margin (%)', 'Red flags', 'Green flags', 'Rationale'],
      ...visibleStocks.map(stock => [stock.rank, stock.symbol, stock.business_quality, stock.valuation, stock.metrics.revenue.value,
        stock.metrics.operating_margin.value, stock.metrics.red_flag_count.value, stock.metrics.green_flag_count.value, stock.rationale])];
    const url = URL.createObjectURL(new Blob(['\uFEFF', csvRows.map(row => row.map(csvCell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' }));
    const link = element('a'); link.href = url;
    link.download = `${active().name.replace(/[^a-z0-9_-]/gi, '-').toLowerCase()}-ranking.csv`;
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $('financial-date').textContent = data.evaluatedOn;
  $('quote-date').textContent = (data.quoteDates || []).join(', ');
  // Fail visibly if projection or rule semantics ever drift from the app defaults.
  for (const preset of presets) {
    if (JSON.stringify(selected(preset).map(stock => stock.symbol)) !== JSON.stringify(preset.symbols))
      throw new Error(`Default filter differs from app: ${preset.name}`);
  }
  renderCards(); update();
})();
