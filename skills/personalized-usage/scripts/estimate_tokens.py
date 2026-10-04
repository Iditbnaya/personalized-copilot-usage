"""Estimate recorded token usage at supplied, verified GitHub Copilot rates.

Offline only: no authentication, database access, or network requests.
"""

import argparse
import datetime as dt
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys


PRICING_SOURCE = "https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing"
TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
RATE_FIELDS = ("input", "output", "cached_input", "cache_write")


class EstimateError(ValueError):
    pass


def amount(value, name):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise EstimateError(f"{name} must be a finite nonnegative decimal.")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise EstimateError(f"{name} is not a decimal.") from exc
    if not number.is_finite() or number < 0:
        raise EstimateError(f"{name} must be finite and nonnegative.")
    return number


def integer(value, name):
    number = amount(value, name)
    if number != number.to_integral_value():
        raise EstimateError(f"{name} must be an integer.")
    return int(number)


def validate_config(config):
    if config.get("pricing_source") != PRICING_SOURCE:
        raise EstimateError("Use rates verified from the official GitHub Copilot pricing page.")
    try:
        checked = dt.date.fromisoformat(config["pricing_checked_at"])
        start = dt.date.fromisoformat(config["start"])
        end = dt.date.fromisoformat(config["end_exclusive"])
        if any(value.isoformat() != config[key] for key, value in (
            ("pricing_checked_at", checked), ("start", start), ("end_exclusive", end)
        )):
            raise ValueError("Dates must use YYYY-MM-DD")
        captured = dt.datetime.fromisoformat(config["captured_at"].replace("Z", "+00:00"))
        if captured.utcoffset() != dt.timedelta(0):
            raise ValueError("Capture time must be UTC")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise EstimateError("Supply ISO start/end dates, pricing_checked_at, and UTC captured_at.") from exc
    if not 0 < (end - start).days <= 93:
        raise EstimateError("Choose an exclusive-end range of 1 to 93 days.")
    if config.get("input_semantics") not in ("includes_cache", "excludes_cache"):
        raise EstimateError("Explicitly choose includes_cache or excludes_cache input semantics.")
    credit_rate = amount(config.get("usd_per_ai_credit"), "usd_per_ai_credit")
    if credit_rate == 0:
        raise EstimateError("usd_per_ai_credit must be positive.")
    models = config.get("rates")
    if not isinstance(models, dict) or not models:
        raise EstimateError("Provide a nonempty rate map keyed by exact recorded model IDs.")
    for model, tiers in models.items():
        if not isinstance(model, str) or not model or not isinstance(tiers, list) or not tiers:
            raise EstimateError("Every model must have a nonempty tier list.")
        previous = 0
        for index, tier in enumerate(tiers):
            if not isinstance(tier, dict) or "up_to_input_tokens" not in tier:
                raise EstimateError(f"Missing tier boundary for {model}.")
            boundary = tier["up_to_input_tokens"]
            if boundary is None:
                if index != len(tiers) - 1:
                    raise EstimateError("Only the final tier may have an unlimited boundary.")
            else:
                boundary = integer(boundary, "up_to_input_tokens")
                if boundary <= previous:
                    raise EstimateError("Tier boundaries must be increasing positive integers.")
                previous = boundary
            for field in RATE_FIELDS:
                if field not in tier:
                    raise EstimateError(f"Missing {field} rate for {model}.")
                if tier[field] is None:
                    if field in ("input", "output"):
                        raise EstimateError(f"{field} rate must be numeric.")
                else:
                    amount(tier[field], field)
        if tiers[-1]["up_to_input_tokens"] is not None:
            raise EstimateError("The final tier must specify a null upper boundary.")
    return credit_rate


def make_query(config):
    validate_config(config)
    boundaries = sorted({
        integer(tier["up_to_input_tokens"], "tier boundary")
        for tiers in config["rates"].values() for tier in tiers
        if tier["up_to_input_tokens"] is not None
    })
    context = "input_tokens"
    if config["input_semantics"] == "excludes_cache":
        context += " + cache_read_tokens + cache_write_tokens"
    valid = " AND ".join(f"typeof({f}) = 'integer' AND {f} >= 0" for f in TOKEN_FIELDS)
    if config["input_semantics"] == "includes_cache":
        valid += " AND cache_read_tokens + cache_write_tokens <= input_tokens"
    bucket = "0"
    if boundaries:
        bucket = ("CASE " + " ".join(
            f"WHEN context_tokens <= {b} THEN {i}" for i, b in enumerate(boundaries)
        ) + f" ELSE {len(boundaries)} END")
    sums = ",\n       ".join(f"SUM({f}) AS {f}" for f in TOKEN_FIELDS)
    # Only validated dates/timestamps and integer boundaries are interpolated.
    captured = dt.datetime.fromisoformat(config["captured_at"].replace("Z", "+00:00")).isoformat()
    return f"""WITH selected AS (
    SELECT model, {', '.join(TOKEN_FIELDS)},
           ({context}) AS context_tokens,
           CASE WHEN {valid} THEN 1 ELSE 0 END AS valid
    FROM assistant_usage_events
    WHERE substr(created_at, 1, 10) >= '{config["start"]}'
      AND substr(created_at, 1, 10) < '{config["end_exclusive"]}'
      AND julianday(created_at) <= julianday('{captured}')
)
SELECT model, COUNT(*) AS records, SUM(valid) AS valid_records,
       MIN(context_tokens) AS min_context_tokens,
       MAX(context_tokens) AS max_context_tokens,
       {sums}
FROM selected
GROUP BY model, valid, {bucket}
ORDER BY model, MIN(context_tokens), valid
LIMIT 501"""


def tier_for(tiers, context):
    for index, tier in enumerate(tiers):
        boundary = tier["up_to_input_tokens"]
        if boundary is None or context <= integer(boundary, "tier boundary"):
            return index, tier
    raise EstimateError("No applicable pricing tier.")


def price_group(row, tiers, semantics):
    if integer(row.get("valid_records"), "valid_records") != integer(row.get("records"), "records"):
        raise EstimateError("Missing, negative, or non-integer token records.")
    tokens = {field: integer(row.get(field), field) for field in TOKEN_FIELDS}
    low = integer(row.get("min_context_tokens"), "min_context_tokens")
    high = integer(row.get("max_context_tokens"), "max_context_tokens")
    if low > high:
        raise EstimateError("Invalid per-record context range.")
    context_sum = tokens["input_tokens"]
    if semantics == "excludes_cache":
        context_sum += tokens["cache_read_tokens"] + tokens["cache_write_tokens"]
    records = integer(row["records"], "records")
    if not low * records <= context_sum <= high * records:
        raise EstimateError("Context range is inconsistent with token sums.")
    first, tier = tier_for(tiers, low)
    if tier_for(tiers, high)[0] != first:
        raise EstimateError("Group spans pricing tiers; regenerate the bucketed query.")
    fresh = tokens["input_tokens"]
    if semantics == "includes_cache":
        fresh -= tokens["cache_read_tokens"] + tokens["cache_write_tokens"]
        if fresh < 0:
            raise EstimateError("Cached read/write counts exceed input; check input semantics.")
    quantities = (fresh, tokens["output_tokens"], tokens["cache_read_tokens"], tokens["cache_write_tokens"])
    cost = Decimal(0)
    for field, quantity in zip(RATE_FIELDS, quantities):
        rate = tier[field]
        if rate is None:
            if quantity:
                raise EstimateError(f"{field} tokens are present but their rate is unavailable.")
        else:
            cost += Decimal(quantity) * amount(rate, field) / Decimal(1_000_000)
    return cost


def estimate(config):
    credit_rate = validate_config(config)
    rows = config.get("rows")
    if not isinstance(rows, list):
        raise EstimateError("Provide query result rows as an array.")
    if len(rows) >= 501:
        raise EstimateError("Query results may be truncated. Narrow the range before estimating.")
    groups = {}
    total_records = 0
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("model"), str) or not row["model"]:
            raise EstimateError("Each aggregate row needs an exact model identifier.")
        count = integer(row.get("records"), "records")
        if count == 0:
            raise EstimateError("Aggregate rows must contain at least one record.")
        total_records += count
        model = row["model"]
        group = groups.setdefault(model, {
            "model": model, "records": 0, "priced_records": 0,
            "estimated_usd": Decimal(0), "exclusions": [],
        })
        group["records"] += count
        tiers = config["rates"].get(model)
        try:
            if tiers is None:
                raise EstimateError("No verified exact-model pricing match.")
            cost = price_group(row, tiers, config["input_semantics"])
        except EstimateError as exc:
            group["exclusions"].append({"records": count, "reason": str(exc)})
            continue
        group["estimated_usd"] += cost
        group["priced_records"] += count
    priced = sum(g["priced_records"] for g in groups.values())
    total = sum((g["estimated_usd"] for g in groups.values()), Decimal(0)) if priced else None
    for group in groups.values():
        group["status"] = ("unavailable" if not group["priced_records"] else
                           "partial" if group["exclusions"] else "estimated")
        if not group["priced_records"]:
            group["estimated_usd"] = None
        group["estimated_credit_equivalent"] = (
            group["estimated_usd"] / credit_rate if group["estimated_usd"] is not None else None
        )
    return {
        "status": ("no_local_records" if not rows else "unavailable" if not priced else
                   "partial" if priced != total_records else "estimated"),
        "scope": "Recorded local app activity repriced at the supplied GitHub Copilot rates",
        "start": config["start"], "end_exclusive": config["end_exclusive"],
        "captured_at": config["captured_at"],
        "pricing_source": PRICING_SOURCE, "pricing_checked_at": config["pricing_checked_at"],
        "input_semantics_assumption": config["input_semantics"],
        "assumptions": [
            "Cached read/write categories are disjoint; their inclusion in input follows the selected assumption.",
            "Output includes reasoning tokens; reasoning is not added again.",
            "Context tiers apply per request, not to accumulated monthly tokens.",
            "Current supplied rates reprice history; historical rates, special modes, and promotions may differ.",
            "No subscription fees, discounts, taxes, Actions minutes, or organization billing adjustments included.",
        ],
        "estimated_usd": total,
        "estimated_credit_equivalent": total / credit_rate if total is not None else None,
        "records": total_records, "priced_records": priced,
        "by_model": sorted(groups.values(), key=lambda g: g["model"]),
        "billing_warning": "ESTIMATE ONLY. Not actual billed charges or measured account credits.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Trusted local JSON with verified rates and aggregate rows")
    parser.add_argument("--query", action="store_true", help="Print SQL for session_store_sql; do not execute it")
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.input.read_text(encoding="utf-8"), parse_float=Decimal)
        if not isinstance(config, dict):
            raise EstimateError("Input must be a JSON object.")
        if args.query:
            print(make_query(config))
        else:
            print(json.dumps(estimate(config), default=str, indent=2))
    except (EstimateError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
