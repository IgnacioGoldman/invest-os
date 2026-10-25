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

const { simulationTradeHistory, simulationAnalysisHistory }=require('../src/portfolioSimulation.ts');
test('trade history includes only executed strategy buys and sells, grouped newest first',()=>{
 const tx=(id,date,type='BUY',portfolio_id='strategy',time='20:00:00')=>({id,execution_date:date,execution_timestamp:`${date}T${time}Z`,type,portfolio_id});
 const transactions=[tx('buy','2026-10-26'),tx('benchmark','2026-10-27','BUY','vwce'),tx('dividend','2026-10-27','DIVIDEND'),tx('split','2026-10-27','SPLIT'),tx('sell','2026-10-28','SELL'),tx('later-buy','2026-10-26','BUY','strategy','21:00:00')];
 const days=simulationTradeHistory({transactions});
 assert.deepEqual(days.map(d=>d.date),['2026-10-28','2026-10-26']);
 assert.deepEqual(days.flatMap(d=>d.trades.map(t=>t.id)),['sell','later-buy','buy']);
 assert.deepEqual(transactions.map(t=>t.id),['buy','benchmark','dividend','split','sell','later-buy']);
 assert.deepEqual(simulationTradeHistory({transactions:[]}),[]);
});
test('daily analysis joins deterministic picks and AI decisions by market session, including days without AI',()=>{
 const reviews=[{session:'2026-10-26',status:'success',candidates:['AAA','BBB']},{session:'2026-10-27',status:'missing_api_key',candidates:['CCC']},{session:'2026-10-28',status:'not_needed',candidates:[]}];
 const decisions=[{id:'buy',session:'2026-10-26',analysis_date:'2026-10-27T00:35:00Z',symbol:'AAA',action:'BUY'}, {id:'legacy',session:'2026-10-25',analysis_date:'2026-10-25T22:35:00Z',action:'HOLD'}];
 const days=simulationAnalysisHistory({reviews,decisions});
 assert.deepEqual(days.map(d=>d.date),['2026-10-28','2026-10-27','2026-10-26','2026-10-25']);
 assert.deepEqual(days[2].review.candidates,['AAA','BBB']);assert.equal(days[2].decisions[0].id,'buy');
 assert.deepEqual(days[1].review.candidates,['CCC']);assert.equal(days[1].decisions.length,0);
 assert.equal(days[3].review,undefined);assert.equal(days[3].decisions[0].id,'legacy');
 assert.deepEqual(simulationAnalysisHistory({reviews:[],decisions:[]}),[]);
});
