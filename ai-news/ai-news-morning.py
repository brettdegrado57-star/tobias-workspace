#!/usr/bin/env python3
"""
AI News Scraper — Fetches AI news and sends to Telegram.
- Weekdays 9am: Daily AI digest (quick summary)
- Monday 9am: Weekly AI roundup (longer)
- Weekdays 6pm: Breaking AI news only (urgent, major stories only)
"""
import feedparser
import requests
from datetime import datetime, timedelta
import time
import json
import re
import os

BOT_TOKEN = "8676105321:AAGMEz3Z1T2frfeHCDmAfSypcQJU7ABH-rc"
CHAT_ID = "8664133183"

FEEDS = [
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("AI News", "https://www.artificialintelligence-news.com/rss/"),
]

AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "openai", "anthropic",
    "claude", "gpt", "chatgpt", "gemini", "llm", "language model",
    "deep learning", "generative ai", "anthropic", "google deepmind",
    "meta ai", "microsoft ai", "nvidia", "ai model", "ai agent", "ai startup",
]

BREAKING_KEYWORDS = [
    "launch", "release", "announce", "acquisition", "merger", "funding round",
    "ipo", "breakthrough", "record", "billion", "unveil", "ceo says",
    "lawsuit", "ban", "regulation", " senate", "congress",
]

CUTOFF_HOURS_DAILY = 18
CUTOFF_HOURS_WEEKLY = 72

def is_ai_related(text):
    t = text.lower()
    return any(kw in t for kw in AI_KEYWORDS)

def is_breaking(text):
    t = text.lower()
    has_breaking = any(kw in t for kw in BREAKING_KEYWORDS)
    has_ai = any(kw in t for kw in AI_KEYWORDS)
    return has_breaking and has_ai

def clean_html(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&hellip;', '...')
    text = text.replace('&mdash;', '—').replace('&ndash;', '–')
    return text.strip()

def fetch_feed(name, url, timeout=10):
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return feedparser.parse(resp.content)
    except Exception as e:
        return None

def summarize(text, max_len=150):
    """Create a quick summary from article text."""
    # Clean and truncate
    text = clean_html(text)
    if len(text) <= max_len:
        return text
    # Try to cut at a sentence or clause
    for sep in ['. ', '—', '–', ': ', ' - ']:
        idx = text.rfind(sep, max_len, len(text))
        if idx > max_len:
            return text[:idx+1].strip()
    return text[:max_len].strip() + "..."

def fetch_articles():
    """Fetch all AI articles from feeds."""
    now = datetime.utcnow()
    articles = []
    
    for name, url in FEEDS:
        feed = fetch_feed(name, url)
        if not feed:
            continue
        
        for entry in feed.entries[:20]:
            try:
                published = entry.get('published_parsed') or entry.get('updated_parsed')
                if published:
                    pub_dt = datetime(*published[:6])
                else:
                    pub_dt = now
                
                title = clean_html(entry.get('title', ''))
                summary = clean_html(entry.get('summary', ''))[:500]
                link = entry.get('link', '')
                
                if not is_ai_related(title + " " + summary):
                    continue
                
                articles.append({
                    'title': title,
                    'summary': summary,
                    'link': link,
                    'source': name,
                    'pub_dt': pub_dt,
                    'age_hours': (now - pub_dt).total_seconds() / 3600,
                })
            except:
                continue
        
        time.sleep(0.3)
    
    # Remove duplicates by title
    seen = set()
    unique = []
    for a in articles:
        t = a['title'].lower()[:80]
        if t not in seen:
            seen.add(t)
            unique.append(a)
    
    return unique

def send_to_telegram(text):
    payload = json.dumps({"chat_id": CHAT_ID, "text": text}).encode()
    req = requests.Request("POST",
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with requests.Session() as s:
        resp = s.send(req.prepare(), timeout=15)
    return json.loads(resp.text).get('ok')

def format_daily(articles):
    """Daily digest — top stories with quick summaries."""
    now = datetime.now()
    cutoff = now - timedelta(hours=CUTOFF_HOURS_DAILY)
    recent = [a for a in articles if a['pub_dt'] > cutoff]
    
    header = f"🤖 AI DIGEST — {now.strftime('%B %d')}\nDaily briefing · {len(recent)} stories\n{'='*28}\n"
    
    if not recent:
        return None
    
    lines = []
    for i, a in enumerate(recent[:8], 1):
        summary = summarize(a['summary'], 140)
        age = f"{int(a['age_hours'])}h ago" if a['age_hours'] < 24 else "yesterday"
        lines.append(f"{i}. 📰 {a['title']}\n   💬 {summary}\n   Source: {a['source']} · {age}")
    
    footer = f"\n_Generated {now.strftime('%I:%M %p')}_"
    return header + "\n\n".join(lines) + footer

def format_weekly(articles):
    """Weekly roundup — more stories, longer summaries."""
    now = datetime.now()
    cutoff = now - timedelta(hours=CUTOFF_HOURS_WEEKLY)
    recent = [a for a in articles if a['pub_dt'] > cutoff]
    
    header = f"📅 AI WEEKLY — {now.strftime('%B %d')}\nWeek in review · {len(recent)} stories\n{'='*28}\n"
    
    if not recent:
        return None
    
    lines = []
    for i, a in enumerate(recent[:12], 1):
        summary = summarize(a['summary'], 180)
        days = "Mon" if a['pub_dt'].weekday() == 0 else ""
        lines.append(f"{i}. 📰 {a['title']}\n   💬 {summary}\n   Source: {a['source']} · {a['pub_dt'].strftime('%a %b %d')}")
    
    footer = f"\n_Generated {now.strftime('%I:%M %p')} · Full digest_"
    return header + "\n\n".join(lines) + footer

def format_breaking(articles):
    """Breaking news — only major urgent stories."""
    now = datetime.now()
    cutoff = now - timedelta(hours=CUTOFF_HOURS_DAILY)
    recent = [a for a in articles if a['pub_dt'] > cutoff]
    
    breaking = [a for a in recent if is_breaking(a['title'] + " " + a['summary'])]
    
    header = f"🚨 AI BREAKING — {now.strftime('%B %d, %I:%M %p')}\n"
    
    if not breaking:
        header += "No major breaking AI news right now.\n"
        header += "_Check back later or see daily digest at 9am_"
        return header
    
    lines = []
    for i, a in enumerate(breaking[:5], 1):
        summary = summarize(a['summary'], 160)
        lines.append(f"⚡ {a['title']}\n   💬 {summary}\n   🔗 {a['link']}")
    
    footer = f"\n_Generated {now.strftime('%I:%M %p')} · {len(breaking)} breaking stories_"
    return header + "\n\n".join(lines) + footer

def main():
    now = datetime.now()
    is_monday = now.weekday() == 0
    is_morning = now.hour < 12
    is_evening = now.hour >= 17
    
    # Determine mode
    if is_evening:
        mode = "breaking"
    elif is_morning and is_monday:
        mode = "weekly"
    else:
        mode = "daily"
    
    print(f"[{now.strftime('%H:%M')}] Mode: {mode}")
    
    articles = fetch_articles()
    print(f"Fetched {len(articles)} articles")
    
    if mode == "breaking":
        text = format_breaking(articles)
    elif mode == "weekly":
        text = format_weekly(articles)
    else:
        text = format_daily(articles)
    
    if not text:
        text = f"🤖 AI NEWS — {now.strftime('%B %d')}\n\nNo AI news in the last 18 hours. Check back this evening!"
    
    ok = send_to_telegram(text)
    print(f"Sent: {ok}")
    return ok

if __name__ == "__main__":
    main()
