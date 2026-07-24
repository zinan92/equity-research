"""Deterministic, non-executable decision and position-policy receipts."""
from __future__ import annotations
import hashlib,json
from dataclasses import asdict,dataclass
from typing import Literal

POLICY_VERSION='park-decision-policy-v1'
def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
@dataclass(frozen=True)
class DecisionInput:
 ticker:str; context_manifest_hash:str; dossier_id:str; current_price:float|None; target_price:float|None; quality_score:float|None; risk_score:float|None; liquidity_score:float|None; coverage_passed:bool; sector_exposure:float; current_position:float; cash_weight:float
 def validate(self):
  if not self.ticker or len(self.context_manifest_hash)!=64 or not self.dossier_id: raise ValueError('decision identity is required')
  if (self.current_price is not None and self.current_price<=0) or not all(0<=x<=1 for x in (self.sector_exposure,self.current_position,self.cash_weight)): raise ValueError('decision input range is invalid')
  for v in (self.quality_score,self.risk_score,self.liquidity_score):
   if v is not None and not 0<=v<=1: raise ValueError('score must be between zero and one')
@dataclass(frozen=True)
class DecisionReceipt:
 ticker:str; action:Literal['increase','hold','reduce','no_action']; target_range:tuple[float,float]|None; position_range:tuple[float,float]|None; reasons:tuple[str,...]; input_hash:str; receipt_hash:str
def decide(value:DecisionInput,*,single_stock_cap:float=.10,sector_cap:float=.25,cash_floor:float=.05)->DecisionReceipt:
 value.validate()
 base={'version':POLICY_VERSION,**asdict(value),'caps':(single_stock_cap,sector_cap,cash_floor)}; ih=digest(base)
 reasons=[]
 if not value.coverage_passed or value.target_price is None: reasons.append('insufficient_evidence_coverage')
 if value.current_price is None: reasons.append('missing_market_price')
 if any(x is None for x in (value.quality_score,value.risk_score,value.liquidity_score)): reasons.append('missing_quality_risk_or_liquidity')
 if value.sector_exposure>=sector_cap: reasons.append('sector_cap_reached')
 if value.cash_weight<=cash_floor: reasons.append('cash_floor_reached')
 if reasons:
  result=DecisionReceipt(value.ticker,'no_action',None,None,tuple(reasons),ih,'')
 else:
  upside=value.target_price/value.current_price-1
  conviction=(value.quality_score+value.liquidity_score+(1-value.risk_score))/3
  if upside<=-.1: action='reduce'; position=(0.0,min(value.current_position,.03))
  elif upside>=.1 and conviction>=.6: action='increase'; position=(value.current_position,min(single_stock_cap,value.current_position+.03))
  else: action='hold'; position=(value.current_position,value.current_position)
  target=(round(value.target_price*.9,6),round(value.target_price*1.1,6))
  result=DecisionReceipt(value.ticker,action,target,position,('input_bound_policy',),ih,'')
 rh=digest({**asdict(result),'receipt_hash':''}); return DecisionReceipt(result.ticker,result.action,result.target_range,result.position_range,result.reasons,result.input_hash,rh)
