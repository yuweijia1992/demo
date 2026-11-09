import unittest
from scripts.build_valuation_model import (
    calc_invested_capital,
    current_interest_bearing_debt,
    cash_equivalents_for_net_debt,
)

class ValuationMethodTests(unittest.TestCase):
    def test_invested_capital_does_not_double_add_long_term_debt(self):
        # 1,000 - (200 - 40) - 100 - 50 - 20 = 670.
        # A long-term debt balance of 300 is intentionally not added a second time.
        self.assertEqual(calc_invested_capital(1000, 200, 40, 100, 50, 20), 670)

    def test_invested_capital_missing_component_stays_null(self):
        self.assertIsNone(calc_invested_capital(1000, 200, None, 100, 50, 20))

    def test_invested_capital_rejects_negative_operating_current_liabilities(self):
        self.assertIsNone(calc_invested_capital(1000, 20, 40, 100, 50, 20))

    def test_current_debt_requires_all_current_components(self):
        balance = {"fields": {
            "shortBorrowings": {"value": 10},
            "shortTermBonds": {"value": 20},
            "currentPortionLongTermDebt": {"value": 30},
            "currentLeaseLiabilities": {"value": 40},
        }}
        total, parts = current_interest_bearing_debt(balance)
        self.assertEqual(total, 100)
        self.assertEqual(parts["currentLeaseLiabilities"], 40)
        balance["fields"]["shortTermBonds"]["value"] = None
        total, _ = current_interest_bearing_debt(balance)
        self.assertIsNone(total)

    def test_restricted_money_funds_are_not_cash_deduction(self):
        balance = {"fields": {
            "cash": {"value": 500, "sourceField": "货币资金"},
            "cashAndCashEquivalents": {"value": 300, "sourceField": "现金及现金等价物"},
            "restrictedCash": {"value": 100},
        }}
        value, basis = cash_equivalents_for_net_debt(balance)
        self.assertEqual(value, 300)
        self.assertEqual(basis, "cash_and_cash_equivalents")

    def test_money_funds_without_cash_equivalent_breakdown_are_not_deducted(self):
        balance = {"fields": {"cash": {"value": 500, "sourceField": "货币资金"}}}
        value, basis = cash_equivalents_for_net_debt(balance)
        self.assertIsNone(value)
        self.assertEqual(basis, "cash_equivalents_not_separately_identified")

if __name__ == "__main__":
    unittest.main()
