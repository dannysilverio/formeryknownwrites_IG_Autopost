#!/usr/bin/env python3
"""
Reads calendar.json (checked into this repo), finds the entry matching
today's date (America/New_York) and the current time slot, and publishes
it to Instagram via the Graph API. Designed to be run by the
instagram-autopost.yml GitHub Actions workflow, which supplies
IG_USER_ID and IG_ACCESS_TOKEN as environment variables (the token comes
from a GitHub Actions repo secret -- it is never committed to the repo).

Reliability: GitHub's exact-minute schedule trigger is not reliable
enough on its own -- runs can fire minutes to hours late, or not fire
at all. So the workflow runs this script every 15 minutes around the
clock instead of at 3 exact minutes, and this script only acts when
"now" falls within WINDOW_MINUTES of one of the 3 target times --
otherwise it's a no-op. That turns "one exact-minute shot per slot"
into "several chances across a window," so a missed or late firing
gets caught by the next check.

Double-post guard: before posting, checks posted.json (also checked into
this repo) for a matching {date, slot} entry. If found, it skips --
this makes it safe for multiple checks within the same window to all
land on the same slot, safe to manually re-run the workflow, and safe
against a delayed/duplicated cron firing. After a successful publish,
it records the {date, slot, permalink} in posted.json. The workflow
then commits that updated file back to the repo so the guard persists
across runs (each run starts from a fresh checkout, so without
committing the log, the guard would reset every time and offer no
protection).
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
WINDOW_MINUTES = 30  # act on a slot if "now" is within this many minutes of its target time
POSTED_LOG = "posted.json"


def now_et():
    return datetime.datetime.now(zoneinfo.ZoneInfo("America/New_York"))


def slot_due_now(now):
    """Return the slot number if now falls within WINDOW_MINUTES of that
    slot's target time, else None (meaning: not time for any slot yet)."""
    best_slot, best_diff = None, None
    for slot, (h, m) in SLOT_TIMES_ET.items():
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        diff = abs((now - target).total_seconds())
        if best_diff is None or diff < best_diff:
            best_slot, best_diff = slot, diff
    if best_diff is not None and best_diff <= WINDOW_MINUTES * 60:
        return best_slot
    return None


def load_posted():
    if os.path.exists(POSTED_LOG):
        with open(POSTED_LOG) as f:
            return json.load(f)
    return []


def save_posted(posted):
    with open(POSTED_LOG, "w") as f:
        json.dump(posted, f, indent=2)
        f.write("\n")


def already_posted(posted, date, slot):
    return any(p["date"] == date and p["slot"] == slot for p in posted)


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
    slot = slot_due_now(now)

    if slot is None:
        print(f"Not within a posting window right now ({now.strftime('%H:%M %Z')}). Nothing to do.")
        return

    posted = load_posted()
    if already_posted(posted, today, slot):
        print(f"Already posted for {today} slot {slot} -- skipping (double-post guard).")
        return

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
    permalink = info.get("permalink", media_id)
    print(f"Posted: {permalink}")

    posted.append({"date": today, "slot": slot, "media_id": media_id, "permalink": permalink})
    save_posted(posted)


if __name__ == "__main__":
    main()
