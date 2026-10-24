"""Scheduled paper portfolio runner. Checkpoint claim in Git before --phase analyze."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.static_stock_assets import load_full_stock_rows
from app.services.simulation.engine import initialize,load_state,save_state,prepare,claim,analyze,finalize,public_dashboard,atomic_json,validate_reconstruction
from app.services.simulation.market import fetch_market


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['initialize','market','prepare','claim','analyze','finalize','publish','verify'],required=True)
    parser.add_argument('--state',type=Path,default=ROOT/'data/simulation/state.json')
    parser.add_argument('--output',type=Path,default=ROOT/'frontend/public/data/simulation/index.json')
    parser.add_argument('--market-file',type=Path,help='Recorded provider bundle for offline verification; never generates synthetic prices.')
    parser.add_argument('--market-output',type=Path,default=Path('/tmp/portfolio-market.json'))
    parser.add_argument('--now',help='ISO timestamp for offline tests; production uses current UTC time.')
    parser.add_argument('--owner',default=os.environ.get('SIMULATION_RUN_OWNER','local'))
    args=parser.parse_args()
    now=args.now or datetime.now(timezone.utc).isoformat()
    if datetime.fromisoformat(now).tzinfo is None: parser.error('--now requires a timezone')
    key=os.environ.get('OPENAI_API_KEY','')
    if not args.state.exists() and args.phase!='initialize':
        parser.error('Simulation state is missing; explicit initialization is required. Never reset existing history automatically.')
    state=load_state(args.state) if args.state.exists() else initialize(now)
    if args.phase=='initialize' and args.state.exists():
        print('Simulation is already initialized; preserving its original baseline.')
    elif args.phase=='market':
        market=json.loads(args.market_file.read_text()) if args.market_file else fetch_market(state,now)
        atomic_json(args.market_output,market)
        has_session=any(d>=state['metadata']['start_date'] and not state['sessions'].get(d,{}).get('accounted') for d in market.get('session_dates',[]))
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as stream:stream.write(f'has_session={str(has_session).lower()}\n')
    elif args.phase=='prepare':
        market=json.loads(args.market_file.read_text()) if args.market_file else fetch_market(state,now)
        try: prepare(state,load_full_stock_rows(ROOT/'frontend/public/data'),market,now,bool(key) or os.environ.get("OPENAI_API_KEY_CONFIGURED")=="true")
        except Exception as error:
            save_state(args.state,state)
            print(f'Simulation accounting failed ({type(error).__name__}); prior ledger preserved.',file=sys.stderr)
            return 1
    elif args.phase in {'claim','analyze','finalize'}:
        sessions=[s for s,r in state['sessions'].items() if r.get('request') and not r.get('decisions_applied')]
        if sessions:
            session=max(sessions)
            if args.phase=='claim': claim(state,session,args.owner,now)
            elif args.phase=='analyze':
                if args.owner=='local' and not args.market_file: parser.error('Paid production analysis requires a durable workflow owner and committed claim')
                analyze(state,session,args.owner,key,now)
            else: finalize(state,session,now)
    elif args.phase=='verify': validate_reconstruction(state)
    save_state(args.state,state)
    atomic_json(args.output,public_dashboard(state))
    print(json.dumps({'phase':args.phase,'status':state['metadata']['status'],'start_date':state['metadata']['start_date'],
        'transactions':len(state['transactions']),'snapshots':len(state['portfolio_snapshots']),'api_configured':bool(key)}))
    return 0

if __name__=='__main__':raise SystemExit(main())
