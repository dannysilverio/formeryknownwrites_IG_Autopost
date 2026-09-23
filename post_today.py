#!/usr/bin/env python3
"""
Reads calendar.json (checked into this repo), finds the entry matching
today's date (America/New_York) and the current time slot, and publishes
it to Instagram via the Graph API. Designed to be run by the
instagram-autopost.yml GitHub Actions workflow, which supplies
IG_USER_ID and IG_ACCESS_TOKEN as environment variables (the token comes
from a GitHub Actions repo secret -- it is never committed to the repo).

Safe to run more than once for the same slot: it checks how close "now"
is to each slot's target time and only acts on the closest one, and it's
fine if a run finds nothing scheduled for today (calendar ended, or this
is a day outside the 30-day range) -- it just exits quietly.
"""
import json
import os
import sys
import time
import datetime
import zoneinfo
import urllib.request
import urllib.parse

GRAPH_VERSION = "v21.0"
BASE = f"https://graph.instagram.com/{GRAPH_VERSION}"

SLOT_TIMES_ET = {1: (8, 45), 2: (12, 15), 3: (18, 30)}


def now_et():
    return datetime.datetime.now(zoneinfo.ZoneInfo("America/New_York"))


def closest_slot(now):
    best_slot, best_diff = None, None
    for slot, (h, m) in SLOT_TIMES_ET.items():
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        diff = abs((now - target).total_seconds())
        if best_diff is None or diff < best_diff:
            best_slot, best_diff = slot, diff
    return best_slot


def http_post(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def http_get(url, params):
    qs = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{qs}", timeout=30) as resp:
        return json.loads(resp.read().decode())


def main():
    ig_user_id = os.environ["IG_USER_ID"]
    access_token = os.environ["IG_ACCESS_TOKEN"]

    with open("calendar.json") as f:
        calendar = json.load(f)

    now = now_et()
    today = now.strftime("%Y-%m-%d")
    slot = closest_slot(now)

    entry = next((e for e in calendar if e["date"] == today and e["slot"] == slot), None)
    if entry is None:
        print(f"No post scheduled for {today} slot {slot}. Nothing to do.")
        return

    print(f"Posting {today} slot {slot}: {entry['image_url']}")

    container = http_post(f"{BASE}/{ig_user_id}/media", {
        "image_url": entry["image_url"],
        "caption": entry["caption"],
        "access_token": access_token,
    })
    if "id" not in container:
        print(f"ERROR creating container: {container}", file=sys.stderr)
        sys.exit(1)
    container_id = container["id"]

    deadline = time.time() + 60
    while time.time() < deadline:
        status = http_get(f"{BASE}/{container_id}", {"fields": "status_code", "access_token": access_token})
        if status.get("status_code") == "FINISHED":
            break
        if status.get("status_code") == "ERROR":
            print(f"ERROR processing container: {status}", file=sys.stderr)
            sys.exit(1)
        time.sleep(2)

    publish = http_post(f"{BASE}/{ig_user_id}/media_publish", {
        "creation_id": container_id,
        "access_token": access_token,
    })
    if "id" not in publish:
        print(f"ERROR publishing: {publish}", file=sys.stderr)
        sys.exit(1)

    media_id = publish["id"]
    info = http_get(f"{BASE}/{media_id}", {"fields": "permalink", "access_token": access_token})
    print(f"Posted: {info.get('permalink', media_id)}")


if __name__ == "__main__":
    main()
