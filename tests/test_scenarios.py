import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from compare_scenarios import compare


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'examples' / 'scenario-comparison.json').read_text(encoding='utf-8'))

    def test_cash_shortfall_and_delayed_settlement(self):
        result = {s['name']: s for s in compare(self.data)['scenarios']}
        self.assertEqual(result['hold']['total_uncovered_when_due'], '3650.00')
        self.assertEqual(result['sale-on-time']['total_uncovered_when_due'], '0.00')
        self.assertEqual(result['sale-on-time']['closing_cash'], '1230.00')
        self.assertEqual(result['settlement-delayed']['total_uncovered_when_due'], '3650.00')
        self.assertEqual(result['settlement-delayed']['closing_cash'], '4880.00')
        self.assertEqual(result['price-stress']['total_uncovered_when_due'], '170.00')
        self.assertEqual(result['price-stress']['first_uncovered_date'], '2027-02-26')

    def test_does_not_mutate_baseline(self):
        snapshot = copy.deepcopy(self.data)
        compare(self.data)
        self.assertEqual(self.data, snapshot)

    def test_duplicate_names_and_baseline_sales_rejected(self):
        self.data['scenarios'][1]['name'] = self.data['scenarios'][0]['name']
        with self.assertRaises(ValueError):
            compare(self.data)
        self.data['scenarios'][1]['name'] = 'different'
        self.data['base']['sales'] = self.data['scenarios'][1]['sales']
        with self.assertRaises(ValueError):
            compare(self.data)


if __name__ == '__main__':
    unittest.main()
