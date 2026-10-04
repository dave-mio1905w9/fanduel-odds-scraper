# fanduel-odds-scraper

I got tired of refreshing FanDuel's site to watch lines move, so this scrapes their public API and dumps compact JSON lines I can grep through. Nothing fancy - just the sports I care about, no selenium, no browser automation.

## install

pip install -r requirements.txt

## usage

python fanduel_odds.py --sport NBA --output lines.jsonl

FanDuel's API doesn't require auth for basic odds, but they rate-limit aggressively. I sleep between requests and retry on 429s.

<!-- last-checked: 2026-10-04 -->
