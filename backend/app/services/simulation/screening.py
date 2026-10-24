"""Adapter to the same filter engine used by saved screens and watchlist badges."""
from datetime import date
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[4] / 'scripts'))
from evaluate_saved_filters import expression_matches

ENTRY_EXPRESSION={'operator':'and','groups':[
    {'operator':'or','conditions':[{'field':'revenue','value':'Strong'},{'field':'revenue','value':'Solid'}]},
    {'operator':'and','conditions':[{'field':'operating_margin','comparison':'gt','value':'0'}]},
    {'operator':'and','conditions':[{'field':'red_flag_count','comparison':'eq','value':'0'}]},
]}

def screen_expression_matches(snapshot: dict, today: date) -> bool:
    return expression_matches(snapshot,ENTRY_EXPRESSION,today)
