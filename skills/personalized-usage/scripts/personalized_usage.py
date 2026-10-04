"""Read documented personal GitHub billing usage without Copilot CLI."""

import argparse
import calendar
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


API_VERSION = "2026-03-10"
SOURCES = ("ai_credit", "premium_request")
FIELDS = (
    "grossQuantity", "discountQuantity", "netQuantity",
    "grossAmount", "discountAmount", "netAmount",
)


class UsageError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise UsageError("GitHub API redirect refused; credentials were not forwarded.")


def parse_json(text: str) -> Dict[str, Any]:
    try:
        result = json.loads(text, parse_float=Decimal)
    except (ValueError, TypeError) as exc:
        raise UsageError("GitHub returned invalid JSON.") from exc
    if not isinstance(result, dict):
        raise UsageError("GitHub returned an unexpected response shape.")
    return result


class GitHub:
    def __init__(self):
        self.token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        self.gh = shutil.which("gh")
        if not self.token and not self.gh:
            raise UsageError(
                "No authentication for the optional personal-plan billing adapter. "
                "Use your own Usage card at https://github.com/settings/copilot "
                "instead. Copilot CLI is not required."
            )

    def get(self, path: str) -> Dict[str, Any]:
        if not path.startswith("/") or path.startswith("//"):
            raise UsageError("Only fixed GitHub API paths are supported.")
        if self.token:
            request = urllib.request.Request(
                "https://api.github.com" + path,
                headers={
                    "Authorization": "Bearer " + self.token,
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": API_VERSION,
                    "User-Agent": "personalized-usage-skill",
                },
            )
            try:
                with urllib.request.build_opener(NoRedirect()).open(
                    request, timeout=30
                ) as response:
                    text = response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                raise UsageError(
                    "GitHub API HTTP {}. Check personal billing access/authentication; "
                    "This optional adapter covers personally purchased plans only; "
                    "managed users should use https://github.com/settings/copilot."
                    .format(exc.code)
                ) from exc
            except (urllib.error.URLError, TimeoutError, UnicodeError) as exc:
                raise UsageError("GitHub API could not be reached or read.") from exc
        else:
            env = os.environ.copy()
            env.pop("GH_DEBUG", None)
            try:
                response = subprocess.run(
                    [self.gh, "api", "--hostname", "github.com",
                     "-H", "Accept: application/vnd.github+json",
                     "-H", "X-GitHub-Api-Version: " + API_VERSION, path],
                    capture_output=True, text=True, timeout=40, env=env,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise UsageError("Existing GitHub CLI authentication could not be used.") from exc
            if response.returncode:
                # Do not echo arbitrary stderr, tokens, or sensitive response bodies.
                raise UsageError(
                    "GitHub API request failed using existing gh authentication. "
                    "This optional adapter covers personally purchased plans only. "
                    "Use your own Usage card at https://github.com/settings/copilot "
                    "instead. No Copilot CLI is needed."
                )
            text = response.stdout
        return parse_json(text)


def dates(args, today: dt.date) -> Tuple[dt.date, dt.date]:
    if args.period != "custom" and (args.start or args.end):
        raise UsageError("--start and --end require --period custom.")
    if args.period == "custom":
        try:
            start = dt.date.fromisoformat(args.start or "")
            end = dt.date.fromisoformat(args.end or "")
        except ValueError as exc:
            raise UsageError("Custom ranges require --start and --end in YYYY-MM-DD.") from exc
    elif args.period == "previous-month":
        end = today.replace(day=1) - dt.timedelta(days=1)
        start = end.replace(day=1)
    elif args.period == "current-month":
        start = today.replace(day=1)
        end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
    elif args.period == "today":
        start = end = today
    else:
        length = 7 if args.period == "last-7-days" else 30
        start, end = today - dt.timedelta(days=length - 1), today
    if start > end or (end - start).days >= 93:
        raise UsageError("Choose an ordered range of at most 93 inclusive days.")
    if start > today or (end > today and args.period != "current-month"):
        raise UsageError("Future ranges are not supported.")
    return start, end


def filters(start: dt.date, end: dt.date) -> List[Dict[str, int]]:
    result = []
    cursor = start
    while cursor <= end:
        month_end = cursor.replace(
            day=calendar.monthrange(cursor.year, cursor.month)[1]
        )
        item = {"year": cursor.year, "month": cursor.month}
        if cursor.day == 1 and month_end <= end:
            cursor = month_end + dt.timedelta(days=1)
        else:
            item["day"] = cursor.day
            cursor += dt.timedelta(days=1)
        result.append(item)
    return result


def number(item: Dict[str, Any], field: str) -> Decimal:
    value = item.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise UsageError("GitHub usage field {} is missing or not numeric.".format(field))
    value = Decimal(value)
    if not value.is_finite():
        raise UsageError("GitHub returned a non-finite usage value.")
    return value


def validate_report(
    report: Dict[str, Any], login: str, period: Dict[str, int]
) -> List[Dict[str, Any]]:
    user = report.get("user")
    if not isinstance(user, str) or user.casefold() != login.casefold():
        raise UsageError("Report identity mismatch; usage was not disclosed.")
    if report.get("timePeriod") != period:
        raise UsageError("Report period mismatch; usage was not disclosed.")
    items = report.get("usageItems")
    if not isinstance(items, list):
        raise UsageError("GitHub usageItems is missing or not an array.")
    for item in items:
        if not isinstance(item, dict):
            raise UsageError("GitHub returned a malformed usage item.")
        for field in ("product", "sku", "model", "unitType"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise UsageError("GitHub usage field {} is missing or invalid.".format(field))
        for field in FIELDS:
            number(item, field)
    return items


def aggregate(items: List[Dict[str, Any]], by_model: bool) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    keys = ("product", "unitType", "model") if by_model else ("product", "unitType")
    for item in items:
        key = tuple(item[field] for field in keys)
        if key not in groups:
            groups[key] = dict(zip(keys, key))
            groups[key].update({field: Decimal(0) for field in FIELDS})
        for field in FIELDS:
            groups[key][field] += number(item, field)
    return [groups[key] for key in sorted(groups)]


def fetch_usage(client, start: dt.date, end: dt.date) -> Dict[str, Any]:
    login = client.get("/user").get("login")
    if not isinstance(login, str) or not login:
        raise UsageError("Could not resolve the authenticated GitHub identity.")
    encoded = urllib.parse.quote(login, safe="")
    query_periods = filters(start, end)
    sources = []
    for source in SOURCES:
        items = []
        failures = []
        non_copilot_rows = 0
        for period in query_periods:
            path = "/users/{}/settings/billing/{}/usage?{}".format(
                encoded, source, urllib.parse.urlencode(period)
            )
            try:
                rows = validate_report(client.get(path), login, period)
            except UsageError as exc:
                failures.append({"filter": period, "error": str(exc)})
                continue
            # Preserve actual product labels; never combine unrelated products.
            for row in rows:
                if "copilot" in row["product"].casefold():
                    items.append(row)
                else:
                    non_copilot_rows += 1
        succeeded = len(query_periods) - len(failures)
        status = (
            "unavailable" if not succeeded else
            "partial" if failures else
            "ok" if items else "no_personal_billing_rows"
        )
        sources.append({
            "source": source, "status": status,
            "successfulFilters": succeeded, "failedFilters": failures,
            "excludedNonCopilotRows": non_copilot_rows,
            "totalsByProductAndUnit": aggregate(items, False),
            "byModel": aggregate(items, True),
        })
    return {
        "user": login,
        "scope": "Copilot usage billed directly to this personal GitHub account",
        "coverageWarning": (
            "Organization/enterprise-funded usage is excluded. Empty personal "
            "reports do not establish zero total Copilot usage."
        ),
        "range": {"start": start.isoformat(), "end": end.isoformat(),
                  "filters": query_periods},
        "collectedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sources": sources,
        "unavailableFromTheseAPIs": [
            "input/output/cached/reasoning/tool token counts",
            "raw model invocation counts",
            "allocated quotas and remaining balances",
            "quota utilization percentages and reset timestamps",
        ],
        "calculation": (
            "Sum each API quantity/amount independently by product and unit; "
            "also by model for model rows. Do not combine the two billing sources. "
            "Billing amounts are not credit counts; currency is not specified."
        ),
    }


def json_number(value):
    if isinstance(value, Decimal):
        # Preserve billing precision in JSON without converting through floats.
        return str(value)
    raise TypeError("Unsupported JSON value.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--period", choices=("current-month", "previous-month", "today",
                             "last-7-days", "last-30-days", "custom"),
        default="current-month",
    )
    parser.add_argument("--start")
    parser.add_argument("--end")
    args = parser.parse_args(argv)
    try:
        start, end = dates(args, dt.datetime.now(dt.timezone.utc).date())
        report = fetch_usage(GitHub(), start, end)
    except UsageError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1
    print(json.dumps(report, default=json_number, indent=2))
    return 0 if all(
        source["status"] in ("ok", "no_personal_billing_rows")
        for source in report["sources"]
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
