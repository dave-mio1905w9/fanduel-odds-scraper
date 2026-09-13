import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fd_client import FanDuelClient, FanDuelError

# Sports I actually track; kept small because I only watch these
DEFAULT_SPORTS = ["NBA", "NFL", "NHL", "MLB"]

# Output keys we keep to keep jsonl lines short

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fanduel_odds",
        usage="python fanduel_odds.py --sport NBA [--sport NFL] [-o odds.jsonl]",
        description="Scrape live moneyline/spread odds from FanDuel and dump as JSONL.",
    )
    parser.add_argument(
        "--sport",
        action="append",
        dest="sports",
        help="Sport to scrape (can pass multiple). Defaults to NBA/NFL/NHL/MLB.",
    )
    parser.add_argument(
        "-o", "--output",
        default="odds.jsonl",
        help="Output JSONL file path (default: odds.jsonl)",
    )
    parser.add_argument(
        "--live-only",
        action="store_true",
        help="Only include live/in-play markets",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.8,
        help="Seconds between requests (default: 0.8)",
    )
    return parser.parse_args()

def extract_market(market: Dict[str, Any], event: Dict[str, Any], now: str) -> Optional[Dict[str, Any]]:
    """Pull the fields we care about from a single market dict."""
    market_id = market.get("marketId")
    market_name = market.get("marketName")
    if not market_id or not market_name:
        return None
    # Only care about moneyline and spread for now
    name_upper = market_name.upper()
    if "MONEYLINE" not in name_upper and "SPREAD" not in name_upper:
        return None
    runners = market.get("runners", [])
    if not runners:
        return None
    # Take the first runner as representative; FanDuel usually has one runner per side
    runner = runners[0]
    record = {
        "ts": now,
        "eventId": event.get("eventId"),
        "eventName": event.get("name"),
        "startTime": event.get("startDate"),
        "marketId": market_id,
        "marketName": market_name,
        "runnerName": runner.get("runnerName"),
        "line": runner.get("line"),
        "oddsAmerican": runner.get("oddsAmerican"),
        "oddsDecimal": runner.get("oddsDecimal"),
        "isLive": market.get("isLive", False),
    }
    return record

def fetch_sport(client: FanDuelClient, sport: str, args: argparse.Namespace) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    try:
        events = client.get_events(sport)
    except FanDuelError as exc:
        print(f"[{sport}] failed to fetch events: {exc}", file=sys.stderr)
        return records
    for event in events:
        event_id = event.get("eventId")
        if not event_id:
            continue
        try:
            markets = client.get_event_markets(event_id)
        except FanDuelError as exc:
            print(f"[{sport}] event {event_id} markets failed: {exc}", file=sys.stderr)
            continue
        for market in markets:
            rec = extract_market(market, event, now)
            if rec is None:
                continue
            if args.live_only and not rec["isLive"]:
                continue
            records.append(rec)
        # small sleep between events to stay polite
        time.sleep(args.delay)
    return records

def main() -> int:
    args = parse_args()
    sports = args.sports or DEFAULT_SPORTS
    all_records: List[Dict[str, Any]] = []
    with FanDuelClient() as client:
        for sport in sports:
            print(f"fetching {sport} ...", file=sys.stderr)
            sport_records = fetch_sport(client, sport, args)
            all_records.extend(sport_records)
            print(f"  {len(sport_records)} records", file=sys.stderr)
    if not all_records:
        print("no records found", file=sys.stderr)
        return 1
    try:
        with open(args.output, "a", encoding="utf-8") as f:
            for rec in all_records:
                f.write(json.dumps(rec, separators=(",", ":")))
                f.write("\n")
    except OSError as exc:
        print(f"failed to write {args.output}: {exc}", file=sys.stderr)
        return 1
    print(f"appended {len(all_records)} lines to {args.output}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        sys.exit(130)
