"""Existing free providers, extended for dated FX and explicit corporate actions."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import math
import requests
from app.services.simulation.engine import BENCHMARK

# Normal close is a conservative bound on early-close days. Unknown exchanges
# fail closed; actual dated candles determine holidays, never a weekday guess.
CLOSE_TIMES={'America/New_York':time(16),'Europe/Berlin':time(17,30),'Europe/Stockholm':time(17,30),
             'Europe/Amsterdam':time(17,30),'Europe/London':time(16,30)}


def finite(value,default=None):
    try: value=float(value)
    except (TypeError,ValueError): return default
    return value if math.isfinite(value) else default


def normalize_bars(frame,metadata: dict,symbol: str,now: datetime) -> dict:
    tz=metadata.get('exchangeTimezoneName') or str(frame.index.tz)
    if tz not in CLOSE_TIMES: raise ValueError('Unsupported exchange timezone')
    ccy=metadata.get('currency')
    if not ccy: raise ValueError('Quote currency is unavailable')
    # Yahoo Close is split-adjusted even with auto_adjust=False. Undo only the
    # later reported splits in the fetched window to recover as-traded units.
    future_splits=1.;records={}
    for index,row in reversed(list(frame.iterrows())):
        day=index.date().isoformat();local_close=datetime.combine(date.fromisoformat(day),CLOSE_TIMES[tz],ZoneInfo(tz))
        reported_end=(metadata.get('currentTradingPeriod') or {}).get('regular',{}).get('end')
        if reported_end:
            actual=datetime.fromtimestamp(reported_end,timezone.utc)
            if actual.astimezone(ZoneInfo(tz)).date()==date.fromisoformat(day): local_close=actual
        split=finite(row.get('Stock Splits'),0.)
        close=finite(row.get('Close'));dividend=finite(row.get('Dividends'),0.)
        if close is not None and close>0 and local_close<=now:
            records[day]={'date':day,'close':close*future_splits,'currency':ccy,
                'source':f'yfinance:history:{symbol}:Close:auto_adjust=False:as_traded',
                'close_timestamp':local_close.astimezone(timezone.utc).isoformat(),
                'split_ratio':split or 1.,'dividend':dividend*future_splits,
                'corporate_actions_available':'Stock Splits' in frame and 'Dividends' in frame,
                'unsupported_action':bool(finite(row.get('Capital Gains'),0.)),
                'observed_at':now.isoformat()}
        if split and split>0: future_splits*=split
    return records


def historical_fx(currency: str,start: str,end: str,session=requests) -> dict:
    if currency=='EUR': return {}
    base='GBP' if currency=='GBp' else currency
    response=session.get(f'https://api.frankfurter.dev/v1/{start}..{end}',params={'base':base,'symbols':'EUR'},timeout=30)
    response.raise_for_status();payload=response.json()
    if payload.get('base')!=base: raise ValueError('FX base currency mismatch')
    rates={}
    for d,values in payload.get('rates',{}).items():
        rate=finite(values.get('EUR'))
        if rate and rate>0: rates[d]={'rate':rate/100 if currency=='GBp' else rate,'date':d,'source':f'frankfurter:historical:{base}/EUR'+(':pence' if currency=='GBp' else '')}
    return rates


def benchmark_identity(info: dict) -> dict:
    name=str(info.get('longName') or info.get('shortName') or '').lower().replace('-','').replace(' ','')
    supplied_isin=info.get('isin')
    verified=(info.get('symbol')==BENCHMARK['symbol'] and info.get('currency')=='EUR' and info.get('quoteType')=='ETF'
              and info.get('exchange') in {'GER','XETRA','XETR'} and 'vanguard' in name and 'allworld' in name and 'acc' in name
              and (not supplied_isin or supplied_isin==BENCHMARK['isin']))
    return {**BENCHMARK,'verified':verified,'provider_name':info.get('longName') or info.get('shortName'),
            'verification':'Official Vanguard ISIN/listing mapping plus provider symbol, ETF type, name, currency and exchange.' if verified else 'Provider identity could not be verified.'}


def fetch_market(state: dict,now: str,ticker_factory=None) -> dict:
    if ticker_factory is None:
        import yfinance as yf
        ticker_factory=yf.Ticker
    clock=datetime.fromisoformat(now)
    latest=max(s['date'] for s in state['portfolio_snapshots'])
    start=min(latest,now[:10]);end=(date.fromisoformat(now[:10])+timedelta(days=1)).isoformat()
    symbols={'SPY',BENCHMARK['symbol']}
    for o in state['orders']:
        if o['status']=='pending': symbols.add(o['symbol'])
    from app.services.simulation.accounting import book
    for portfolio in ('strategy','vwce'):
        symbols.update(p['symbol'] for p in book(state,portfolio)['positions'] if p['status']=='open')
    prices={};errors=[];benchmark=None
    def collect(symbol):
        ticker=ticker_factory(symbol)
        info=ticker.get_info()
        frame=ticker.history(start=start,end=end,interval='1d',auto_adjust=False,back_adjust=False,actions=True,repair=False,timeout=25)
        if frame is None or frame.empty: return symbol,{},info
        metadata={**info,**(ticker.get_history_metadata() or {})}
        return symbol,normalize_bars(frame,metadata,symbol,clock),info
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending={pool.submit(collect,s):s for s in sorted(symbols)}
        for future in as_completed(pending):
            symbol=pending[future]
            try:
                _,records,info=future.result();prices[symbol]=records
                if symbol==BENCHMARK['symbol']: benchmark=benchmark_identity(info)
            except Exception as error: errors.append(f'{symbol}: market data unavailable ({type(error).__name__}).')
    fx_start=(date.fromisoformat(start)-timedelta(days=7)).isoformat()
    currencies={m['currency'] for series in prices.values() for m in series.values()}
    rates={}
    for currency in currencies:
        if currency=='EUR': continue
        try: rates[currency]=historical_fx(currency,fx_start,now[:10])
        except Exception as error: errors.append(f'{currency}: historical FX unavailable ({type(error).__name__}).')
    for symbol,series in prices.items():
        for d,mark in series.items():
            if mark['currency']=='EUR':
                mark.update(fx_to_eur=1.,fx_date=d,fx_source='fx:EUR/EUR:identity');continue
            available=[r for rd,r in rates.get(mark['currency'],{}).items() if 0<=(date.fromisoformat(d)-date.fromisoformat(rd)).days<=7]
            if available:
                fx=max(available,key=lambda r:r['date']);mark.update(fx_to_eur=fx['rate'],fx_date=fx['date'],fx_source=fx['source'])
    sessions=sorted({d for s,series in prices.items() for d in series if series})
    return {'fx_rates':rates,'prices':prices,'session_dates':sessions,'benchmark':benchmark,'errors':errors}
