# Estimated USD cost from local tokens

This is the default cost path. It needs no GitHub login or billing role.
It estimates recorded model activity, not actual charges or measured account
credit consumption. Always use the word **estimated** for USD and credit totals.

## Sources and assumptions

1. Discover models and token fields through the authorized personal history
   tool described in `local-activity.md`. Do not read raw databases, internal
   cost/multiplier fields, prompts, or another user's history.
2. Read https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing
   using an available web/documentation tool. Extract only the rates and
   context thresholds needed for the recorded models. Rates are USD per
   1 million tokens, not per individual token. Verify USD per AI credit there
   or at https://docs.github.com/en/billing/concepts/product-billing/github-copilot-billing.
3. Match exact recorded model IDs to documented names. Cosmetic spaces/case
   can be normalized only when unambiguous. Do not guess aliases, versions,
   fast-mode mappings, hidden Auto selections, or unpublished models. Leave
   unmatched models unpriced. A missing price is not zero.
4. Declare input/cache semantics. The default local-app estimate explicitly
   ASSUMES `includes_cache`: input includes disjoint cached-read/cache-write
   categories. This is not established by field names alone. If the host
   documents separate uncached input, choose `excludes_cache` instead.
   Report this assumption with the estimate, and exclude impossible records.
   Reasoning tokens are not added to output again; the SDK describes them as
   a subset of output. Do not separately add tool tokens.
5. Date the rates. Repricing older records at today's verified rates is an
   estimate, not a reconstruction of historical bills. Disclose promotions,
   special modes, or rate-date uncertainty; exclude ambiguous model matches.
   Do not silently substitute another provider's API prices.

Do not claim the calculator verified a pricing source itself. It has no network
access; the calling agent must verify the supplied rate table from the official
page. If that cannot be done, return the local token report with a precise
pricing-data limitation rather than invent rates.

## Calculate with the offline helper

Create a temporary JSON input in the session artifact directory, outside the
repository. Never publish the user's usage rows. Use this shape, replacing all
example values with the actual date range, exact models, and verified rates:

```json
{
  "pricing_source": "https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing",
  "pricing_checked_at": "2026-10-04",
  "captured_at": "2026-10-04T12:00:00Z",
  "start": "2026-10-01",
  "end_exclusive": "2026-10-05",
  "input_semantics": "includes_cache",
  "usd_per_ai_credit": "0.01",
  "rates": {
    "gpt-5-mini": [
      {
        "up_to_input_tokens": null,
        "input": "0.25",
        "output": "2",
        "cached_input": "0.025",
        "cache_write": null
      }
    ]
  },
  "rows": []
}
```

Example rates are illustrative and must be reverified. Include all applicable
tiers for each matched model. A non-null `up_to_input_tokens` is an inclusive
per-request upper threshold; the following tier starts strictly above it.
The final tier uses null. Use null cache rates only for documented N/A or
unavailable pricing; positive usage in that category is then excluded.

Generate a bounded, aggregate-only query:

```powershell
python "<skill-directory>\scripts\estimate_tokens.py" "<session-artifact>\estimate.json" --query
```

Run the returned SQL using `session_store_sql` with `source: "local"`, not a
shell database reader. It groups compatible requests into context-size
buckets, keeping missing/invalid rows separate. It returns model, record/sample
counts, min/max per-request context, and sums of four token categories.
Copy the returned rows into the JSON's `rows` array, preserving nulls and values.

Then calculate:

```powershell
python "<skill-directory>\scripts\estimate_tokens.py" "<session-artifact>\estimate.json"
```

Python 3.9+ is needed for the helper, with no third-party dependencies. Do not
install a runtime without permission. If unavailable, use an available decimal
calculator with the same formulas and disclosure rules; never claim the helper
ran when it did not.

## Formulas

For input that includes cache categories:

`uncached_input = input_tokens - cache_read_tokens - cache_write_tokens`

For input that excludes cache categories:

`uncached_input = input_tokens`

In that second convention, per-request context includes input plus both cache
categories when selecting a tier.

`estimated_USD = (uncached_input * input_rate + output_tokens * output_rate + cache_read_tokens * cached_input_rate + cache_write_tokens * cache_write_rate) / 1,000,000`

`estimated_credit_equivalent = estimated_USD / verified_USD_per_AI_credit`

The helper sums exact decimal amounts before any display rounding. Format
USD to cents (or show additional decimals for amounts below one cent), not
each request rounded to cents. For example, two half-cent estimates sum to
one cent rather than two independently rounded cents.

## Coverage and display

- Show **Model | Input tokens | Output tokens | Total tokens | Cached tokens |
  Estimated USD**, plus totals. Existing token totals remain source-based;
  a model lacking pricing can still have token data.
- Label estimated credit equivalents separately from actual account credits.
  Do not fetch account balances merely to estimate local cost.
- Use only sums of priced rows for a partial USD total and label it **partial
  estimate**. State how many recorded requests were excluded and why, without
  adding an API-event column to the default report.
- If min/max context crosses pricing tiers, regroup; never select a tier from
  monthly accumulated input tokens. A capped 501-row query must be narrowed,
  not silently totaled.
- Missing or invalid token groups, cache totals exceeding inclusive input,
  unknown models, and unpriced positive cache categories are excluded explicitly.
- Include input-semantics assumption, pricing date/source, recorded range,
  and a short **Not an invoice; local records only** disclaimer.
- Subscription fees, discounts, taxes, included credits, shared-pool budgets,
  Actions minutes, and special billing adjustments are outside this estimate.

The helper does not inspect account identity or grant access: privacy must
already be enforced by the personal history tool used to supply its data.

Token-field reference:
https://github.com/github/copilot-sdk/blob/main/docs/features/streaming-events.md
