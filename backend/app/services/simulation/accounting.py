"""One ledger/accounting engine for strategy and benchmark; all values in EUR."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, date, timedelta, time, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_DOWN
import hashlib
import json
import math

CAPITAL = 10000.0
FEE_RATE = .001
MAX_POSITIONS = 4
MAX_ALLOCATION = .25


def amount(value) -> float:
    value = float(Decimal(str(value)).quantize(Decimal('.00000001')))
    if not math.isfinite(value): raise ValueError('Nonfinite accounting amount')
    return value


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def append_transaction(state: dict, transaction: dict) -> dict:
    ledger = state['transactions']
    existing = next((t for t in ledger if t['id'] == transaction['id']), None)
    if existing:
        if any(existing.get(k) != v for k,v in transaction.items()): raise ValueError('Conflicting transaction identifier')
        return existing
    t = {**transaction, 'previous_hash': ledger[-1]['hash'] if ledger else None}
    t['hash'] = digest(t)
    ledger.append(t)
    return t


def verify_ledger(state: dict) -> None:
    previous, ids, last_date = None, set(), ''
    for row in state['transactions']:
        content = {k:v for k,v in row.items() if k != 'hash'}
        if (row['id'] in ids or row['previous_hash'] != previous or digest(content) != row['hash']
                or row['execution_date'] < last_date): raise ValueError('Invalid ledger chain or chronology')
        ids.add(row['id']);previous=row['hash'];last_date=row['execution_date']
    for portfolio in ('strategy','vwce'):
        if book(state,portfolio)['cash'] < -1e-7: raise ValueError('Negative portfolio cash')


def book(state: dict, portfolio: str, through: str | None = None) -> dict:
    cash = state['metadata']['initial_capital']
    positions = {}
    fees, dividends = 0., 0.
    for t in state['transactions']:
        if t['portfolio_id'] != portfolio or through and t['execution_date'] > through: continue
        cash = amount(cash + t['net_cash_eur']); fees = amount(fees + t['fees_eur'])
        if t['type'] == 'BUY':
            p = positions.setdefault(t['position_id'], {'id':t['position_id'],'portfolio_id':portfolio,
                'symbol':t['symbol'],'name':t['name'],'currency':t['price_currency'],'status':'open',
                'entry_date':t['execution_date'],'exit_date':None,'quantity':0.,'cost_basis':0.,
                'invested_capital':0.,'sale_proceeds':0.,'realized_pnl':0.,'dividends':0.,'fees':0.,
                'entry_price':t['execution_price'],'purchase_original':0.,'purchased_quantity':0.,'exit_price':None,'transactions':[],
                'entry_reason':t['rationale'],'exit_reason':None,'replacement_for':t.get('replacement_for'),
                'replaced_by':None})
            p['purchase_original'] += t['gross_original_currency'];p['purchased_quantity'] += t['quantity']
            p['entry_price']=p['purchase_original']/p['purchased_quantity']
            p['quantity'] += t['quantity'];p['cost_basis']=amount(p['cost_basis']-t['net_cash_eur'])
            p['invested_capital']=amount(p['invested_capital']-t['net_cash_eur'])
            p['fees']=amount(p['fees']+t['fees_eur']);p['transactions'].append(t['id'])
        elif t['position_id'] in positions:
            p=positions[t['position_id']];p['transactions'].append(t['id'])
            if t['type']=='SELL':
                if t['quantity'] > p['quantity']+1e-10: raise ValueError('Sale exceeds owned quantity')
                basis=amount(p['cost_basis']*t['quantity']/p['quantity'])
                p['realized_pnl']=amount(p['realized_pnl']+t['net_cash_eur']-basis)
                p['cost_basis']=amount(p['cost_basis']-basis);p['quantity']=max(0.,p['quantity']-t['quantity'])
                p['sale_proceeds']=amount(p['sale_proceeds']+t['net_cash_eur']);p['fees']=amount(p['fees']+t['fees_eur'])
                if p['quantity'] < 1e-10:
                    p.update(status='closed',exit_date=t['execution_date'],exit_price=t['execution_price'],exit_reason=t['rationale'],replaced_by=t.get('replacement_symbol'))
            elif t['type']=='SPLIT':
                p['quantity'] *= t['split_ratio'];p['purchased_quantity'] *= t['split_ratio'];p['entry_price']/=t['split_ratio']
            elif t['type']=='DIVIDEND':
                p['dividends']=amount(p['dividends']+t['net_cash_eur']);dividends=amount(dividends+t['net_cash_eur'])
    return {'cash':cash,'positions':list(positions.values()),'fees':fees,'dividends':dividends,
            'realized_pnl':amount(sum(p['realized_pnl'] for p in positions.values()))}


def latest_mark(market: dict, symbol: str, session: str, cutoff_timestamp: str | None = None) -> dict | None:
    candidates=[m for d,m in market.get(symbol,{}).items() if d <= session and valid_mark(m) and (not cutoff_timestamp or m['close_timestamp'] <= cutoff_timestamp)]
    return max(candidates,key=lambda m:m['date']) if candidates else None


def valid_mark(mark: dict | None) -> bool:
    return bool(mark and mark.get('source') and mark.get('fx_source') and mark.get('date') and mark.get('fx_date')
                and mark['fx_date'] <= mark['date'] and mark.get('currency')
                and all(isinstance(mark.get(k),(int,float)) and not isinstance(mark.get(k),bool) and math.isfinite(mark[k]) and mark[k]>0 for k in ('close','fx_to_eur')))


def valuation(state: dict, portfolio: str, session: str, cutoff_timestamp: str | None = None) -> dict:
    b=book(state,portfolio,session);invested,unrealized,stale=0.,0.,[]
    for p in b['positions']:
        if p['status'] != 'open': continue
        mark=latest_mark(state['market_data'],p['symbol'],session,cutoff_timestamp)
        if not mark: raise ValueError('An owned position has no historical valuation price')
        adjusted_price=mark['close']
        for t in state['transactions']:
            if t['position_id']==p['id'] and t['type']=='SPLIT' and mark['date'] < t['execution_date'] <= session:
                adjusted_price/=t['split_ratio']
        fx={'rate':mark['fx_to_eur'],'date':mark['fx_date'],'source':mark['fx_source']}
        if mark['currency']=='EUR':fx={'rate':1.,'date':session,'source':'fx:EUR/EUR:identity'}
        rates=[]
        for d,rate in state.get('fx_rates',{}).get(mark['currency'],{}).items():
            published=datetime.combine(date.fromisoformat(d),time(16),ZoneInfo('Europe/Berlin')).astimezone(timezone.utc).isoformat()
            if d<=session and (not cutoff_timestamp or published<=cutoff_timestamp):rates.append(rate)
        if rates:fx=max(rates,key=lambda r:r['date'])
        p.update(current_price=adjusted_price,price_date=mark['date'],fx_to_eur=fx['rate'],fx_date=fx['date'],fx_source=fx['source'])
        p['market_value']=amount(p['quantity']*adjusted_price*fx['rate'])
        p['unrealized_pnl']=amount(p['market_value']-p['cost_basis'])
        p['unrealized_return_pct']=p['unrealized_pnl']/p['cost_basis']*100 if p['cost_basis'] else None
        p['total_return_pct']=(p['market_value']+p['sale_proceeds']+p['dividends']-p['invested_capital'])/p['invested_capital']*100 if p['invested_capital'] else None
        invested+=p['market_value'];unrealized+=p['unrealized_pnl']
        if mark['date'] != session: stale.append(p['symbol'])
    equity=amount(b['cash']+invested)
    return {**b,'date':session,'portfolio_id':portfolio,'invested_value':amount(invested),'equity':equity,
            'unrealized_pnl':amount(unrealized),'cumulative_return_pct':(equity/state['metadata']['initial_capital']-1)*100,
            'stale_symbols':stale,'valuation_complete':not stale}


def execution_price(state: dict, order: dict, session: str) -> dict | None:
    mark=state['market_data'].get(order['symbol'],{}).get(session)
    if not valid_mark(mark) or mark['currency'] != order['currency'] or session <= order['market_cutoff']: return None
    if datetime.fromisoformat(mark['close_timestamp']) <= datetime.fromisoformat(order['decision_timestamp']): return None
    return mark


def execute_orders(state: dict, session: str) -> None:
    # Chronological exchange closes prevent a European purchase spending a
    # US sale that has not happened yet. Sales win only at the same timestamp.
    def execution_order(o):
        mark=execution_price(state,o,session) if o['status']=='pending' else None
        return (mark['close_timestamp'] if mark else 'z',o['type']!='SELL',o['decision_timestamp'],o['id'])
    for order in sorted(state['orders'],key=execution_order):
        if order['status'] != 'pending': continue
        mark=execution_price(state,order,session)
        if not mark: continue
        if order['portfolio_id']=='vwce' and not state.get('benchmark',{}).get('verified'): continue
        if order.get('depends_on'):
            parent=next(o for o in state['orders'] if o['id']==order['depends_on'])
            if parent['status']!='executed': continue
        b=book(state,order['portfolio_id']);open_positions=[p for p in b['positions'] if p['status']=='open']
        unit=Decimal(str(mark['close']))*Decimal(str(mark['fx_to_eur']))
        if order['type']=='BUY':
            if any(p['symbol']==order['symbol'] for p in open_positions) or order['portfolio_id']=='strategy' and len(open_positions)>=MAX_POSITIONS:
                order.update(status='cancelled',failure='Position already held or position limit reached.');continue
            equity=valuation(state,order['portfolio_id'],session,mark['close_timestamp'])['equity']
            budget=min(b['cash'],order['budget_eur'],equity*(MAX_ALLOCATION if order['portfolio_id']=='strategy' else 1))
            quantity=(Decimal(str(max(0,budget)))/(unit*(1+Decimal(str(FEE_RATE))))).quantize(Decimal('.000000000001'),rounding=ROUND_DOWN)
            if quantity<=0: order.update(status='cancelled',failure='Insufficient cash.');continue
            position_id=order['id']
        else:
            position=next((p for p in open_positions if p['id']==order['position_id']),None)
            if not position: order.update(status='cancelled',failure='Position is no longer open.');continue
            quantity=Decimal(str(position['quantity']));position_id=position['id']
        gross=amount(quantity*unit);fee=amount(Decimal(str(gross))*Decimal(str(FEE_RATE)))
        cash=amount(-gross-fee if order['type']=='BUY' else gross-fee)
        if order['type']=='BUY' and -cash>b['cash']+1e-8: raise ValueError('Purchase exceeds available cash')
        t={'id':f"tx:{order['id']}",'portfolio_id':order['portfolio_id'],'symbol':order['symbol'],'name':order['name'],
           'type':order['type'],'decision_date':order['decision_timestamp'][:10],'decision_timestamp':order['decision_timestamp'],'decision_market_cutoff':order['market_cutoff'],
           'execution_date':session,'execution_timestamp':mark['close_timestamp'],'execution_price':mark['close'],
           'price_currency':mark['currency'],'fx_to_eur':mark['fx_to_eur'],'fx_date':mark['fx_date'],'fx_source':mark['fx_source'],
           'price_source':mark['source'],'quantity':float(quantity),'gross_original_currency':amount(quantity*Decimal(str(mark['close']))),
           'gross_eur':gross,'fees_eur':fee,'net_cash_eur':cash,'position_id':position_id,'decision_id':order['decision_id'],
           'realized_pnl_eur':amount(cash-position['cost_basis']*float(quantity)/position['quantity']) if order['type']=='SELL' else None,
           'replacement_for':order.get('depends_on'),'replacement_symbol':order.get('replacement_symbol'),'rationale':order['rationale']}
        append_transaction(state,t);order.update(status='executed',execution_date=session,transaction_id=t['id'])
        for decision in state['investment_decisions']:
            if decision['id']==order['decision_id']:
                decision['execution_status']='executed' if not any(o['status']=='pending' and o['decision_id']==decision['id'] for o in state['orders']) else 'partly_executed'


def apply_corporate_actions(state: dict, session: str) -> None:
    # Entitlement is determined before closing-price trades on the ex-date.
    for portfolio in ('strategy','vwce'):
        for p in book(state,portfolio,(date.fromisoformat(session)-timedelta(days=1)).isoformat())['positions']:
            if p['status']!='open': continue
            mark=state['market_data'].get(p['symbol'],{}).get(session)
            if not valid_mark(mark): continue
            if mark.get('unsupported_action'):
                raise ValueError('Unsupported corporate action requires reconciliation')
            quantity=p['quantity']
            for kind,key in [('SPLIT','split_ratio'),('DIVIDEND','dividend')]:
                value=mark.get(key,0)
                if not value or kind=='SPLIT' and value==1: continue
                if kind=='SPLIT' and value<=0 or kind=='DIVIDEND' and value<0: raise ValueError('Invalid corporate action')
                t={'id':f"{kind}:{p['id']}:{session}",'portfolio_id':portfolio,'symbol':p['symbol'],'name':p['name'],'type':kind,
                   'execution_date':session,'execution_timestamp':session+'T00:00:00+00:00','decision_timestamp':None,'decision_market_cutoff':None,
                   'execution_price':value if kind=='DIVIDEND' else 0,'price_currency':mark['currency'],
                   'fx_to_eur':mark['fx_to_eur'],'fx_date':mark['fx_date'],'fx_source':mark['fx_source'],'price_source':mark['source'],
                   'quantity':quantity,'split_ratio':value if kind=='SPLIT' else None,'gross_original_currency':amount(quantity*value) if kind=='DIVIDEND' else 0,
                   'gross_eur':amount(quantity*value*mark['fx_to_eur']) if kind=='DIVIDEND' else 0,'fees_eur':0,
                   'net_cash_eur':amount(quantity*value*mark['fx_to_eur']) if kind=='DIVIDEND' else 0,'position_id':p['id'],'decision_id':None,
                   'rationale':'Reported split; quantity adjusted, EUR cost basis unchanged.' if kind=='SPLIT' else 'Reported cash dividend credited on the ex-date (payment-date simplification).'}
                append_transaction(state,t)
                if kind=='SPLIT': quantity*=value


def record_snapshot(state: dict, session: str) -> None:
    for portfolio in ('strategy','vwce'):
        if any(s['date']==session and s['portfolio_id']==portfolio for s in state['portfolio_snapshots']): continue
        v=valuation(state,portfolio,session)
        previous=next((s for s in reversed(state['portfolio_snapshots']) if s['portfolio_id']==portfolio),None)
        state['portfolio_snapshots'].append({k:value for k,value in v.items() if k!='positions'} | {
            'daily_return_pct':(v['equity']/previous['equity']-1)*100 if previous and previous['equity'] else None})
    state['portfolio_snapshots'].sort(key=lambda s:(s['date'],s['portfolio_id']))


def performance(state: dict, portfolio: str) -> dict:
    points=[s for s in state['portfolio_snapshots'] if s['portfolio_id']==portfolio]
    peak=state['metadata']['initial_capital'];drawdown=0.
    for p in points:
        peak=max(peak,p['equity']);drawdown=min(drawdown,(p['equity']/peak-1)*100)
    latest=points[-1];days=(datetime.fromisoformat(latest['date'])-datetime.fromisoformat(state['metadata']['start_date'])).days
    annual=(latest['equity']/state['metadata']['initial_capital'])**(365.25/days)-1 if days>=365 and latest['equity']>0 else None
    return {**latest,'max_drawdown_pct':drawdown,'annualized_return_pct':annual*100 if annual is not None else None}
