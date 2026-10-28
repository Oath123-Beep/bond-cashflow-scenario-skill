"""Offline fixed-cash-flow arithmetic for transparent educational scenarios.

The user supplies every cash-flow date, sale entitlement cutoff and price.
The program does not retrieve prices, infer market conventions or recommend trades.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from pathlib import Path

getcontext().prec = 32
ZERO = Decimal("0")
HUNDRED = Decimal("100")


def dec(value, name):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name}: expected a decimal number") from exc
    if not result.is_finite():
        raise ValueError(f"{name}: expected a finite number")
    return result


def nonnegative(value, name):
    result = dec(value, name)
    if result < ZERO:
        raise ValueError(f"{name}: cannot be negative")
    return result


def day(value, name):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}: expected YYYY-MM-DD") from exc


def rendered(value):
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def price(data):
    day(data["valuation_date"], "valuation_date")
    face = nonnegative(data["face_amount"], "face_amount")
    frequency = data["frequency_per_year"]
    if isinstance(frequency, bool) or not isinstance(frequency, int) or frequency < 1:
        raise ValueError("frequency_per_year: expected a positive integer")
    annual_yield = dec(data["annual_nominal_yield"], "annual_nominal_yield")
    factor = Decimal("1") + annual_yield / Decimal(frequency)
    if factor <= ZERO:
        raise ValueError("period discount factor must be positive")
    entries = data["cashflows"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("cashflows: expected a nonempty array")
    per_100 = ZERO
    rows = []
    for item in entries:
        period = item["period"]
        if isinstance(period, bool) or not isinstance(period, int) or not 0 <= period <= 1000:
            raise ValueError("period: expected an integer between 0 and 1000")
        amount = nonnegative(item["amount_per_100"], "amount_per_100")
        present = amount / factor ** period
        per_100 += present
        rows.append({"period": period, "cashflow_per_100": str(amount),
                     "present_value_per_100": rendered(present)})
    return {"mode": "price", "valuation_date": data["valuation_date"],
            "price_type": "theoretical PV of supplied cash flows; full-price interpretation requires complete matching settlement cash flows; not a quote",
            "price_per_100": rendered(per_100),
            "total_value": rendered(per_100 * face / HUNDRED),
            "cashflows": rows,
            "assumptions": "Equal periods; nominal annual yield compounded at the stated frequency. User-supplied cash flows. Excludes credit, taxes, liquidity and trading costs."}


def ledger(data):
    as_of = day(data["as_of"], "as_of")
    through = day(data["analysis_through"], "analysis_through")
    if through < as_of:
        raise ValueError("analysis_through must be on/after as_of")
    cash = nonnegative(data["initial_cash"], "initial_cash")
    raw_bonds = data["bonds"]
    if not isinstance(raw_bonds, list) or not raw_bonds:
        raise ValueError("bonds: expected a nonempty array")
    bonds = {}
    for item in raw_bonds:
        key = item["id"]
        if not isinstance(key, str) or not key or key in bonds:
            raise ValueError("bond id must be a unique nonempty string")
        holding = nonnegative(item["face_held"], f"{key}.face_held")
        flows = []
        principal_flows = []
        all_flow_dates = []
        for flow in item["cashflows"]:
            flow_day = day(flow["date"], f"{key}.cashflow.date")
            if flow["kind"] not in ("coupon", "principal"):
                raise ValueError("cashflow kind must be coupon or principal")
            amount = nonnegative(flow["amount_per_100"], f"{key}.cashflow.amount")
            all_flow_dates.append(flow_day)
            if flow["kind"] == "principal":
                principal_flows.append((flow_day, amount))
            if flow_day > as_of:
                flows.append((flow_day, flow["kind"], amount))
        if len(principal_flows) != 1 or principal_flows[0][1] != HUNDRED:
            raise ValueError(f"{key}: exactly one explicit principal cash flow of 100 per 100 face is required; amortizing/unknown maturity is unsupported")
        maturity = principal_flows[0][0]
        if maturity <= as_of or any(flow_day > maturity for flow_day in all_flow_dates):
            raise ValueError(f"{key}: bond must mature after as_of; cash flows after maturity are unsupported")
        bonds[key] = {"face": holding, "cashflows": flows, "sales": [], "maturity": maturity}

    events = {}

    def event(date_key):
        return events.setdefault(date_key, {"flows": [], "sales": [], "requirements": []})

    for item in data.get("sales", []):
        key = item["bond_id"]
        if key not in bonds:
            raise ValueError(f"unknown bond_id: {key}")
        face = nonnegative(item["face"], "sale.face")
        trade = day(item["trade_date"], "sale.trade_date")
        settlement = day(item["settlement_date"], "sale.settlement_date")
        cutoff = day(item["entitlement_cutoff"], "sale.entitlement_cutoff")
        if trade < as_of or settlement < trade or cutoff < trade:
            raise ValueError("sale dates must be on/after as_of; settlement and entitlement cutoff on/after trade")
        if trade > through or settlement > through:
            raise ValueError("sale trade and settlement must be within the analysis horizon")
        maturity = bonds[key]["maturity"]
        if trade >= maturity or settlement >= maturity or cutoff > maturity:
            raise ValueError(f"{key}: sale trade and settlement must precede principal payment; entitlement cutoff cannot follow maturity")
        dirty = nonnegative(item["dirty_price_per_100"], "sale.dirty_price_per_100")
        fee = nonnegative(item["fee"], "sale.fee")
        net = face * dirty / HUNDRED - fee
        if net < ZERO:
            raise ValueError("sale fee exceeds hypothetical proceeds")
        bonds[key]["sales"].append({"face": face, "cutoff": cutoff})
        event(settlement)["sales"].append((key, net))

    for key, bond in bonds.items():
        sold = sum((item["face"] for item in bond["sales"]), ZERO)
        if sold > bond["face"]:
            raise ValueError(f"{key}: total sold face exceeds initial holding")
        for flow_day, kind, amount in bond["cashflows"]:
            if flow_day > through:
                continue
            surrendered = sum((sale["face"] for sale in bond["sales"]
                               if sale["cutoff"] <= flow_day), ZERO)
            eligible = bond["face"] - surrendered
            event(flow_day)["flows"].append((key, kind, eligible * amount / HUNDRED))

    for item in data["requirements"]:
        due = day(item["date"], "requirement.date")
        if due < as_of or due > through:
            raise ValueError("requirement.date must be within the analysis horizon")
        amount = nonnegative(item["amount"], "requirement.amount")
        event(due)["requirements"].append(amount)

    total_uncovered = ZERO
    rows = []
    for event_day in sorted(events):
        bucket = events[event_day]
        opening = cash
        sale_amount = sum((amount for _, amount in bucket["sales"]), ZERO)
        flow_amount = sum((amount for _, _, amount in bucket["flows"]), ZERO)
        required = sum(bucket["requirements"], ZERO)
        available = opening + sale_amount + flow_amount
        paid = min(available, required)
        uncovered = required - paid
        cash = available - paid
        total_uncovered += uncovered
        rows.append({"date": event_day.isoformat(), "opening_cash": rendered(opening),
                     "sale_proceeds": rendered(sale_amount),
                     "contractual_cashflow": rendered(flow_amount),
                     "requirement": rendered(required), "paid_from_available_cash": rendered(paid),
                     "uncovered_requirement": rendered(uncovered), "closing_cash": rendered(cash),
                     "cashflow_details": [{"bond_id": key, "kind": kind, "amount": rendered(amount)}
                                          for key, kind, amount in bucket["flows"]]})
    return {"mode": "ledger", "as_of": data["as_of"], "analysis_through": data["analysis_through"], "rows": rows,
            "total_uncovered_when_due": rendered(total_uncovered),
            "closing_cash": rendered(cash),
            "assumptions": "Same-day settlement and bond cash flows are available before same-day requirements. Shortfalls are recorded when due and are not backfilled. No borrowing, taxes, defaults or trade execution modeled."}


def main(argv):
    if len(argv) != 3 or argv[1] not in ("price", "ledger"):
        print("Usage: python bond_cashflow.py price|ledger INPUT.json", file=sys.stderr)
        return 2
    try:
        with Path(argv[2]).open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        result = price(data) if argv[1] == "price" else ledger(data)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError,
            InvalidOperation, OverflowError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
