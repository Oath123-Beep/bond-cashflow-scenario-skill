"""Compare sale scenarios against an identical cash-needs baseline."""
import copy
import json
import sys
from decimal import Decimal
from pathlib import Path
from bond_cashflow import ledger


def compare(data):
    base = data['base']
    scenarios = data['scenarios']
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError('scenarios must be a nonempty array')
    if base.get('sales'):
        raise ValueError('base sales must be empty; each scenario specifies all sales')
    names = set()
    results = []
    for scenario in scenarios:
        name = scenario['name']
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError('scenario names must be nonempty and unique')
        names.add(name)
        sales = scenario['sales']
        if not isinstance(sales, list):
            raise ValueError('scenario sales must be an array')
        inputs = copy.deepcopy(base)
        inputs['sales'] = sales
        result = ledger(inputs)
        shortages = [r for r in result['rows'] if Decimal(r['uncovered_requirement']) > 0]
        results.append({
            'name': name, 'assumption': scenario.get('assumption', ''), 'sales': sales,
            'first_uncovered_date': shortages[0]['date'] if shortages else None,
            'total_uncovered_when_due': result['total_uncovered_when_due'],
            'closing_cash': result['closing_cash'], 'timeline': result['rows'],
        })
    return {
        'mode': 'scenario_comparison', 'as_of': base['as_of'],
        'analysis_through': base['analysis_through'], 'scenarios': results,
        'assumptions': 'Identical initial cash, holdings, supplied cashflows and needs. Sales are hypothetical and not confirmed trades. Same-day receipts precede obligations. Unmet obligations are not backfilled. No optimization or trade feasibility inferred.'
    }


def main(argv):
    if len(argv) != 2:
        print('Usage: python scripts/compare_scenarios.py INPUT.json', file=sys.stderr)
        return 2
    try:
        with Path(argv[1]).open(encoding='utf-8-sig') as handle:
            output = compare(json.load(handle))
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
        print(f'Input error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
