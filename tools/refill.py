#!/usr/bin/env python3
"""
Writes the next batch of formerlyknownwrites posts with the Claude API and
hands them to add_posts.py (which dedupes, renders, and schedules them).

Needs the ANTHROPIC_API_KEY environment variable (a GitHub Actions secret).
Cost is a fraction of a cent per batch.

    python3 tools/refill.py                # live: call the API
    python3 tools/refill.py --stub f.json  # offline test: use a saved response

Topic mix per batch of 30 requested (trimmed to whole days after dedupe):
fatherhood weighted heaviest, then betrayal, hardship, life, and one or two
of each earlier theme.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from add_posts import TOPIC_TAGS, norm  # noqa: E402

MODEL = os.environ.get("REFILL_MODEL", "claude-haiku-5-5")
COUNT = 30

MIX = {
    "fatherhood": 8, "betrayal": 3, "hardship": 3, "life": 3,
    "absence": 1, "audacity": 2, "timing": 2, "growth": 2, "redirection": 2,
    "healing": 1, "boundaries": 1, "self_worth": 1, "purpose": 1,
}

SYSTEM = """You write posts for the Instagram quote page formerlyknownwrites, in the voice of a father who has been through real hardship and is raising his children to be adults with values.

Voice: plain, direct, aphoristic. Short. Each post is one to three short sentences, usually with a line break between thoughts. It should read like something a person would screenshot and send to someone. Concrete over abstract. No clichés ("hustle", "grind", "good vibes only", "everything happens for a reason"), no advice-column tone, no hashtags, no emojis.

Hard rules:
- Never use em dashes or en dashes. Use commas, periods, or parentheses.
- Universal wording only. Never point at a specific person or relationship. Every post must be about an experience in general and read as safe if screenshotted and shown to anyone.
- Tone for any post about parenting: warm, patient, steady, and child-centered. Never harsh, rigid, cold, or controlling. No lines about a cruel or ungentle world, and no scorekeeping about who shows up or when.
- Parenting voice, how this father actually talks about his kids: tender and affirming, often speaking straight to the child ("you"). Love that does not have to be earned. "You are enough." Being a steady presence through life's storms rather than promising to prevent them. Faith and family as what holds him up. Encouraging kids to stay curious, kind, imaginative, and true to themselves, to follow the dreams in their own heart, to balance passion with gentleness, and to get back up when they stumble. Gratitude for what his children teach him. Humble about his own imperfection ("some days I wish for a do-over"). Never stern, never lecturing, never a list of rules.
- Never imply anyone else fails at what a post describes, never attribute motives to other people, and never mention schedules, days of the week, or being absent or away.
- Betrayal posts stay general. Nothing about people close to you using or targeting you.
- Do not repeat or closely paraphrase any quote in the AVOID list.
- Under 200 characters each. Use \\n inside the string for a deliberate line break.
- Vary sentence shape. Not every post should be "X isn't Y, it's Z".

Return ONLY a JSON array, no prose. Each element: {"topic": "<one of the allowed topics>", "text": "<the quote>"}."""


def recent_texts(limit=150):
    cal = json.load(open(os.path.join(ROOT, "calendar.json")))
    texts_path = os.path.join(ROOT, "bank", "texts.json")
    banked = json.load(open(texts_path)) if os.path.exists(texts_path) else []
    seen = [t["text"] for t in banked] + [e["caption"].split("\n\n")[0] for e in cal]
    out, keys = [], set()
    for t in reversed(seen):
        k = norm(t)
        if k not in keys:
            keys.add(k)
            out.append(t.replace("\n", " "))
    return out[:limit]


def call_api(prompt):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("::warning::ANTHROPIC_API_KEY is not set, so the weekly refill was skipped. "
              "Add it under Settings > Secrets and variables > Actions.")
        sys.exit(0)
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 6000,
        "system": SYSTEM + (
            "\n\nAdditional rules from the page owner (follow strictly):\n" + os.environ["REFILL_EXTRA_RULES"]
            if os.environ.get("REFILL_EXTRA_RULES") else ""
        ),
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode())
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def parse_posts(raw):
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        raise ValueError("no JSON array in model response")
    posts = json.loads(m.group(0))
    clean = []
    for p in posts:
        if isinstance(p, dict) and p.get("topic") in TOPIC_TAGS and isinstance(p.get("text"), str):
            clean.append({"topic": p["topic"], "text": p["text"].strip()})
    return clean


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stub")
    args = ap.parse_args()

    if args.stub:
        raw = open(args.stub).read()
    else:
        mix_lines = "\n".join(f"- {k}: {v}" for k, v in MIX.items())
        avoid = "\n".join(f"- {t}" for t in recent_texts())
        prompt = (
            f"Write {COUNT} new posts with this topic mix:\n{mix_lines}\n\n"
            "Topic meanings: fatherhood (raising kids with values, protecting them, steadiness), "
            "betrayal, hardship (overcoming), life (perspective), absence (missing someone, grief), "
            "audacity (courage to start), timing (patience), growth (outgrowing, changing), "
            "redirection (closed doors), healing, boundaries, self_worth, purpose.\n\n"
            f"AVOID (already posted, do not repeat or paraphrase):\n{avoid}\n\n"
            "Return the JSON array now."
        )
        raw = call_api(prompt)

    posts = parse_posts(raw)
    print(f"model returned {len(posts)} usable posts")
    if len(posts) < 9:
        sys.exit("too few usable posts, not adding anything")

    tmp = os.path.join(ROOT, "bank", "_incoming.json")
    json.dump(posts, open(tmp, "w"), indent=2, ensure_ascii=False)
    try:
        subprocess.run([sys.executable, os.path.join(HERE, "add_posts.py"), tmp], check=True, cwd=ROOT)
    finally:
        os.remove(tmp)


if __name__ == "__main__":
    main()
