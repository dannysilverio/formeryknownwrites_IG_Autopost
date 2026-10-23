#!/usr/bin/env python3
"""
Adds new posts to the calendar.

Input: a JSON file containing a list of posts:
    [{"topic": "fatherhood", "text": "The quote.\nOptional second line.",
      "style": "note" | "black"   (optional; default: slot 1 = note, slots 2-3 = black)
      "hashtags": ["#one", ...]   (optional; default comes from the topic)
      "cta": "Tag a dad..."       (optional; default rotates)
     }, ...]

For each post this script:
  1. rejects duplicates and near-duplicates of anything already in the
     calendar or bank/texts.json
  2. rejects em dashes (house rule: commas, periods, or parentheses instead)
  3. renders a 1080x1350 PNG into bank/
  4. appends calendar.json entries, 3 per day (slots 1, 2, 3), starting the
     day after the last scheduled date (or tomorrow, whichever is later)
  5. logs the full text in bank/texts.json (used for dedupe and future prompts)

It never touches posted.json, so it cannot cause a double post.

Usage:
    python3 tools/add_posts.py new_posts.json [--dry-run] [--start-date YYYY-MM-DD]
"""
import argparse
import datetime
import difflib
import json
import os
import re
import sys
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from render_post import render  # noqa: E402

RAW_BASE = "https://raw.githubusercontent.com/dannysilverio/formeryknownwrites_IG_Autopost/main/"
CALENDAR = os.path.join(ROOT, "calendar.json")
TEXTS = os.path.join(ROOT, "bank", "texts.json")
SLOTS = (1, 2, 3)

DEFAULT_CTAS = [
    "Save this for the day you need to reread it.",
    "Tag someone who needs to see this today.",
    "Share this to your story if you felt this one.",
    "Which line are you sitting with? Tell me below.",
    "Send this to the friend who's going through it right now.",
]
TOPIC_CTAS = {
    "fatherhood": [
        "Tag a father who leads by example.",
        "Send this to a dad who needs to hear it today.",
        "Save this for the next hard parenting day.",
    ],
}

TOPIC_TAGS = {
    "fatherhood": ["#fatherhood", "#dadlife", "#raisingkids", "#parentingquotes", "#leadbyexample"],
    "betrayal": ["#betrayalquotes", "#trustissues", "#lessonslearned", "#loyaltyquotes", "#protectyourpeace"],
    "hardship": ["#overcomingadversity", "#resilience", "#comebackstory", "#strongermindset", "#keepgoing"],
    "life": ["#lifelessons", "#lifequotes", "#perspective", "#realtalk", "#livewithintention"],
    "life_lessons": ["#wisdomquotes", "#lessonslearned", "#dailywisdom", "#lifelessonslearned", "#growthmindset"],
    "absence": ["#missingsomeone", "#griefquotes", "#presenceovergifts", "#cherishthemnow", "#quietstrength"],
    "audacity": ["#confidencequotes", "#mindsetshift", "#dothescarything", "#selfbelief", "#growthmindset"],
    "timing": ["#divinetiming", "#patiencequotes", "#trusttheprocess", "#thingswilllineup", "#slowgrowth"],
    "growth": ["#growthquotes", "#outgrowingpeople", "#innergrowth", "#newseason", "#glowupjourney"],
    "redirection": ["#redirectionnotrejection", "#healingjourney", "#letgoandgrow", "#newchapter", "#protectedbynos"],
    "healing": ["#healingquotes", "#innerpeace", "#lettinggoquotes", "#selfhealers", "#emotionalhealing"],
    "boundaries": ["#boundariesquotes", "#protectyourpeace", "#noexplanationneeded", "#selfrespect", "#peaceoverpleasing"],
    "self_worth": ["#selfworthquotes", "#knowyourworth", "#chooseyourself", "#boundariesarehealthy", "#selflove"],
    "purpose": ["#findyourpurpose", "#becomingher", "#becominghim", "#nextchapter", "#purposedriven"],
}


def norm(s):
    return re.sub(r"[^a-z0-9 ]+", "", s.lower().replace("\n", " ")).strip()


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def existing_texts(calendar, texts_log):
    """Normalized text of everything already scheduled or banked."""
    out = [norm(e["caption"].split("\n\n")[0]) for e in calendar]
    out += [norm(t["text"]) for t in texts_log]
    return out


def next_start(calendar, override):
    if override:
        return datetime.date.fromisoformat(override)
    today = datetime.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date()
    last = max(datetime.date.fromisoformat(e["date"]) for e in calendar) if calendar else today
    return max(last + datetime.timedelta(days=1), today + datetime.timedelta(days=1))


def max_seq(bank_dir, calendar, texts_log):
    """Highest p#### number ever used (files on disk, calendar URLs, logged files),
    so a new image can never overwrite an existing one even after cleanup."""
    names = []
    if os.path.isdir(bank_dir):
        names += os.listdir(bank_dir)
    names += [e["image_url"].rsplit("/", 1)[-1] for e in calendar]
    names += [t.get("file", "").rsplit("/", 1)[-1] for t in texts_log]
    nums = [int(m.group(1)) for n in names for m in [re.match(r"p(\d{4})_", n)] if m]
    return max(nums) if nums else 0


def build_caption(post, idx):
    topic = post["topic"]
    ctas = TOPIC_CTAS.get(topic, []) + DEFAULT_CTAS
    cta = post.get("cta") or ctas[idx % len(ctas)]
    tags = post.get("hashtags") or TOPIC_TAGS.get(topic, [])
    return post["text"].strip() + "\n\n" + cta + "\n\n" + " ".join(tags[:5])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("posts_json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--start-date")
    args = ap.parse_args()

    posts = load_json(args.posts_json, None)
    if not isinstance(posts, list) or not posts:
        sys.exit("input must be a non-empty JSON list")

    calendar = load_json(CALENDAR, [])
    texts_log = load_json(TEXTS, [])
    seen = existing_texts(calendar, texts_log)

    accepted, rejected = [], []
    for p in posts:
        text = p.get("text", "").strip()
        topic = p.get("topic", "")
        if topic not in TOPIC_TAGS and not p.get("hashtags"):
            rejected.append((text[:50], f"unknown topic {topic!r} and no hashtags"))
            continue
        if "—" in text or "–" in text or "--" in text:
            rejected.append((text[:50], "contains a dash that reads as an em dash"))
            continue
        if len(text) < 15:
            rejected.append((text[:50], "too short"))
            continue
        n = norm(text)
        clash = next((s for s in seen if n == s or difflib.SequenceMatcher(None, n, s).ratio() > 0.82), None)
        if clash:
            rejected.append((text[:50], "duplicate or near-duplicate of an existing post"))
            continue
        seen.append(n)
        accepted.append(p)

    # Only whole days (multiples of 3) so no day is left with an empty slot.
    keep = len(accepted) // len(SLOTS) * len(SLOTS)
    if keep != len(accepted):
        print(f"  trimming {len(accepted) - keep} post(s) so the batch fills whole days")
        accepted = accepted[:keep]

    start = next_start(calendar, args.start_date)
    seq = max_seq(os.path.join(ROOT, "bank"), calendar, texts_log)

    new_entries, new_texts = [], []
    for i, p in enumerate(accepted):
        day_offset, slot = divmod(i, len(SLOTS))
        slot += 1
        date = (start + datetime.timedelta(days=day_offset)).isoformat()
        style = p.get("style") or ("note" if slot == 1 else "black")
        seq += 1
        fname = f"p{seq:04d}_{style}_{p['topic']}.png"
        out_path = os.path.join(ROOT, "bank", fname)
        try:
            if not args.dry_run:
                render(p["text"], style, out_path)
        except ValueError as e:
            rejected.append((p["text"][:50], f"render failed: {e}"))
            seq -= 1
            continue
        new_entries.append({
            "date": date,
            "slot": slot,
            "image_url": RAW_BASE + "bank/" + fname,
            "caption": build_caption(p, len(calendar) + i),
        })
        new_texts.append({"text": p["text"].strip(), "topic": p["topic"], "style": style,
                          "file": "bank/" + fname, "date": date, "slot": slot})

    # Dates must be gapless: if a render failed mid-batch, re-pack the schedule.
    for i, (e, t) in enumerate(zip(new_entries, new_texts)):
        day_offset, slot = divmod(i, len(SLOTS))
        e["date"] = t["date"] = (start + datetime.timedelta(days=day_offset)).isoformat()
        e["slot"] = t["slot"] = slot + 1

    print(f"accepted {len(new_entries)}, rejected {len(rejected)}")
    for snippet, why in rejected:
        print(f"  REJECTED {snippet!r}: {why}")
    if new_entries:
        print(f"  schedule: {new_entries[0]['date']} slot {new_entries[0]['slot']} -> {new_entries[-1]['date']} slot {new_entries[-1]['slot']}")

    if args.dry_run or not new_entries:
        return
    save_json(CALENDAR, calendar + new_entries)
    save_json(TEXTS, texts_log + new_texts)


if __name__ == "__main__":
    main()
