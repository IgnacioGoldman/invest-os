"""Persistent forward-running sessions, accounting, review journal and static export."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, date, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
from app.config import get_settings
from app.services.simulation.accounting import CAPITAL, FEE_RATE, amount, book, digest, verify_ledger, record_snapshot, execute_orders, apply_corporate_actions, valuation, performance
from app.services.simulation.strategy import STRATEGY_VERSION, ANALYSIS_VERSION, screen_stock, select_candidates, apply_decisions
from app.services.simulation.analysis import build_payload, validate_review, call_gemini

BENCHMARK={'symbol':'VWCE.DE','name':'Vanguard FTSE All-World UCITS ETF (USD) Accumulating',
           'isin':'IE00BK5BQT80','currency':'EUR','exchange':'Xetra',
           'source':'https://www.vanguard.co.uk/professional/product/etf/equity/9679/ftse-all-world-ucits-etf-usd-accumulating',
           'verified':False}


def initialize(now: str) -> dict:
    start=datetime.fromisoformat(now).astimezone(ZoneInfo('Europe/Stockholm')).date().isoformat()
    state={'schema_version':1,'metadata':{'simulation_id':f'investos-v1-{start}','start_date':start,'activated_at':now,
        'initial_capital':CAPITAL,'currency':'EUR','strategy_version':STRATEGY_VERSION,'analysis_version':ANALYSIS_VERSION,
        'latest_successful_update':None,'last_successful_analysis':None,'last_attempt':None,'status':'initialized',
        'transaction_fee_rate':FEE_RATE,'return_basis':'Recorded cash dividends and split-adjusted quantities; taxes and additional execution costs excluded. Corporate-action coverage may be incomplete.',
        'ai_cost_treatment':'Investment returns include modeled trading fees. AI expenses are separate; returns are not net of AI operating expenses.'},
        'benchmark':dict(BENCHMARK),'transactions':[],'orders':[],'investment_decisions':[],
        'portfolio_snapshots':[],'sessions':{},'ai_usage':[],'market_data':{},'fx_rates':{},'errors':[]}
    state['orders'].append({'id':f'benchmark:{start}','portfolio_id':'vwce','symbol':BENCHMARK['symbol'],'name':BENCHMARK['name'],
        'type':'BUY','currency':'EUR','budget_eur':CAPITAL,'decision_timestamp':now,'market_cutoff':start,'decision_id':f'benchmark:{start}',
        'status':'pending','position_id':None,'rationale':'Passive accumulating VWCE buy-and-hold benchmark, first eligible session after activation.'})
    record_snapshot(state,start)
    return state


def load_state(path: Path) -> dict:
    state=json.loads(path.read_text());verify_ledger(state)
    if state.get('schema_version')!=1: raise ValueError('Unsupported simulation schema')
    return state


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    os.replace(temporary,path)


def save_state(path: Path,state: dict) -> None:
    verify_ledger(state);atomic_json(path,state)


def prepare(state: dict,snapshots: list[dict],market: dict,now: str,api_configured: bool) -> str | None:
    state['metadata']['last_attempt']=now
    state['metadata']['api_configured']=api_configured
    if market.get('benchmark'):
        info=market['benchmark']
        if info.get('verified') and info.get('symbol')==BENCHMARK['symbol'] and info.get('isin')==BENCHMARK['isin'] and info.get('currency')=='EUR':
            state['benchmark'].update(info)
    for currency,rates in market.get('fx_rates',{}).items():
        target=state.setdefault('fx_rates',{}).setdefault(currency,{})
        for d,rate in rates.items():
            if d<=now[:10]:target.setdefault(d,rate)
    for symbol,marks in market.get('prices',{}).items():
        saved=state['market_data'].setdefault(symbol,{})
        for d,mark in marks.items():
            if d>=state['metadata']['start_date'] and d<=now[:10]: saved.setdefault(d,mark)
    for error in market.get('errors',[]): state['errors'].append({'at':now,'stage':'market_data','message':error})
    days=sorted(d for d in market.get('session_dates',[]) if d>=state['metadata']['start_date'] and d<=now[:10])
    for session in days:
        existing=state['sessions'].get(session,{})
        if existing.get('accounted'): continue
        before=deepcopy(state)
        try:
            apply_corporate_actions(state,session)
            execute_orders(state,session)
            record_snapshot(state,session)
            state['sessions'].setdefault(session,{})['accounted']=True
        except Exception:
            state.clear();state.update(before)
            state['errors'].append({'at':now,'stage':'accounting','session':session,'message':'Accounting validation failed; prior ledger preserved. Inspect the workflow logs.'})
            state['metadata']['status']='accounting_error'
            raise
    if days:
        state['metadata']['latest_successful_update']=now
    if not days:
        state['metadata']['status']='awaiting_market_session'
        return None
    session=days[-1]
    record=state['sessions'].setdefault(session,{})
    if record.get('request') or record.get('decisions_applied'):
        return session
    today=datetime.fromisoformat(now).astimezone(ZoneInfo('Europe/Stockholm')).date()
    by_symbol={s['ticker']:s for s in snapshots}
    screens={}
    for symbol,snapshot in by_symbol.items():
        try:
            generated=datetime.fromisoformat(snapshot.get('generated_at','').replace('Z','+00:00'))
            if generated.tzinfo is None or generated>datetime.fromisoformat(now): continue
        except ValueError: continue
        screens[symbol]=screen_stock(snapshot,today)
    holdings=valuation(state,'strategy',session)['positions']
    holdings=[p for p in holdings if p['status']=='open']
    held={p['symbol'] for p in holdings}
    pending={o['symbol'] for o in state['orders'] if o['status']=='pending' and o['portfolio_id']=='strategy'}
    candidates=select_candidates(list(screens.values()),held,pending)
    record['screening']=[{k:s[k] for k in ('symbol','eligible','reasons','revenue_strength','operating_margin','forward_pe_class','red_flags','financial_as_of','price_as_of')} for s in sorted(screens.values(),key=lambda s:s['symbol'])]
    record['universe_count']=len(snapshots)
    record['unavailable_symbols']=sorted(set(by_symbol)-set(screens))
    record['candidates']=[s['symbol'] for s in candidates]
    for p in holdings:
        history=[d for d in state['investment_decisions'] if d['symbol']==p['symbol'] and d.get('assessment')]
        if history:
            p['thesis_status']=history[-1]['assessment']['thesis_status'];p['last_explanation']=history[-1]['explanation']
    if not candidates and not holdings:
        record.update(analysis_status='not_needed',analysis_message='No companies pass all reliable V1 entry conditions; uninvested capital remains cash.')
        apply_decisions(state,session,screens,None,{},now)
        state['metadata']['status']='current' if api_configured else 'awaiting_api_key'
        return session
    payload,registry=build_payload(by_symbol,record['candidates'],holdings,screens,session,now)
    selected=set(record['candidates'])|held
    record['request']={'id':f'{state["metadata"]["simulation_id"]}:{session}:{ANALYSIS_VERSION}',
        'model':get_settings().gemini_model,
        'status':'ready' if api_configured else 'missing_api_key','prepared_at':now,'payload':payload,'registry':registry,
        'input_hash':digest(payload),'screens':{symbol:screens[symbol] for symbol in selected if symbol in screens},'owner':None}
    record['analysis_status']=record['request']['status']
    state['metadata']['status']='analysis_pending' if api_configured else 'awaiting_api_key'
    return session


def claim(state: dict,session: str,owner: str,now: str) -> bool:
    request=state['sessions'].get(session,{}).get('request')
    if not request or request['status']!='ready': return False
    if (datetime.fromisoformat(now)-datetime.fromisoformat(request['prepared_at'])).total_seconds()>86400:
        request['status']='expired';state['sessions'][session]['analysis_status']='expired';return False
    request.update(status='attempted',owner=owner,attempted_at=now)
    state['ai_usage'].append({'id':request['id'],'session':session,'at':now,'status':'attempted','model':request.get('model') or get_settings().gemini_model,'usage':None,'estimated_cost_usd':None})
    state['sessions'][session]['analysis_status']='attempted'
    return True


def analyze(state: dict,session: str,owner: str,api_key: str,now: str,caller=call_gemini) -> bool:
    record=state['sessions'][session];request=record.get('request')
    if not api_key or not request or request['status']!='attempted' or request['owner']!=owner: return False
    try:
        # No retries: a paid attempt is journaled and committed BEFORE this call.
        raw,usage=caller(request,api_key)
        entry=next(u for u in state['ai_usage'] if u['id']==request['id'])
        entry.update(status='received',**usage)
        review=validate_review(raw,request)
        request.update(status='success',completed_at=now,review=review)
        entry['status']='success'
        record['analysis_status']='success';state['metadata']['last_successful_analysis']=now
        state['metadata']['status']='current'
        return True
    except Exception as error:
        # Never persist exception strings containing provider headers or API keys.
        request.update(status='failed',completed_at=now,error_type=type(error).__name__)
        record.update(analysis_status='failed',analysis_message='AI review failed validation or the API request failed; no new simulated orders were created.')
        for entry in state['ai_usage']:
            if entry['id']==request['id']:entry['status']='failed'
        if not any(u['id']==request['id'] for u in state['ai_usage']):
            state['ai_usage'].append({'id':request['id'],'session':session,'at':now,'status':'failed','model':request.get('model') or get_settings().gemini_model,'usage':None,'estimated_cost_usd':None})
        state['metadata']['status']='analysis_error'
        return False


def finalize(state: dict,session: str,now: str) -> None:
    record=state['sessions'][session];request=record.get('request')
    if not request: return
    if request['status']=='attempted':
        request.update(status='indeterminate')
        for usage in state['ai_usage']:
            if usage['id']==request['id']:usage['status']='indeterminate'
        record.update(analysis_status='indeterminate',analysis_message='A prior paid request may have started. It will not be retried automatically for this session.')
        state['metadata']['status']='analysis_error'
    if request['status']=='missing_api_key': record['analysis_message']='GEMINI_API_KEY is not configured. No AI request or new strategy orders were created.'
    review=request.get('review') if request['status']=='success' else None
    apply_decisions(state,session,request['screens'],review,request['registry'],now)


def validate_reconstruction(state: dict) -> None:
    verify_ledger(state)
    for snapshot in state['portfolio_snapshots']:
        actual=valuation(state,snapshot['portfolio_id'],snapshot['date'])
        for key in ('cash','invested_value','equity','realized_pnl','unrealized_pnl','fees'):
            if abs(actual[key]-snapshot[key])>1e-6: raise ValueError(f'Historical reconstruction mismatch: {snapshot["date"]} {key}')


def public_dashboard(state: dict) -> dict:
    latest=max(s['date'] for s in state['portfolio_snapshots'])
    portfolios={p:{**valuation(state,p,latest),'performance':performance(state,p)} for p in ('strategy','vwce')}
    decisions=state['investment_decisions']
    for portfolio in portfolios.values():
        for p in portfolio['positions']:
            rows=[d for d in decisions if d['symbol']==p['symbol'] and d.get('assessment')]
            p['replacement_of_symbol']=next((o['symbol'] for o in state['orders'] if o['id']==p.get('replacement_for')),None)
            p.update(thesis_status=rows[-1]['assessment']['thesis_status'] if rows else 'unknown',
                     last_assessment_date=rows[-1]['analysis_date'] if rows else None,
                     last_explanation=rows[-1]['assessment']['explanation'] if rows else None,
                     holding_days=(date.fromisoformat(p['exit_date'] or latest)-date.fromisoformat(p['entry_date'])).days,
                     realized_return_pct=(p['realized_pnl']+p['dividends'])/p['invested_capital']*100 if p['invested_capital'] else None)
    history=[]
    for d in decisions:
        assessment=d.get('assessment')
        history.append({**{k:v for k,v in d.items() if k!='assessment'},'assessment':assessment})
    usage=state['ai_usage']
    return {'schema_version':1,'metadata':state['metadata'],'benchmark':state['benchmark'],'portfolios':portfolios,
            'snapshots':state['portfolio_snapshots'],'transactions':state['transactions'],'orders':state['orders'],
            'decisions':history,'ai_usage':usage,'ai_costs':{'estimated_usd':amount(sum(u.get('estimated_cost_usd') or 0 for u in usage)),
                'complete':all(u.get('estimated_cost_usd') is not None for u in usage),'deducted_from_returns':False,'net_economic_return':None},
            'reviews':[{'session':s,'status':r.get('analysis_status'),'candidates':r.get('candidates',[]),'screened_count':len(r.get('screening',[])),
                        'eligible_count':sum(x['eligible'] for x in r.get('screening',[])),
                        'message':r.get('analysis_message')} for s,r in sorted(state['sessions'].items())],
            'recent_errors':state['errors'][-5:]}
