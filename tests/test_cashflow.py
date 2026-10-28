import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bond_cashflow', ROOT / 'scripts' / 'bond_cashflow.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def scenario():
    return {
        'as_of': '2026-01-01', 'analysis_through': '2026-12-31', 'initial_cash': '20',
        'bonds': [{'id': 'B1', 'face_held': '1000', 'cashflows': [
            {'date': '2026-07-01', 'kind': 'coupon', 'amount_per_100': '5'},
            {'date': '2027-01-01', 'kind': 'coupon', 'amount_per_100': '5'},
            {'date': '2027-01-01', 'kind': 'principal', 'amount_per_100': '100'}]}],
        'sales': [], 'requirements': []}


class FinancialInvariants(unittest.TestCase):
    def test_textbook_nominal_price(self):
        with (ROOT / 'examples' / 'price.json').open(encoding='utf-8') as f:
            result = mod.price(json.load(f))
        self.assertEqual(result['total_value'], '965.35')
        self.assertEqual(result['price_per_100'], '96.53')

    def test_real_terms_simulated_two_payment_scenario(self):
        with (ROOT / 'examples' / 'real-bond-scenario.json').open(encoding='utf-8') as f:
            result = mod.ledger(json.load(f))
        rows = {r['date']: r for r in result['rows']}
        self.assertEqual(rows['2026-12-11']['contractual_cashflow'], '1850.00')
        self.assertEqual(rows['2026-12-15']['uncovered_requirement'], '0.00')
        self.assertEqual(rows['2027-03-01']['uncovered_requirement'], '3650.00')
        self.assertEqual(result['total_uncovered_when_due'], '3650.00')
        self.assertNotIn('2028-12-11', rows)

    def test_earlier_shortfall_is_not_backfilled(self):
        data = scenario()
        data['requirements'] = [{'date': '2026-02-01', 'amount': '100'}, {'date': '2026-07-02', 'amount': '10'}]
        result = mod.ledger(data)
        rows = {r['date']: r for r in result['rows']}
        self.assertEqual(rows['2026-02-01']['uncovered_requirement'], '80.00')
        self.assertEqual(rows['2026-07-02']['uncovered_requirement'], '0.00')
        self.assertEqual(result['total_uncovered_when_due'], '80.00')

    def test_partial_sale_does_not_credit_sold_coupon(self):
        data = scenario()
        data['sales'] = [{'bond_id': 'B1', 'face': '300', 'trade_date': '2026-03-01',
            'settlement_date': '2026-03-02', 'entitlement_cutoff': '2026-03-01',
            'dirty_price_per_100': '99', 'fee': '2'}]
        result = mod.ledger(data)
        rows = {r['date']: r for r in result['rows']}
        self.assertEqual(rows['2026-03-02']['sale_proceeds'], '295.00')
        self.assertEqual(rows['2026-07-01']['contractual_cashflow'], '35.00')

    def test_same_day_initial_cash_excludes_reprocessing_its_coupon(self):
        data = scenario()
        data['bonds'][0]['cashflows'].insert(0, {'date': '2026-01-01', 'kind': 'coupon', 'amount_per_100': '5'})
        data['requirements'] = [{'date': '2026-01-01', 'amount': '25'}]
        result = mod.ledger(data)
        first = result['rows'][0]
        self.assertEqual(first['contractual_cashflow'], '0.00')
        self.assertEqual(first['uncovered_requirement'], '5.00')

    def test_settlement_date_before_payment_covers_requirement(self):
        data = scenario()
        data['sales'] = [{'bond_id': 'B1', 'face': '100', 'trade_date': '2026-03-01',
            'settlement_date': '2026-03-02', 'entitlement_cutoff': '2026-03-01',
            'dirty_price_per_100': '100', 'fee': '0'}]
        data['requirements'] = [{'date': '2026-03-02', 'amount': '110'}]
        result = mod.ledger(data)
        first = result['rows'][0]
        self.assertEqual(first['sale_proceeds'], '100.00')
        self.assertEqual(first['uncovered_requirement'], '0.00')
        self.assertEqual(first['closing_cash'], '10.00')

    def test_sale_settling_after_deadline_does_not_cover(self):
        data = scenario()
        data['sales'] = [{'bond_id': 'B1', 'face': '100', 'trade_date': '2026-03-01',
            'settlement_date': '2026-03-03', 'entitlement_cutoff': '2026-03-01',
            'dirty_price_per_100': '100', 'fee': '0'}]
        data['requirements'] = [{'date': '2026-03-02', 'amount': '110'}]
        result = mod.ledger(data)
        self.assertEqual(result['rows'][0]['uncovered_requirement'], '90.00')
        self.assertEqual(result['total_uncovered_when_due'], '90.00')

    def test_missing_price_is_rejected(self):
        data = scenario()
        data['sales'] = [{'bond_id': 'B1', 'face': '100', 'trade_date': '2026-03-01',
            'settlement_date': '2026-03-02', 'entitlement_cutoff': '2026-03-01', 'fee': '0'}]
        with self.assertRaises(KeyError):
            mod.ledger(data)

    def test_overselling_rejected(self):
        data = scenario()
        data['sales'] = [{'bond_id': 'B1', 'face': '1001', 'trade_date': '2026-03-01',
            'settlement_date': '2026-03-02', 'entitlement_cutoff': '2026-03-01',
            'dirty_price_per_100': '100', 'fee': '0'}]
        with self.assertRaises(ValueError):
            mod.ledger(data)

    def test_negative_or_nonfinite_cash_rejected(self):
        for value in ['-1', 'NaN', 'Infinity']:
            data = scenario()
            data['initial_cash'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                mod.ledger(data)

    def test_invalid_dates_and_horizon_rejected(self):
        data = scenario()
        data['requirements'] = [{'date': '2027-01-01', 'amount': '10'}]
        with self.assertRaises(ValueError):
            mod.ledger(data)
        data = scenario()
        data['analysis_through'] = '2025-12-31'
        with self.assertRaises(ValueError):
            mod.ledger(data)

    def test_sale_after_maturity_rejected(self):
        data = scenario()
        data['analysis_through'] = '2027-02-01'
        data['sales'] = [{'bond_id': 'B1', 'face': '100', 'trade_date': '2027-01-01',
            'settlement_date': '2027-01-02', 'entitlement_cutoff': '2027-01-01',
            'dirty_price_per_100': '100', 'fee': '0'}]
        with self.assertRaises(ValueError):
            mod.ledger(data)

    def test_periodic_yield_domain_rejected(self):
        data = {'valuation_date': '2026-01-01', 'face_amount': '100', 'frequency_per_year': 2,
                'annual_nominal_yield': '-2', 'cashflows': [{'period': 1, 'amount_per_100': '100'}]}
        with self.assertRaises(ValueError):
            mod.price(data)


if __name__ == '__main__':
    unittest.main()
