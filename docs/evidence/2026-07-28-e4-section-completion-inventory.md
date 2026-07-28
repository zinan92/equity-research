# E4 三家 Tier-B 章节完成度盘点

本文件只读取 C1 章节合同；不改变任何输入、Tier 或 B6 policy。

## 18 章 × 缺什么

| section_id | required_inputs | 300750.SZ status / present / missing | 600519.SH status / present / missing | 000001.SZ status / present / missing | blocking source |
|---|---|---|---|---|---|
| executive_summary | market_snapshot, decision_summary | MISSING / — / market_snapshot, decision_summary | MISSING / — / market_snapshot, decision_summary | MISSING / — / market_snapshot, decision_summary | decision_summary: data_core.decision_policy; market_snapshot: data_core.e4_market_fundamentals_batch |
| investment_thesis | investment_thesis, variant_view | MISSING / — / investment_thesis, variant_view | MISSING / — / investment_thesis, variant_view | MISSING / — / investment_thesis, variant_view | investment_thesis: 未建; variant_view: 未建 |
| business_model | company_profile, segment_financials | MISSING / — / company_profile, segment_financials | MISSING / — / company_profile, segment_financials | MISSING / — / company_profile, segment_financials | company_profile: data_core.company_positions; segment_financials: 未建 |
| industry_structure | industry_profile, market_size | MISSING / — / industry_profile, market_size | MISSING / — / industry_profile, market_size | MISSING / — / industry_profile, market_size | industry_profile: data_core.industry_profiles; market_size: 未建 |
| competition_and_moat | peer_comparison, moat_assessment | MISSING / — / peer_comparison, moat_assessment | MISSING / — / peer_comparison, moat_assessment | MISSING / — / peer_comparison, moat_assessment | moat_assessment: 未建; peer_comparison: 未建 |
| management_and_governance | management_record, governance_events | MISSING / — / management_record, governance_events | MISSING / — / management_record, governance_events | MISSING / — / management_record, governance_events | governance_events: 未建; management_record: 未建 |
| revenue_quality_and_kpis | revenue_history, operating_kpis | MISSING / — / revenue_history, operating_kpis | MISSING / — / revenue_history, operating_kpis | MISSING / — / revenue_history, operating_kpis | operating_kpis: 未建; revenue_history: data_core.e4_page_level_filing_facts |
| profitability_and_earnings_quality | income_history, margin_bridge | PARTIAL / income_history / margin_bridge | PARTIAL / income_history / margin_bridge | PARTIAL / income_history / margin_bridge | margin_bridge: 未建 |
| cash_flow_and_balance_sheet | cash_flow_history, balance_sheet_history | MISSING / — / cash_flow_history, balance_sheet_history | MISSING / — / cash_flow_history, balance_sheet_history | MISSING / — / cash_flow_history, balance_sheet_history | balance_sheet_history: data_core.e4_market_fundamentals_batch; cash_flow_history: data_core.e4_market_fundamentals_batch |
| accounting_quality | accounting_checks, audit_opinions | MISSING / — / accounting_checks, audit_opinions | MISSING / — / accounting_checks, audit_opinions | MISSING / — / accounting_checks, audit_opinions | accounting_checks: 未建; audit_opinions: data_core.e4_page_level_filing_facts |
| forecasts_and_consensus | broker_estimates, consensus_history | MISSING / — / broker_estimates, consensus_history | MISSING / — / broker_estimates, consensus_history | MISSING / — / broker_estimates, consensus_history | broker_estimates: data_core.e4_sell_side_claim_admission; consensus_history: data_core.e4_valuation_sellside_coverage |
| valuation | valuation_scenarios, valuation_assumptions, current_market | MISSING / — / valuation_scenarios, valuation_assumptions, current_market | MISSING / — / valuation_scenarios, valuation_assumptions, current_market | MISSING / — / valuation_scenarios, valuation_assumptions, current_market | current_market: data_core.e4_market_fundamentals_batch; valuation_assumptions: data_core.e4_valuation_assumptions; valuation_scenarios: data_core.e4_valuation_receipts |
| macro_policy_and_costs | macro_exposures, policy_events | MISSING / — / macro_exposures, policy_events | MISSING / — / macro_exposures, policy_events | MISSING / — / macro_exposures, policy_events | macro_exposures: 未建; policy_events: data_core.event_intelligence |
| catalysts_and_events | event_timeline, catalyst_calendar | MISSING / — / event_timeline, catalyst_calendar | MISSING / — / event_timeline, catalyst_calendar | MISSING / — / event_timeline, catalyst_calendar | catalyst_calendar: data_core.industry_catalysts; event_timeline: data_core.event_intelligence |
| risks_and_falsification | risk_register, falsification_tests | MISSING / — / risk_register, falsification_tests | MISSING / — / risk_register, falsification_tests | MISSING / — / risk_register, falsification_tests | falsification_tests: 未建; risk_register: 未建 |
| decision_framework | recommendation_policy_output | MISSING / — / recommendation_policy_output | MISSING / — / recommendation_policy_output | MISSING / — / recommendation_policy_output | recommendation_policy_output: data_core.decision_policy |
| monitoring_and_action_triggers | monitoring_kpis, action_triggers | MISSING / — / monitoring_kpis, action_triggers | MISSING / — / monitoring_kpis, action_triggers | MISSING / — / monitoring_kpis, action_triggers | action_triggers: 未建; monitoring_kpis: 未建 |
| evidence_and_methodology | evidence_set_receipt, citation_index, methodology | FULL / evidence_set_receipt, citation_index, methodology / — | FULL / evidence_set_receipt, citation_index, methodology / — | FULL / evidence_set_receipt, citation_index, methodology / — | — |

## 缺失输入杠杆排序

所有项的依赖章节数均为 1；以下仅以“已有模块可接”作为同分时的次序。

| rank | input | dependent sections | source/module |
|---:|---|---:|---|
| 1 | audit_opinions | 1 | data_core.e4_page_level_filing_facts |
| 2 | balance_sheet_history | 1 | data_core.e4_market_fundamentals_batch |
| 3 | broker_estimates | 1 | data_core.e4_sell_side_claim_admission |
| 4 | cash_flow_history | 1 | data_core.e4_market_fundamentals_batch |
| 5 | catalyst_calendar | 1 | data_core.industry_catalysts |
| 6 | company_profile | 1 | data_core.company_positions |
| 7 | consensus_history | 1 | data_core.e4_valuation_sellside_coverage |
| 8 | current_market | 1 | data_core.e4_market_fundamentals_batch |
| 9 | decision_summary | 1 | data_core.decision_policy |
| 10 | event_timeline | 1 | data_core.event_intelligence |
| 11 | industry_profile | 1 | data_core.industry_profiles |
| 12 | market_snapshot | 1 | data_core.e4_market_fundamentals_batch |
| 13 | policy_events | 1 | data_core.event_intelligence |
| 14 | recommendation_policy_output | 1 | data_core.decision_policy |
| 15 | revenue_history | 1 | data_core.e4_page_level_filing_facts |
| 16 | valuation_assumptions | 1 | data_core.e4_valuation_assumptions |
| 17 | valuation_scenarios | 1 | data_core.e4_valuation_receipts |
| 18 | accounting_checks | 1 | 未建 |
| 19 | action_triggers | 1 | 未建 |
| 20 | falsification_tests | 1 | 未建 |
| 21 | governance_events | 1 | 未建 |
| 22 | investment_thesis | 1 | 未建 |
| 23 | macro_exposures | 1 | 未建 |
| 24 | management_record | 1 | 未建 |
| 25 | margin_bridge | 1 | 未建 |
| 26 | market_size | 1 | 未建 |
| 27 | moat_assessment | 1 | 未建 |
| 28 | monitoring_kpis | 1 | 未建 |
| 29 | operating_kpis | 1 | 未建 |
| 30 | peer_comparison | 1 | 未建 |
| 31 | risk_register | 1 | 未建 |
| 32 | segment_financials | 1 | 未建 |
| 33 | variant_view | 1 | 未建 |

## 一句话结论

距离 Tier A 的真实缺口是 **33 项独立 required inputs**：其中 17 项已有模块可作为接线起点，16 项在当前产品路径仍为未建；C1 v2 目前没有任何 required input 被两个章节复用，因此按该契约计算，最高杠杆也只是 1 个章节。
