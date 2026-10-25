"""Forward-only scenario tests; synthetic prices never enter published history."""
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json
import os
import requests
import unittest

from test_screening_metrics import fact
from test_red_flags import clean
from app.services.simulation.accounting import book, valuation, verify_ledger, execute_orders, apply_corporate_actions, record_snapshot
from app.services.simulation.engine import initialize,prepare,claim,analyze,finalize,public_dashboard,validate_reconstruction,atomic_json,load_state,BENCHMARK
from app.services.simulation.strategy import screen_stock,select_candidates,forward_pe_classification
from app.services.simulation.analysis import validate_review,call_gemini,estimate_usage_cost,InvestmentReview
from app.config import get_settings
from app.services.simulation.market import benchmark_identity,historical_fx,normalize_bars

START='2026-10-25T18:00:00+00:00'
MON='2026-10-26';TUE='2026-10-27';WED='2026-10-28';THU='2026-10-29'

def now(d):return d+'T22:35:00+00:00'

def stock(symbol='AAA',growth=12):
    s=clean();s['ticker']=symbol;s['name']='Company '+symbol
    s['price_opportunity']['current_price'].update(as_of=MON)
    s['metrics']['market_cap'].update(as_of=MON)
    s['valuation_inputs']['forward_eps_public']={**fact(5,'AnnualExpectedEPS',MON),'source':'analyst:consensus:FY2027',
        'currency':'USD','tier':'proxy_estimate','forecast_horizon':'FY2027 annual','estimate_as_of':MON}
    if growth!=12:
        for i,row in enumerate(s['historical_series']['quarterly_revenue']):
            revenue=100 if i<4 else 100*(1+growth/100)**(i//4)
            row['metrics']['revenue']['value']=revenue
            if i>=4:row['metrics']['revenue_growth_yoy']['value']=(revenue/s['historical_series']['quarterly_revenue'][i-4]['metrics']['revenue']['value']-1)*100
            s['historical_series']['quarterly_fundamentals'][i]['metrics']['revenue']['value']=revenue
            s['historical_series']['quarterly_fundamentals'][i]['metrics']['operating_income']['value']=revenue*.2
    return s

def mark(d,price=100,currency='USD',fx=.9,split=1,dividend=0):
    return {'date':d,'close':price,'currency':currency,'fx_to_eur':fx,'fx_date':d,'fx_source':'fixture:historical-fx',
            'source':'fixture:closing-price','close_timestamp':d+'T20:00:00+00:00','split_ratio':split,'dividend':dividend,
            'corporate_actions_available':True,'unsupported_action':False}

def market(d,symbols=('AAA',),price=100,fx=.9,split=1,dividend=0):
    return {'session_dates':[d],'benchmark':{**BENCHMARK,'verified':True},'prices':{
        'SPY':{d:mark(d,500)},'VWCE.DE':{d:mark(d,200,'EUR',1)},
        **{s:{d:mark(d,price,fx=fx,split=split,dividend=dividend)} for s in symbols}},'errors':[]}

def good_review(request,investment='compelling',thesis='intact'):
    candidates=request['payload']['candidates']
    return {'assessments':[{'symbol':c['symbol'],'business_assessment':'Profitable growing business.',
        'valuation_assessment':'The supplied sourced forward multiple is reasonable.',
        'investment_assessment':investment,'thesis_status':thesis,
        'evidence':[{'reference_id':f'{c["symbol"]}:{key}','explanation':'The supplied dated metric supports this assessment.'} for key in ('revenue','operating_margin','forward_pe') if f'{c["symbol"]}:{key}' in request['registry']],
        'principal_risks':['Forecasts may be incorrect.'],'explanation':'Reported growth and profitability support the case at the supplied forward valuation.'} for c in request['payload']['companies']],
        'ranked_candidates':list(candidates),'comparisons':[]}

def mocked_call(request,key):
    return good_review(request),{'model':'gemini-3-flash-preview','usage':{'input_tokens':100,'output_tokens':50},'estimated_cost_usd':.0002}

def gemini_response(request):
    return {'responseId':'fixture-response','modelVersion':'gemini-3-flash-preview',
            'usageMetadata':{'promptTokenCount':1000,'cachedContentTokenCount':200,
                             'candidatesTokenCount':100,'thoughtsTokenCount':50,'totalTokenCount':1150},
            'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(good_review(request))}]}}]}

def run_review(state,stocks,d,market_data=None,caller=mocked_call,configured=True):
    session=prepare(state,stocks,market_data or market(d,[s['ticker'] for s in stocks]),now(d),configured)
    if session:
        claim(state,session,'test-run:1',now(d));analyze(state,session,'test-run:1','fixture-key' if configured else '',now(d),caller)
        finalize(state,session,now(d))
    return session


class PortfolioSimulationTests(unittest.TestCase):
    def held(self):
        state=initialize(START);s=stock();run_review(state,[s],MON)
        for symbol,series in market(TUE)['prices'].items():state['market_data'].setdefault(symbol,{}).update(series)
        execute_orders(state,TUE);record_snapshot(state,TUE);state['sessions'][TUE]={'accounted':True}
        return state,s

    def test_initial_buy_later_close_costs_fx_cash_and_common_baseline(self):
        state=initialize(START);s=stock();run_review(state,[s],MON)
        self.assertEqual(book(state,'strategy')['positions'],[])
        self.assertEqual([t['type'] for t in state['transactions']],['BUY']) # Benchmark only.
        baseline=[p for p in state['portfolio_snapshots'] if p['date']=='2026-10-25']
        self.assertEqual([p['equity'] for p in baseline],[10000,10000])
        self.assertEqual(state['orders'][1]['status'],'pending')
        prepare(state,[s],market(TUE,price=110),now(TUE),True)
        tx=next(t for t in state['transactions'] if t['portfolio_id']=='strategy')
        self.assertEqual(tx['execution_date'],TUE)
        self.assertEqual(tx['execution_price'],110)
        self.assertAlmostEqual(tx['quantity'],2500/1.001/(110*.9),places=10)
        self.assertAlmostEqual(tx['fees_eur'],tx['gross_eur']*.001,places=7)
        self.assertAlmostEqual(book(state,'strategy')['cash'],7500,places=6)
        self.assertAlmostEqual(valuation(state,'strategy',TUE)['equity'],10000-tx['fees_eur'],places=6)
        validate_reconstruction(state)

    def test_no_qualifiers_preserves_cash_and_independent_benchmark(self):
        state=initialize(START);s=stock();s['valuation_inputs']={}
        run_review(state,[s],MON)
        self.assertEqual(book(state,'strategy')['cash'],10000)
        self.assertEqual(len(book(state,'vwce')['positions']),1)
        self.assertEqual(state['investment_decisions'][0]['action'],'NO_ACTION')
        self.assertEqual(state['sessions'][MON]['analysis_status'],'not_needed')
        self.assertFalse(state['sessions'][MON]['screening'][0]['eligible'])

    def test_holding_twenty_percent_winner_creates_no_sale(self):
        state,s=self.held();run_review(state,[s],TUE)
        before=len(state['transactions'])
        run_review(state,[s],WED,market(WED,price=120))
        self.assertEqual(len(state['transactions']),before)
        self.assertEqual(state['investment_decisions'][-1]['action'],'HOLD')
        self.assertGreater(valuation(state,'strategy',WED)['unrealized_pnl'],400)

    def test_expensive_valuation_without_alternative_does_not_sell(self):
        state,s=self.held();s['valuation_inputs']['forward_eps_public']['value']=2
        run_review(state,[s],TUE)
        self.assertEqual(state['sessions'][TUE]['screening'][0]['forward_pe_class'],'Expensive')
        self.assertFalse(any(o['type']=='SELL' for o in state['orders']))
        self.assertEqual(state['investment_decisions'][-1]['action'],'HOLD')

    def test_broken_thesis_and_confirmed_negative_margin_sell_next_session(self):
        state,s=self.held();s['historical_series']['quarterly_fundamentals'][-1]['metrics']['operating_income']['value']=-10
        run_review(state,[s],TUE,caller=lambda r,k:(good_review(r,thesis='broken'),{}))
        self.assertEqual(state['investment_decisions'][-1]['action'],'SELL')
        self.assertEqual(book(state,'strategy')['positions'][0]['status'],'open')
        prepare(state,[s],market(WED,price=90),now(WED),True)
        p=book(state,'strategy')['positions'][0]
        self.assertEqual(p['status'],'closed');self.assertEqual(p['exit_date'],WED)
        self.assertLess(p['realized_pnl'],0);self.assertEqual(len(p['transactions']),2)
        self.assertIn('Thesis broken',p['exit_reason']);validate_reconstruction(state)

    def test_replacement_executes_sale_before_buy_and_links_history(self):
        state,a=self.held();b=stock('BBB');a['valuation_inputs']['forward_eps_public']['value']=2
        def review(request,key):
            r=good_review(request,thesis='deteriorating')
            r['comparisons']=[{'candidate_symbol':'BBB','holding_symbol':'AAA','materially_better':True,
                'evidence':[{'reference_id':f'{s}:forward_pe','explanation':'Dated multiples support a material valuation comparison.'} for s in ['AAA','BBB']],
                'explanation':'BBB has a substantially more attractive supplied valuation with comparable reported profitability.'}]
            return r,{}
        run_review(state,[a,b],TUE,market(TUE,['AAA','BBB']),review)
        self.assertTrue(any(d['action']=='REPLACE' for d in state['investment_decisions']))
        prepare(state,[a,b],market(WED,['AAA','BBB'],price=120),now(WED),True)
        tx=[t for t in state['transactions'] if t['portfolio_id']=='strategy' and t['execution_date']==WED]
        self.assertEqual([t['type'] for t in tx],['SELL','BUY'])
        self.assertEqual(tx[1]['replacement_for'],next(o['id'] for o in state['orders'] if o['type']=='SELL'))
        positions=book(state,'strategy')['positions'];self.assertEqual([p['status'] for p in positions],['closed','open'])
        self.assertEqual(positions[0]['replaced_by'],'BBB')
        self.assertLessEqual(-tx[1]['net_cash_eur'],valuation(state,'strategy',WED)['equity']*.25+.02)
        validate_reconstruction(state)

    def test_missing_financial_data_never_qualifies_or_implies_deterioration(self):
        s=stock();s['historical_series']['quarterly_fundamentals'][-1]['metrics'].pop('capex')
        self.assertFalse(screen_stock(s,date.fromisoformat(MON))['eligible'])
        state,held=self.held();held['historical_series']['quarterly_fundamentals'][-1]['metrics'].pop('operating_income')
        run_review(state,[held],TUE,caller=lambda r,k:(good_review(r,thesis='broken'),{}))
        self.assertEqual(state['investment_decisions'][-1]['action'],'HOLD')

    def test_api_failure_invalid_schema_and_untrusted_references_create_no_orders(self):
        for failure in ['exception','invalid','bad_source','duplicates','missing_company']:
            state=initialize(START)
            def caller(request,key):
                if failure=='exception': raise RuntimeError('not persisted')
                r=good_review(request)
                if failure=='invalid':r['execute_trades']=True
                elif failure=='bad_source':r['assessments'][0]['evidence'][0]['reference_id']='invented:fact'
                elif failure=='duplicates':r['ranked_candidates']*=2
                else:r['assessments']=[]
                return r,{'usage':{'input_tokens':1,'output_tokens':1},'estimated_cost_usd':.000012}
            run_review(state,[stock()],MON,caller=caller)
            self.assertEqual(len(state['orders']),1)
            self.assertEqual(state['sessions'][MON]['analysis_status'],'failed')
            self.assertEqual(state['investment_decisions'][-1]['action'],'NO_ACTION')
            self.assertEqual(len(book(state,'vwce')['positions']),1)

    def test_duplicate_session_and_paid_claim_recovery_are_idempotent(self):
        state=initialize(START);calls=[]
        def caller(r,k):calls.append(1);return mocked_call(r,k)
        run_review(state,[stock()],MON,caller=caller);before=deepcopy(state)
        run_review(state,[stock()],MON,caller=caller)
        self.assertEqual(state,before);self.assertEqual(calls,[1])
        # Checkpoint was persisted but response was lost: do not call again.
        state=initialize(START);prepare(state,[stock()],market(MON),now(MON),True)
        self.assertTrue(claim(state,MON,'prior-run',now(MON)))
        self.assertFalse(claim(state,MON,'new-run',now(MON)))
        self.assertFalse(analyze(state,MON,'new-run','fixture-key',now(MON),caller))
        finalize(state,MON,now(MON));self.assertEqual(state['sessions'][MON]['analysis_status'],'indeterminate')
        self.assertEqual(len(state['orders']),1)

    def test_missing_api_key_creates_no_call_or_strategy_orders(self):
        state=initialize(START)
        run_review(state,[stock()],MON,configured=False,caller=lambda *a:self.fail('API must not be called'))
        self.assertEqual(state['metadata']['status'],'awaiting_api_key')
        self.assertEqual(state['ai_usage'],[]);self.assertEqual(len(state['orders']),1)

    def test_invalid_execution_price_fx_or_same_session_remain_pending(self):
        state=initialize(START);run_review(state,[stock()],MON)
        execute_orders(state,MON)
        self.assertEqual(len(book(state,'strategy')['positions']),0)
        for key,value in [('close',0),('fx_to_eur',None)]:
            bad=deepcopy(state);m=market(TUE);m['prices']['AAA'][TUE][key]=value
            prepare(bad,[stock()],m,now(TUE),True)
            self.assertEqual(len(book(bad,'strategy')['positions']),0)
            self.assertEqual(bad['orders'][1]['status'],'pending')

    def test_fx_split_and_dividend_preserve_basis_and_avoid_double_counting(self):
        state,s=self.held();qty=book(state,'strategy')['positions'][0]['quantity'];basis=book(state,'strategy')['positions'][0]['cost_basis']
        run_review(state,[s],TUE)
        prepare(state,[s],market(WED,price=50,fx=.8,split=2,dividend=1),now(WED),True)
        p=valuation(state,'strategy',WED)['positions'][0]
        self.assertAlmostEqual(p['quantity'],qty*2)
        self.assertAlmostEqual(p['cost_basis'],basis)
        self.assertAlmostEqual(p['market_value'],qty*2*50*.8)
        self.assertAlmostEqual(p['dividends'],qty*2*.8,places=7)
        self.assertEqual([t['type'] for t in state['transactions']][-2:],['SPLIT','DIVIDEND'])
        self.assertAlmostEqual(valuation(state,'strategy',TUE)['positions'][0]['market_value'],qty*100*.9)
        validate_reconstruction(state)

    def test_historical_positions_remain_after_sale_and_replacement(self):
        state,s=self.held();before=deepcopy(state['portfolio_snapshots'])
        s['historical_series']['quarterly_fundamentals'][-1]['metrics']['operating_income']['value']=-10
        run_review(state,[s],TUE,caller=lambda r,k:(good_review(r,thesis='broken'),{}))
        prepare(state,[s,stock('BBB')],market(WED,['AAA','BBB'],price=150),now(WED),True)
        run_review(state,[stock('BBB')],WED,market(WED,['BBB']))
        prepare(state,[stock('BBB')],market(THU,['BBB'],price=500),now(THU),True)
        self.assertEqual(state['portfolio_snapshots'][:len(before)],before)
        self.assertEqual([p['symbol'] for p in book(state,'strategy')['positions']],['AAA','BBB'])
        self.assertGreater(book(state,'strategy')['realized_pnl'],0)
        validate_reconstruction(state)

    def test_selection_limits_and_original_valuation_boundaries(self):
        screens=[screen_stock(stock(f'S{i:02}',25 if i%2 else 12),date.fromisoformat(MON)) for i in range(30)]
        for i,s in enumerate(screens):s['forward_pe_class']='Cheap' if i%3 else 'Fair'
        result=select_candidates(screens,set(),set())
        self.assertEqual(len(result),20)
        self.assertEqual(result[0]['forward_pe_class'],'Cheap')
        self.assertEqual(result[0]['revenue_strength'],'Strong')
        self.assertEqual([forward_pe_classification(v) for v in [0,18,18.01,25,26,34.99,35,50]],['Unknown','Cheap','Fair','Fair','Unknown','Unknown','Expensive','Expensive'])
        state=initialize(START);stocks=[stock(s) for s in ['AAA','BBB','CCC','DDD','EEE']]
        run_review(state,stocks,MON)
        self.assertEqual(len([o for o in state['orders'] if o['portfolio_id']=='strategy']),4)
        prepare(state,stocks,market(TUE,[s['ticker'] for s in stocks]),now(TUE),True)
        self.assertEqual(len(book(state,'strategy')['positions']),4)
        self.assertGreaterEqual(book(state,'strategy')['cash'],0)
        verify_ledger(state)

    def test_atomic_persistence_tamper_detection_and_public_export(self):
        state,s=self.held()
        with TemporaryDirectory() as temp:
            path=Path(temp)/'state.json';atomic_json(path,state);loaded=load_state(path)
            self.assertEqual(loaded,state)
        bad=deepcopy(state);bad['transactions'][0]['quantity']+=1
        with self.assertRaises(ValueError):verify_ledger(bad)
        public=public_dashboard(state);self.assertNotIn('market_data',public)
        self.assertNotIn('registry',json.dumps(public))
        self.assertFalse(public['ai_costs']['deducted_from_returns'])
        self.assertIsNone(public['ai_costs']['net_economic_return'])
        self.assertEqual(public['portfolios']['strategy']['performance']['annualized_return_pct'],None)

    def test_usage_and_gemini_request_parameters(self):
        self.assertAlmostEqual(estimate_usage_cost({'input_tokens':1000,'output_tokens':100,'input_tokens_details':{'cached_tokens':200}}),.00071)
        self.assertIsNone(estimate_usage_cost({'input_tokens':1000,'output_tokens':100},'another-gemini-model'))
        self.assertIsNone(estimate_usage_cost({}))
        self.assertIsNone(estimate_usage_cost({'input_tokens':1000,'output_tokens':100,'input_tokens_details':{'cached_tokens':1001}}))
        state=initialize(START);prepare(state,[stock()],market(MON),now(MON),True);r=state['sessions'][MON]['request']
        r['model']='gemini-3-flash-preview'
        response=gemini_response(r)
        # Ignore thought parts and support the final JSON spanning multiple parts.
        text=response['candidates'][0]['content']['parts'][0]['text']
        response['candidates'][0]['content']['parts']=[{'thought':True,'text':'Internal thought.'},{'text':text[:30]},{'text':text[30:]}]
        with patch('app.services.simulation.analysis.requests.post',return_value=SimpleNamespace(raise_for_status=lambda:None,json=lambda:response)) as post:
            raw,metadata=call_gemini(r,'test-key')
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0],'https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent')
        args=post.call_args.kwargs
        self.assertEqual(args['headers'],{'x-goog-api-key':'test-key'})
        self.assertFalse(args['allow_redirects'])
        self.assertEqual(args['timeout'],(10,300))
        config=args['json']['generationConfig']
        self.assertEqual(config['thinkingConfig'],{'thinkingLevel':'high'})
        self.assertEqual(config['responseMimeType'],'application/json')
        self.assertEqual(config['responseJsonSchema'],InvestmentReview.model_json_schema())
        self.assertEqual(json.loads(args['json']['contents'][0]['parts'][0]['text']),r['payload'])
        self.assertIn('equity investment analyst',args['json']['systemInstruction']['parts'][0]['text'])
        self.assertEqual(validate_review(raw,r),good_review(r))
        self.assertEqual(metadata['usage']['input_tokens'],1000)
        self.assertEqual(metadata['usage']['output_tokens'],150)
        self.assertEqual(metadata['usage']['output_tokens_details']['reasoning_tokens'],50)
        self.assertEqual(metadata['provider_usage'],response['usageMetadata'])
        self.assertAlmostEqual(metadata['estimated_cost_usd'],.00086)

    def test_gemini_invalid_responses_preserve_usage_and_never_create_orders(self):
        for invalid in ('blocked','truncated','malformed','empty','invalid_evidence','extra_field'):
            with self.subTest(invalid=invalid):
                state=initialize(START);prepare(state,[stock()],market(MON),now(MON),True)
                r=state['sessions'][MON]['request'];response=gemini_response(r)
                if invalid=='blocked':
                    response.update(candidates=[],promptFeedback={'blockReason':'SAFETY'})
                elif invalid=='truncated':response['candidates'][0]['finishReason']='MAX_TOKENS'
                elif invalid=='malformed':response['candidates'][0]['content']['parts']=[{'text':'{'}]
                elif invalid=='empty':response['candidates'][0]['content']['parts']=[]
                else:
                    review=good_review(r)
                    if invalid=='invalid_evidence':review['assessments'][0]['evidence'][0]['reference_id']='invented'
                    else:review['unexpected']=True
                    response['candidates'][0]['content']['parts']=[{'text':json.dumps(review)}]
                claim(state,MON,'test-run',now(MON))
                with patch('app.services.simulation.analysis.requests.post',return_value=SimpleNamespace(raise_for_status=lambda:None,json=lambda:response)) as post:
                    self.assertFalse(analyze(state,MON,'test-run','test-key',now(MON)))
                    self.assertFalse(analyze(state,MON,'test-run','test-key',now(MON)))
                post.assert_called_once()
                finalize(state,MON,now(MON))
                self.assertEqual(state['ai_usage'][0]['status'],'failed')
                self.assertEqual(state['ai_usage'][0]['usage']['output_tokens'],150)
                self.assertEqual(len(state['orders']),1) # Benchmark only.

    def test_gemini_http_failures_do_not_retry_or_leak_credentials(self):
        for error in (requests.HTTPError('429 test-secret'),requests.Timeout('test-secret')):
            with self.subTest(error=type(error).__name__):
                state=initialize(START);prepare(state,[stock()],market(MON),now(MON),True)
                claim(state,MON,'test-run',now(MON))
                with patch('app.services.simulation.analysis.requests.post',side_effect=error) as post:
                    self.assertFalse(analyze(state,MON,'test-run','test-secret',now(MON)))
                    self.assertFalse(analyze(state,MON,'test-run','test-secret',now(MON)))
                post.assert_called_once()
                self.assertNotIn('test-secret',json.dumps(state))

    def test_gemini_model_is_frozen_at_preparation_and_journaled(self):
        state=initialize(START)
        with patch.dict(os.environ,{'GEMINI_MODEL':'gemini-custom-model'}):
            prepare(state,[stock()],market(MON),now(MON),True)
        r=state['sessions'][MON]['request'];response=gemini_response(r)
        response['modelVersion']='gemini-custom-model-version'
        with patch.dict(os.environ,{'GEMINI_MODEL':'changed-model'}):
            claim(state,MON,'test-run',now(MON))
            self.assertEqual(state['ai_usage'][0]['model'],'gemini-custom-model')
            with patch('app.services.simulation.analysis.requests.post',return_value=SimpleNamespace(raise_for_status=lambda:None,json=lambda:response)) as post:
                self.assertTrue(analyze(state,MON,'test-run','test-key',now(MON)))
            self.assertIn('/gemini-custom-model:generateContent',post.call_args.args[0])
            finalize(state,MON,now(MON))
        self.assertIsNone(state['ai_usage'][0]['estimated_cost_usd'])
        self.assertEqual(state['investment_decisions'][-1]['model'],'gemini-custom-model-version')

    def test_gemini_settings_load_dotenv_and_respect_environment_overrides(self):
        with TemporaryDirectory() as temp:
            Path(temp,'.env').write_text('GEMINI_API_KEY=dotenv-key\nGEMINI_MODEL=gemini-dotenv-model\n')
            with patch('app.config.PROJECT_DIR',Path(temp)),patch.dict(os.environ,{},clear=True):
                settings=get_settings()
                self.assertEqual(settings.gemini_api_key,'dotenv-key')
                self.assertEqual(settings.gemini_model,'gemini-dotenv-model')
                with patch.dict(os.environ,{'GEMINI_API_KEY':'ci-key','GEMINI_MODEL':'models/gemini-ci-model'}):
                    settings=get_settings()
                    self.assertEqual(settings.gemini_api_key,'ci-key')
                    self.assertEqual(settings.gemini_model,'gemini-ci-model')
                with patch.dict(os.environ,{'GEMINI_API_KEY':'','GEMINI_MODEL':''}):
                    settings=get_settings()
                    self.assertIsNone(settings.gemini_api_key)
                    self.assertEqual(settings.gemini_model,'gemini-3-flash-preview')

    def test_missing_gemini_key_does_not_make_a_request(self):
        state=initialize(START);prepare(state,[stock()],market(MON),now(MON),False)
        with patch('app.services.simulation.analysis.requests.post') as post:
            self.assertFalse(claim(state,MON,'test-run',now(MON)))
            self.assertFalse(analyze(state,MON,'test-run','',now(MON)))
            with self.assertRaises(ValueError):call_gemini(state['sessions'][MON]['request'],'')
        post.assert_not_called()
        finalize(state,MON,now(MON))
        self.assertIn('GEMINI_API_KEY',state['sessions'][MON]['analysis_message'])

    def test_benchmark_identity_and_historical_fx(self):
        info={'symbol':'VWCE.DE','currency':'EUR','quoteType':'ETF','exchange':'GER','longName':BENCHMARK['name'],'isin':BENCHMARK['isin']}
        self.assertTrue(benchmark_identity(info)['verified'])
        for key,value in [('symbol','VWRA.L'),('currency','USD'),('isin','wrong'),('quoteType','EQUITY')]:
            bad={**info,key:value};self.assertFalse(benchmark_identity(bad)['verified'])
        response=SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'base':'USD','rates':{MON:{'EUR':.9},TUE:{'EUR':.8}}})
        rates=historical_fx('USD',MON,TUE,SimpleNamespace(get=lambda *a,**kw:response))
        self.assertEqual([r['rate'] for r in rates.values()],[.9,.8])

    def test_cross_market_replacement_waits_for_recorded_sale_proceeds(self):
        state,a=self.held();a['valuation_inputs']['forward_eps_public']['value']=2
        b=stock('BBB')
        def review(request,key):
            r=good_review(request,thesis='deteriorating')
            r['comparisons']=[{'candidate_symbol':'BBB','holding_symbol':'AAA','materially_better':True,
                'evidence':[{'reference_id':f'{s}:forward_pe','explanation':'The sourced multiples support the proposed replacement.'} for s in ['AAA','BBB']],
                'explanation':'The new candidate has materially better valuation with similar operating fundamentals.'}]
            return r,{}
        run_review(state,[a,b],TUE,market(TUE,['AAA','BBB']),review)
        bundle=market(WED,['AAA','BBB'])
        bundle['prices']['BBB'][WED]['close_timestamp']=WED+'T16:30:00+00:00'
        prepare(state,[a,b],bundle,now(WED),True)
        sale=next(o for o in state['orders'] if o['type']=='SELL')
        purchase=next(o for o in state['orders'] if o['symbol']=='BBB')
        self.assertEqual(sale['status'],'executed');self.assertEqual(purchase['status'],'pending')
        next_day=market(THU,['AAA','BBB']);next_day['prices']['BBB'][THU]['close_timestamp']=THU+'T16:30:00+00:00'
        prepare(state,[a,b],next_day,now(THU),True)
        self.assertEqual(purchase['status'],'executed')
        self.assertEqual(purchase['execution_date'],THU)
        validate_reconstruction(state)

    def test_stock_export_preserves_durable_simulation(self):
        from export_static_site_data import export_simulation_data
        with TemporaryDirectory() as directory:
            root=Path(directory);data=root/'data';output=root/'public'
            atomic_json(data/'simulation/state.json',initialize(START))
            export_simulation_data(data,output)
            payload=json.loads((output/'simulation/index.json').read_text())
            self.assertEqual(payload['metadata']['start_date'],'2026-10-25')
            self.assertEqual(payload['transactions'],[])

    def test_interrupted_attempt_exposes_unknown_operating_cost(self):
        state=initialize(START);prepare(state,[stock()],market(MON),now(MON),True)
        claim(state,MON,'first-run',now(MON));finalize(state,MON,now(MON))
        self.assertEqual(state['ai_usage'][0]['status'],'indeterminate')
        self.assertFalse(public_dashboard(state)['ai_costs']['complete'])

    def test_nontrading_price_uses_valuation_date_fx_without_rewriting_history(self):
        state,s=self.held();before=valuation(state,'strategy',TUE)['equity']
        bundle=market(WED,[])
        bundle['fx_rates']={'USD':{WED:{'rate':.8,'date':WED,'source':'fixture:dated-fx'}}}
        prepare(state,[s],bundle,now(WED),True)
        v=valuation(state,'strategy',WED);p=v['positions'][0]
        self.assertEqual(p['price_date'],TUE);self.assertEqual(p['fx_date'],WED)
        self.assertAlmostEqual(p['market_value'],p['quantity']*100*.8,places=7)
        self.assertEqual(v['stale_symbols'],['AAA'])
        self.assertEqual(valuation(state,'strategy',TUE)['equity'],before)
        validate_reconstruction(state)

    def test_yahoo_split_normalization_and_no_open_session_candles(self):
        import pandas as pd
        index=pd.to_datetime([MON,TUE,WED]).tz_localize('America/New_York')
        frame=pd.DataFrame({'Close':[50,50,55],'Stock Splits':[0,2,0],'Dividends':[0,0,1]},index=index)
        rows=normalize_bars(frame,{'currency':'USD','exchangeTimezoneName':'America/New_York'},'AAA',datetime.fromisoformat(now(WED)))
        self.assertEqual([rows[d]['close'] for d in [MON,TUE,WED]],[100,50,55])
        early=normalize_bars(frame,{'currency':'USD','exchangeTimezoneName':'America/New_York'},'AAA',datetime.fromisoformat(WED+'T12:00:00+00:00'))
        self.assertNotIn(WED,early)

if __name__=='__main__':unittest.main()
