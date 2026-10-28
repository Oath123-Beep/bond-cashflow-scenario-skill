"""Reproduce one textbook bond PV comparison; dates are illustrative, not market rules."""
import json
import sys
from decimal import Decimal
from pathlib import Path

try:
    import QuantLib as ql
except ImportError as exc:
    raise SystemExit('Install optional dependency: python -m pip install QuantLib') from exc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from bond_cashflow import price

with (ROOT / 'examples' / 'price.json').open(encoding='utf-8-sig') as f:
    data = json.load(f)

if data['valuation_date'] != '2026-01-01' or data['frequency_per_year'] != 2:
    raise ValueError('This comparison is limited to the bundled textbook case')
if Decimal(str(data['face_amount'])) != Decimal('1000') or Decimal(str(data['annual_nominal_yield'])) != Decimal('0.12'):
    raise ValueError('This comparison is limited to the bundled textbook case')
expected = [(1, Decimal('5')), (2, Decimal('5')), (3, Decimal('5')), (4, Decimal('105'))]
flows = [(c['period'], Decimal(str(c['amount_per_100']))) for c in data['cashflows']]
if flows != expected:
    raise ValueError('Unexpected example cash flows')

valuation = ql.Date(1, 1, 2026)
maturity = ql.Date(1, 1, 2028)
ql.Settings.instance().evaluationDate = valuation
schedule = ql.Schedule(valuation, maturity, ql.Period(ql.Semiannual),
                       ql.NullCalendar(), ql.Unadjusted, ql.Unadjusted,
                       ql.DateGeneration.Forward, False)
day_count = ql.ActualActual(ql.ActualActual.Bond, schedule)
bond = ql.FixedRateBond(0, 1000.0, schedule, [0.10], day_count,
                        ql.Unadjusted, 100.0, valuation)
dirty = bond.dirtyPrice(0.12, day_count, ql.Compounded, ql.Semiannual, valuation)
clean = bond.cleanPrice(0.12, day_count, ql.Compounded, ql.Semiannual, valuation)
accrued = bond.accruedAmount(valuation)
observed = {}
for cf in bond.cashflows():
    if cf.date() > valuation:
        key = cf.date().ISO()
        observed[key] = observed.get(key, 0.0) + cf.amount()
expected_dates = ['2026-07-01', '2027-01-01', '2027-07-01', '2028-01-01']
actual_cashflows = [observed.get(date, 0.0) for date in expected_dates]
if len(observed) != 4 or any(abs(a-b)>1e-8 for a,b in zip(actual_cashflows,[50,50,50,1050])):
    raise AssertionError(f'Cash flows do not match: {observed!r}')
manual = sum(amount / (1.06 ** period) for period, amount in enumerate([50,50,50,1050], 1))
project = price(data)
total = dirty * 1000.0 / 100.0
difference = abs(total-manual)
if difference > 0.000001:
    raise AssertionError(f'QuantLib vs manual mismatch: {difference}')
if abs(total-float(project['total_value'])) > 0.0051:
    raise AssertionError('QuantLib vs rounded project total mismatch')
output = {
    'quantlib_version': ql.__version__,
    'valuation_date': valuation.ISO(),
    'settlement_date': valuation.ISO(),
    'calendar': 'NullCalendar; unadjusted; illustrative only',
    'day_count': 'ActualActual(Bond, schedule)',
    'nominal_yield': 0.12,
    'compounding': 'semiannual',
    'quantlib_cashflows_by_date': observed,
    'dirty_price_per_100': dirty,
    'clean_price_per_100': clean,
    'accrued_per_100': accrued,
    'quantlib_value_for_1000_face': total,
    'manual_value_for_1000_face': manual,
    'project_rounded_total': project['total_value'],
    'absolute_difference_quantlib_vs_manual': difference,
    'limitations': 'One synthetic regular-period case. Not observed prices, a trading calendar, or validation of other bonds, contracts or settlement conventions.'
}
print(json.dumps(output, ensure_ascii=False, indent=2))
