#!/usr/bin/env python3
"""
Writes the next batch of formerlyknownwrites posts with the Claude API and
hands them to add_posts.py (which dedupes, renders, and schedules them).

Needs the ANTHROPIC_API_KEY environment variable (a GitHub Actions secret).
Cost is a fraction of a cent per batch.

    python3 tools/refill.py                # live: call the API
    python3 tools/refill.py --stub f.json  # offline test: use a saved response

Topic mix per batch of 30 requested (trimmed to whole days after dedupe),
updated Nov 2026 to go deeper and stop repeating itself: four each across the
six core lanes (who was there when I had nothing, a father's love, healing
from a narcissist, chasing greatness alone, the loneliness of the road, the
hardships of the come up), plus six "classic" posts drawn at random each week
from the older themes so the page keeps its range without looping.
"""
import argparse
import json
import os
import random
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

CORE = {
    "small_circle": 4, "fatherhood": 4, "narcissist_healing": 4,
    "greatness": 4, "loneliness": 4, "come_up": 4,
}
CLASSIC = [
    "betrayal", "hardship", "life", "life_lessons", "growth", "absence", "audacity",
    "timing", "redirection", "healing", "boundaries", "self_worth", "purpose",
]
CLASSIC_PER_BATCH = COUNT - sum(CORE.values())  # 6


def build_mix():
    mix = dict(CORE)
    for t in random.sample(CLASSIC, CLASSIC_PER_BATCH):
        mix[t] = mix.get(t, 0) + 1
    assert sum(mix.values()) == COUNT
    return mix

SYSTEM = """You write posts for the Instagram quote page formerlyknownwrites, in the voice of a Dominican-born, Bronx-raised founder and father who came up from nothing, built something real, leans on faith and family, and is raising his children to be adults with values. The page goes deep: the stuff people feel but rarely say out loud. Most posts are NOT about parenting.

Voice: rap-style bars. Wordplay is the signature: lines that carry two or three meanings at once ("finish line / hard lines / read between them", "paid attention when I couldn't pay anything", "a dream I never let anybody repo"), triads ("the odds, the oddsmakers, and the odd ones out"), and flips that land on the last word. Concrete, lived-in details over abstractions (overdraft fees, ramen nights, borrowed rides, 3am, bills, receipts, the back seat on the long way home). Short: one to three short sentences, usually with a line break between thoughts, built to be screenshotted and sent to someone. No clichés ("hustle", "grind", "good vibes only", "everything happens for a reason", "trust the process"), no advice-column tone, no hashtags, no emojis.

THE SIX CORE LANES (the heart of the page):
- small_circle: everybody loves the end product, but who was there when I had nothing. The latecomers who show up for the finish line, the view, the celebration. Gratitude for the few who were there early. IMPORTANT: this man DID have people. His mother, his brother, a few cousins and a handful of real friends had his back. Never write that nobody was there or that he did it with no one. The point is a small, real circle versus a big late crowd. Honor the early ones as often as you call out the late ones. Never name or describe a specific person.
- fatherhood: the love of a father. Tender and affirming, often spoken straight to the child ("you"): love that never has to be earned, "you are enough", a steady presence through storms rather than a promise there will be none, faith and family holding him up, wanting his kids curious, kind, free and true to themselves, gratitude for what they teach him, humble about his own imperfection. Images: a rock, a garden, a lighthouse, a compass, roots and wings, the table, the long way home. Fatherhood as something he builds and tends, not a title.
- narcissist_healing: the struggle of dealing with a narcissist, written from the healing side. Patterns, not a person: rewriting history, moving the goalposts, love with terms and conditions, apologies with fine print, walking on eggshells, confusion where closure should be, peace feeling strange after chaos. The power stays with the reader: seeing clearly, no longer explaining or auditioning, choosing peace. Prefer "some people" or "someone" over "they". Never diagnose a named or describable person.
- greatness: the struggle of someone trying to achieve greatness. The weight of a vision others can't see yet, betting on yourself, being your own blueprint, consistency nobody claps for, building without a map. It can be lonely without being friendless: he had a small corner in his fight.
- loneliness: the loneliness of that road. Quiet seasons, 3am, losing signal with people as you change frequency, being misunderstood for seeing early, growth thinning the guest list. Loneliness here is about carrying the vision, not about being abandoned. No self-pity; there is always a little light in the line.
- come_up: the hardships of the come up. Being broke in pocket and rich in plans, counting every dollar twice, overdrafts, no safety net, ideas written on unpaid bills, the thousand quiet reps nobody posted. Pride without bragging.

CLASSIC topics (a few each week, same voice): betrayal, hardship, life, life_lessons, growth, absence, audacity, timing, redirection, healing, boundaries, self_worth, purpose.

Hard rules:
- Never use em dashes or en dashes. Use commas, periods, or parentheses.
- Universal wording. Never point at a specific, identifiable person or relationship. Every post must read as safe if screenshotted and shown to anyone, including in a courtroom.
- Only fatherhood posts mention children, kids, or being a dad. No other post mentions parenting, co-parenting, custody, an ex, a child's other parent, family court, or "home" in a way that could read as being about a family situation. narcissist_healing posts in particular never touch family, kids, partners, exes or co-parenting.
- Parenting tone is warm, patient, steady and child-centered. Never harsh, rigid, cold or controlling, never a list of rules, no lines about a cruel world, and no scorekeeping about who shows up or when for the kids.
- Never mention schedules, days of the week, or being absent or away from the children.
- Betrayal posts are about the reader's own trust, lessons, boundaries and healing; never describe what someone did or intended.
- Growth and outgrowing posts have no villain and leave no one behind in blame.
- No threats, no revenge, no mocking anyone's character, appearance or mental health. Call out patterns with wit, not cruelty.
- Do not repeat or closely paraphrase any quote in the AVOID list, and do not recycle the same image twice in one batch (one "table", one "map", one "crown" at most).
- Under 200 characters each. Use \\n inside the string for a deliberate line break.
- Vary sentence shape. Not every post should be "X isn't Y, it's Z" or a three-item list.

EXAMPLES of the bar to hit (do not reuse these):
- "You showed up for the finish line.\\nNever once called during the hard lines.\\nRead between them."
- "I keep receipts for gratitude, not revenge.\\nI know exactly who paid attention when I couldn't pay anything."
- "You'll outgrow my arms.\\nNever my reach."
- "Their apologies came with fine print.\\nTheir love came with terms and conditions.\\nI finally read the contract."
- "Ramen nights, borrowed rides, and a dream I never let anybody repo."
- "I didn't lose friends.\\nI lost signal.\\nDifferent frequency, same love."

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
        mix_lines = "\n".join(f"- {k}: {v}" for k, v in build_mix().items())
        avoid = "\n".join(f"- {t}" for t in recent_texts())
        prompt = (
            f"Write {COUNT} new posts with this topic mix:\n{mix_lines}\n\n"
            "Topic meanings: small_circle (who was there when I had nothing; gratitude for the early few, the late crowd at the finish line), "
            "fatherhood (the love of a father, tender and affirming), narcissist_healing (seeing the patterns clearly and choosing peace), "
            "greatness (chasing a vision others can't see yet), loneliness (the quiet of that road), come_up (the hardships of starting from nothing), "
            "betrayal (trust, lessons, protecting your peace), hardship (overcoming), life (perspective, gratitude, what matters), "
            "life_lessons (wisdom learned the hard way), absence (missing someone, grief), audacity (courage to start), timing (patience), "
            "growth (outgrowing situations and seasons), redirection (closed doors), healing, boundaries, self_worth, purpose.\n\n"
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
