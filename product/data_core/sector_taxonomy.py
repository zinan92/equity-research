"""Separate cross-sector taxonomy; never repurposes AI-compute identities."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from .industry_ontology import build_ontology

SECTOR_TAXONOMY_VERSION='park-cross-sector-taxonomy-v1'
@dataclass(frozen=True)
class SectorSegment:
 segment_id:str; sector:str; name:str; definition:str; boundary:str
_ROWS=(
 ('battery','动力与储能电池','电池制造与系统集成','Includes battery cells, packs and energy-storage systems; excludes upstream minerals.'),
 ('consumer','高端白酒','品牌白酒生产、渠道与消费需求','Includes branded baijiu operations; excludes general food and beverage.'),
 ('bank','全国性商业银行','存贷款、息差、资产质量与资本','Includes commercial-bank balance sheet operations; excludes insurers and brokers.'),
)
def build_cross_sector_taxonomy():
 rows=tuple(SectorSegment(f'cross-sector/{key}',key,name,definition,boundary) for key,name,definition,boundary in _ROWS)
 if len({r.segment_id for r in rows})!=len(rows): raise ValueError('sector identities must be unique')
 return rows
def taxonomy_receipt():
 rows=build_cross_sector_taxonomy(); material='|'.join(r.segment_id for r in rows)
 return {'version':SECTOR_TAXONOMY_VERSION,'segment_count':len(rows),'identity_hash':sha256(material.encode()).hexdigest(),'boundary':'Cross-sector extension; does not modify ai-compute ontology.'}
def validate_position_segment(segment_id:str):
 allowed={r.segment_id for r in build_cross_sector_taxonomy()}
 if segment_id in {r.segment_id for r in build_ontology()[1]}: return 'ai-compute'
 if segment_id in allowed: return 'cross-sector'
 raise ValueError('unknown or mismatched taxonomy segment')
