"""Fixed V1 entry/hold/exit rules. AI supplies assessments, never trades or amounts."""
from __future__ import annotations
from datetime import date, datetime, timezone, timedelta
from app.config import get_settings
from app.services.screening_metrics import build_screening_metrics, number
from app.services.simulation.accounting import MAX_ALLOCATION, MAX_POSITIONS, book, valuation, digest

STRATEGY_VERSION = '1.0.0'
ANALYSIS_VERSION = '2.0.0'


def forward_pe_classification(value) -> str:
    """Original InvestOS 18/25/35/50 research bands; 25–35 remains unclear."""
    n=number(value)
    if n is None or n<=0: return 'Unknown'
    return 'Cheap' if n<=18 else 'Fair' if n<=25 else 'Expensive' if n>=35 else 'Unknown'


def screen_stock(snapshot: dict, today: date) -> dict:
    projection=build_screening_metrics(snapshot,today)
    m=projection['metrics'];r=m['revenue'];op=m['operating_margin'];f=m['forward_pe'];risk=m['red_flag_count']
    strength=r.get('strength','Unknown') if r.get('validated') else 'Unknown'
    margin=number(op.get('value')) if op.get('validated') else None
    forward=forward_pe_classification(f.get('value'))
    count=number(risk.get('value')) if risk.get('validated') and risk.get('coverage',{}).get('complete') else None
    # These are the same projected values and conditions as the existing filter
    # engine, with the preserved research-only forward-P/E gate added for V1.
    from app.services.simulation.screening import screen_expression_matches
    eligible=screen_expression_matches({**snapshot,'screening':projection},today) and forward in {'Cheap','Fair'}
    reasons=[]
    if strength not in {'Strong','Solid'}: reasons.append('Revenue strength is not Strong or Solid, or is unavailable.')
    if margin is None or margin<=0: reasons.append('Positive validated operating margin is required.')
    if forward not in {'Cheap','Fair'}: reasons.append('A fresh, sourced annual forward EPS estimate with Cheap/Fair forward P/E is required.')
    if count != 0: reasons.append('A complete current zero-red-flag assessment is required.')
    return {'symbol':snapshot['ticker'],'name':snapshot.get('name') or snapshot['ticker'],'eligible':eligible,'reasons':reasons,
            'revenue_strength':strength,'operating_margin':margin,'forward_pe_class':forward,'red_flags':count,
            'financial_as_of':r.get('as_of'),'price_as_of':f.get('price_as_of'),
            'metrics':m,'projection':projection,'currency':snapshot.get('price_currency')}


def select_candidates(screens: list[dict], held: set[str], pending: set[str]) -> list[dict]:
    return sorted((s for s in screens if s['eligible'] and s['symbol'] not in held|pending),
                  key=lambda s:(s['forward_pe_class']!='Cheap',s['revenue_strength']!='Strong',-s['operating_margin'],s['symbol']))[:20]


def evidence_sufficient(assessment: dict | None, symbol: str, registry: dict) -> bool:
    if not assessment or len(assessment['explanation'].strip())<20: return False
    refs={e['reference_id'] for e in assessment['evidence'] if len(e['explanation'].strip())>=10}
    return len(refs)>=2 and all(r in registry and registry[r]['symbol']==symbol for r in refs)


def current_inputs(screen: dict, now: str) -> bool:
    today=datetime.fromisoformat(now).date()
    if any(not screen['metrics'][k].get('validated') or (screen['metrics'][k].get('valid_until') or '') < today.isoformat() for k in ('revenue','operating_margin','red_flag_count')):
        return False
    f=screen['metrics']['forward_pe']
    try:
        return all(0 <= (today-date.fromisoformat(f[k][:10])).days <= 7 for k in ('price_as_of','estimate_as_of'))
    except (TypeError,ValueError,KeyError): return False


def deteriorating(screen: dict) -> bool:
    return screen['revenue_strength']=='Weak' or screen['operating_margin'] is not None and screen['operating_margin']<0


def replacement_eligible(screen: dict) -> bool:
    reliable=screen['revenue_strength']!='Unknown' and screen['operating_margin'] is not None and screen['forward_pe_class']!='Unknown' and screen['red_flags'] is not None
    return reliable and (screen['forward_pe_class']=='Expensive' or screen['red_flags']>0
                        or screen['revenue_strength'] not in {'Strong','Solid'} or screen['operating_margin']<=0)


def decision(state: dict, session: str, symbol: str | None, action: str, reason: str, now: str, assessment=None, screen=None) -> dict:
    request=state['sessions'][session].get('request') or {}
    usage=next((u for u in state['ai_usage'] if u['id']==request.get('id')), {})
    row={'id':f'decision:{session}:{symbol or "portfolio"}', 'session':session,'analysis_date':now,'symbol':symbol,
         'action':action,'explanation':reason,'model':usage.get('model') or request.get('model') or get_settings().gemini_model,'analysis_version':ANALYSIS_VERSION,'strategy_version':STRATEGY_VERSION,
         'assessment':assessment,'execution_status':'no_transaction','financial_as_of':screen.get('financial_as_of') if screen else None,
         'market_cutoff':session,'metrics':{k:screen[k] for k in ('revenue_strength','operating_margin','forward_pe_class','red_flags')} if screen else None,
         'red_flag_ids':[f['id'] for f in screen['metrics']['red_flag_count']['flags']] if screen else []}
    state['investment_decisions'].append(row)
    return row


def order(state: dict, d: dict, screen: dict, side: str, now: str, *, position_id=None,budget=0.,depends_on=None,replacement_symbol=None) -> dict:
    o={'id':f"order:{d['session']}:{screen['symbol']}:{side}",'portfolio_id':'strategy','symbol':screen['symbol'],'name':screen['name'],
       'type':side,'currency':screen['currency'],'decision_timestamp':now,'market_cutoff':d['session'],'decision_id':d['id'],
       'rationale':d['explanation'],'status':'pending','position_id':position_id,'budget_eur':budget,
       'depends_on':depends_on,'replacement_symbol':replacement_symbol}
    state['orders'].append(o);d['execution_status']='pending'
    return o


def apply_decisions(state: dict, session: str, screens: dict, review: dict | None, registry: dict, now: str) -> None:
    record=state['sessions'][session]
    if record.get('decisions_applied'): return
    holdings=[p for p in book(state,'strategy')['positions'] if p['status']=='open']
    assessments={a['symbol']:a for a in review['assessments']} if review else {}
    candidates=record.get('candidates',[])
    ranked=review['ranked_candidates'] if review else []
    permitted=[s for s in ranked if s in candidates and screens[s]['eligible'] and assessments[s]['investment_assessment']=='compelling'
               and current_inputs(screens[s],now) and evidence_sufficient(assessments[s],s,registry)
               and any(registry[e['reference_id']]['metric'] in {'revenue','operating_margin'} for e in assessments[s]['evidence'])
               and any(registry[e['reference_id']]['metric']=='forward_pe' for e in assessments[s]['evidence'])]
    pending={o['symbol'] for o in state['orders'] if o['status']=='pending' and o['portfolio_id']=='strategy'}
    used=set(pending)|{p['symbol'] for p in holdings};sells=0
    equity=valuation(state,'strategy',session)['equity']
    cash=book(state,'strategy')['cash']-sum(o['budget_eur'] for o in state['orders'] if o['status']=='pending' and o['type']=='BUY' and o['portfolio_id']=='strategy' and not o.get('depends_on'))
    for p in sorted(holdings,key=lambda p:p['symbol']):
        symbol=p['symbol'];a=assessments.get(symbol);s=screens.get(symbol)
        if not review or not s or symbol in pending or not evidence_sufficient(a,symbol,registry):
            decision(state,session,symbol,'HOLD','Retain the position: no validated review or sufficient evidence for a permitted exit; existing pending instructions are preserved.',now,a,s);continue
        if a['thesis_status']=='broken' and deteriorating(s):
            cause='revenue' if s['revenue_strength']=='Weak' else 'operating_margin'
            if s['metrics'][cause].get('validated') and (s['metrics'][cause].get('valid_until') or '')>=now[:10] and any(registry[e['reference_id']].get('metric')==cause for e in a['evidence']):
                d=decision(state,session,symbol,'SELL','Thesis broken with confirmed business deterioration. '+a['explanation'],now,a,s)
                order(state,d,s,'SELL',now,position_id=p['id']);sells+=1;continue
        comparison=next((c for c in review['comparisons'] if c['holding_symbol']==symbol and c['materially_better']
                         and c['candidate_symbol'] in permitted and c['candidate_symbol'] not in used
                         and len(c['explanation'].strip())>=20 and len({e['reference_id'] for e in c['evidence']})>=2
                         and {registry[e['reference_id']]['symbol'] for e in c['evidence']}=={symbol,c['candidate_symbol']}),None)
        if replacement_eligible(s) and current_inputs(s,now) and a['thesis_status'] in {'deteriorating','broken'} and comparison:
            new=screens[comparison['candidate_symbol']]
            d=decision(state,session,symbol,'REPLACE','Replace after documented deterioration and a materially superior qualifying alternative. '+comparison['explanation'],now,a,s)
            sell=order(state,d,s,'SELL',now,position_id=p['id'],replacement_symbol=new['symbol'])
            order(state,d,new,'BUY',now,budget=equity*MAX_ALLOCATION,depends_on=sell['id'])
            used.add(new['symbol']);continue
        decision(state,session,symbol,'HOLD','Hold while no fully evidenced V1 exit is justified. '+a['explanation'],now,a,s)
    slots=MAX_POSITIONS-len(holdings)+sells-sum(o['status']=='pending' and o['type']=='BUY' and o['portfolio_id']=='strategy' and not o.get('depends_on') for o in state['orders'])
    for symbol in ranked:
        if symbol not in candidates: continue
        a=assessments[symbol];s=screens[symbol]
        if symbol in permitted and symbol not in used and slots>0 and cash>0:
            budget=min(cash,equity*MAX_ALLOCATION)
            d=decision(state,session,symbol,'BUY','Passes the V1 screen with a compelling, evidenced investment case. '+a['explanation'],now,a,s)
            order(state,d,s,'BUY',now,budget=budget);slots-=1;cash-=budget;used.add(symbol)
        elif symbol not in used:
            decision(state,session,symbol,'NO_ACTION','Not selected: the investment case, evidence, capacity or available cash does not meet every BUY requirement. '+a['explanation'],now,a,s)
    if not review or not holdings and not ranked:
        decision(state,session,None,'NO_ACTION',record.get('analysis_message') or 'No qualifying companies; available capital remains cash.',now)
    record['decisions_applied']=True
