const { test }=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const ts=require('typescript');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);
const { comparisonPoints,simulationIsStale,simulationMoney,simulationPercent }=require('../src/portfolioSimulation.ts');
const published=JSON.parse(fs.readFileSync(path.join(__dirname,'../public/data/simulation/index.json'),'utf8'));
test('published simulation begins with real activation baseline and no fabricated history',()=>{
 assert.equal(published.schema_version,1);assert.equal(published.metadata.currency,'EUR');assert.equal(published.metadata.initial_capital,10000);
 const points=comparisonPoints(published);assert.ok(points.length>0);
 assert.equal(points[0].date,published.metadata.start_date);assert.equal(points[0].strategy.equity,10000);assert.equal(points[0].vwce.equity,10000);
 for(const point of points)assert.ok(point.date>=published.metadata.start_date);
 for(const t of published.transactions)assert.ok(t.execution_date>published.metadata.start_date);
 assert.equal(published.ai_costs.deducted_from_returns,false);assert.equal(published.ai_costs.net_economic_return,null);
});
test('chart aligns recorded dates, sorts chronologically and never replaces missing values with zero',()=>{
 const snapshots=[{date:'2026-10-26',portfolio_id:'strategy',equity:11000},{date:'2026-10-25',portfolio_id:'vwce',equity:10000},{date:'2026-10-25',portfolio_id:'strategy',equity:10000},{date:'2026-10-27',portfolio_id:'vwce',equity:NaN}];
 const points=comparisonPoints({snapshots});assert.deepEqual(points.map(p=>p.date),['2026-10-25']);
 assert.equal(points[0].strategy.equity,10000);assert.equal(points[0].vwce.equity,10000);
 snapshots.push({date:'2026-10-26',portfolio_id:'vwce',equity:10500});assert.equal(comparisonPoints({snapshots})[1].strategy.equity,11000);
});
test('stale update detection and signed return formatting remain explicit',()=>{
 const metadata={activated_at:'2026-10-24T18:00:00Z',latest_successful_update:null};
 assert.equal(simulationIsStale(metadata,Date.parse('2026-10-25T18:00:00Z')),false);
 assert.equal(simulationIsStale(metadata,Date.parse('2026-10-29T18:00:00Z')),true);
 assert.ok(simulationPercent(5).startsWith('+'));assert.ok(simulationPercent(-5).startsWith('-'));assert.equal(simulationPercent(null),'—');
 assert.match(simulationMoney(10000),/10.*000/);assert.match(simulationMoney(12,'GBp'),/GBp/);
});
