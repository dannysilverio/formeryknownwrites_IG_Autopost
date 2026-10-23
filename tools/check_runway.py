#!/usr/bin/env python3
"""
Tells you how many days of new posts are left in calendar.json.

Prints the runway every time. Exits non-zero (which makes GitHub send a
failure email) only when the runway is short AND it is the one 9 AM ET check
of the day, so a stalled refill produces one email a day, not one every 15
minutes. The posting script's own recycle fallback keeps the page posting in
the meantime, so a warning here means "refill is stuck", not "page is silent".
"""
import datetime
import json
import os
import sys
import zoneinfo

WARN_BELOW_DAYS = 5

root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
cal = json.load(open(os.path.join(root, "calendar.json")))
now = datetime.datetime.now(zoneinfo.ZoneInfo("America/New_York"))
today = now.date().isoformat()

future_days = sorted({e["date"] for e in cal if e["date"] > today})
runway = len(future_days)
last = future_days[-1] if future_days else today
print(f"Runway: {runway} full day(s) of new posts after today (last scheduled date: {last}).")

morning_check = now.hour == 9 and now.minute < 15
if runway < WARN_BELOW_DAYS and morning_check:
    print(f"::error::Only {runway} day(s) of new posts left. The weekly refill may be stuck. "
          "Recycling older posts is covering the gap. Check the 'Refill content bank' workflow.")
    sys.exit(1)
