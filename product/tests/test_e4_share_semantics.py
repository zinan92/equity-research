from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data_core.e4_catl_financial_history import OfficialFinancialFact
class ShareSemanticsTest(unittest.TestCase):
 def test_share_count_uses_shares_not_currency_unit(self):
  amount=OfficialFinancialFact('300750.SZ','share_capital_amount',233085.12,'d','a'*64,110,'股本','股本 233,085.12','2022FY','consolidated','万元','CNY','https://x')
  count=OfficialFinancialFact('300750.SZ','shares_outstanding',4563868956,'d2','b'*64,6,'公司现有总股本','公司现有总股本 4,563,868,956 股','2025FY','share_count_disclosure','股','N/A','https://x')
  self.assertNotEqual(amount.value,count.value); self.assertEqual(count.unit,'股'); self.assertNotEqual(amount.unit,'股')
