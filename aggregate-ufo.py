#!/usr/bin/env python3
"""
UFO / UAP feed aggregator for CTPIDM and CTP Space Systems.

Fetches the UFO/UAP RSS feeds listed in ufo-feeds.json (the same UFO/UAP
sources the CTP Magazine draws from — see ctp-magazine-hugo/rss-feeds.md,
topic "UFOs & UAPs", feeds #18-22, #59-61, #79, #80, #84, #85, #92, #93),
extracts title / link / excerpt / date per item, dedupes by link AND by
near-duplicate title, and writes data/ufo-feed.json for Hugo to render
into the "UFO & UAP — from the wider web" section under Our Articles.

Republication rule: every feed here is EXCERPT + LINK (per the Magazine's
clearance list, 2026-11-19) — title + the short excerpt the RSS feed
supplies, HARD ceiling 200 words, + prominent link back to the original
article. Never more. Aggregator links (Google News / Bing News) go through
the aggregator and redirect to the original article, as in the Magazine.

Stdlib only (urllib + xml.etree). No feedparser dependency, so the same
script runs unchanged in GitHub Actions with setup-python.

Usage:  python3 aggregate-ufo.py [--feeds ufo-feeds.json] [--out data/ufo-feed.json]
Exit code 0 even if individual feeds fail (failures are logged, the rest
of the run continues). Exit code 1 only if the feed list cannot be read
or no feed at all succeeded.
"""

import argparse
import concurrent.futures
import gzip
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

BASE = Path(__file__).resolve().parent
FEEDS_JSON = BASE / "ufo-feeds.json"
OUT_JSON = BASE / "data" / "ufo_feed.json"

MAX_WORDS_EXCERPT = 200          # hard ceiling, Phys.org's own stated limit
MAX_PARAS_DISPLAY = 3            # card shows at most 3 paragraphs
MAX_WORDS_DISPLAY = 300          # card shows at most ~300 words
MAX_CHARS_DISPLAY = 1500         # card shows at most ~1500 characters
MAX_PARA_CHARS = 600             # no single paragraph over ~600 chars
MAX_ITEMS_PER_FEED = 25          # Google News returns ~100; take newest 25
MAX_ITEMS_TOTAL = 40             # feed section shows the newest 40
FETCH_TIMEOUT = 25
WORKERS = 8
USER_AGENT = "CTPUFOFeedAggregator/1.0 (+https://ctpidm.github.io/)"


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_url(url: str) -> bytes:
    """Fetch with retries. Some servers drop the first connection
    (RemoteDisconnected) or reject the feed Accept header (415);
    retry with backoff, then with browser-like headers, and for
    http:// URLs also try the https:// variant as a last resort."""
    last_exc = None
    candidates = [url]
    if url.startswith("http://"):
        candidates.append("https://" + url[len("http://"):])
    for candidate in candidates:
        for attempt, headers in enumerate((
            _FEED_HEADERS,
            _BROWSER_HEADERS,
            _BROWSER_HEADERS,
        )):
            try:
                req = urllib.request.Request(candidate, headers=headers)
                with urllib.request.urlopen(req,
                                            timeout=FETCH_TIMEOUT) as resp:
                    raw = resp.read()
                if raw[:2] == b"\x1f\x8b":         # gzip magic bytes
                    raw = gzip.decompress(raw)
                return raw
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code not in (403, 406, 415) or attempt == 2:
                    break
            except Exception as exc:              # timeouts, disconnects
                last_exc = exc
                if attempt == 2:
                    break
            time.sleep(2 * (attempt + 1))
    raise last_exc


_FEED_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/rss+xml, application/atom+xml, "
              "application/xml, text/xml, */*;q=0.8",
    "Accept-Encoding": "gzip",
}
_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip",
}


# ---------------------------------------------------------------------------
# XML parsing (namespace-agnostic: RSS 2.0, Atom, RDF/RSS 1.0)
# ---------------------------------------------------------------------------

def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(elem, names) -> str:
    """First matching direct child's text (names = set of local names)."""
    for child in elem:
        if local(child.tag) in names and child.text:
            return child.text.strip()
    return ""


def child_attr(elem, names, attr) -> str:
    for child in elem:
        if local(child.tag) in names and child.get(attr):
            return child.get(attr).strip()
    return ""


def find_descendants(elem, name: str):
    return [e for e in elem.iter() if local(e.tag) == name]


def strip_html(text: str) -> str:
    """Strip HTML but PRESERVE paragraph breaks: block closers (</p>,
    </div>, </li>, headings, blockquote) and <br> become paragraph
    separators ("\\n\\n") before the tags are removed, and whitespace is
    collapsed only WITHIN a paragraph."""
    if not text:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text,
                  flags=re.S | re.I)
    text = re.sub(r"</(p|div|li|h[1-6]|blockquote|tr|section|article)>",
                  "\n\n", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    paras = [re.sub(r"\s+", " ", p).strip()
             for p in text.split("\n\n")]
    paras = [p for p in paras if p]
    return "\n\n".join(paras)


def parse_date(raw: str):
    """Return an aware datetime, or None if unparseable/missing."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)       # RFC 2822 (RSS pubDate)
        if dt is not None:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    try:                                      # ISO 8601 (Atom)
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


_HTML_ENTITIES = {
    "nbsp": "&#160;", "rsquo": "&#8217;", "lsquo": "&#8216;",
    "rdquo": "&#8221;", "ldquo": "&#8220;", "mdash": "&#8212;",
    "ndash": "&#8211;", "hellip": "&#8230;", "copy": "&#169;",
    "reg": "&#174;", "trade": "&#8482;", "laquo": "&#171;",
    "raquo": "&#187;", "middot": "&#183;", "bull": "&#8226;",
    "deg": "&#176;", "plusmn": "&#177;", "times": "&#215;",
    "divide": "&#247;", "frac12": "&#189;", "frac14": "&#188;",
    "frac34": "&#190;", "eacute": "&#233;", "egrave": "&#232;",
    "agrave": "&#224;", "aacute": "&#225;", "ouml": "&#246;",
    "uuml": "&#252;", "auml": "&#228;", "szlig": "&#223;",
    "ccedil": "&#231;", "ntilde": "&#241;", "iexcl": "&#161;",
    "iquest": "&#191;", "sect": "&#167;", "para": "&#182;",
    "sup2": "&#178;", "sup3": "&#179;", "micro": "&#181;",
    "alpha": "&#945;", "beta": "&#946;", "gamma": "&#947;",
    "delta": "&#948;", "pi": "&#960;", "omega": "&#969;",
    "prime": "&#8242;", "Prime": "&#8243;", "larr": "&#8592;",
    "rarr": "&#8594;", "harr": "&#8596;", "darr": "&#8595;",
    "uarr": "&#8593;", "ne": "&#8800;", "le": "&#8804;",
    "ge": "&#8805;", "infin": "&#8734;", "asymp": "&#8776;",
    "sum": "&#8721;",
}
_BARE_AMP = re.compile(
    r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")
_INVALID_XML_CHARS = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitise_xml(text: str) -> bytes:
    """Second-chance parse for sloppy feeds: strip leading junk, fix
    bare & and HTML-only entities OUTSIDE CDATA sections, drop
    control characters that XML forbids. CDATA content is untouched."""
    parts = re.split(r"(<!\[CDATA\[.*?\]\]>)", text, flags=re.S)
    out = []
    for part in parts:
        if part.startswith("<![CDATA["):
            out.append(part)
            continue
        for name, ref in _HTML_ENTITIES.items():
            part = part.replace(f"&{name};", ref)
        part = _BARE_AMP.sub("&amp;", part)
        part = _INVALID_XML_CHARS.sub("", part)
        out.append(part)
    return "".join(out).encode("utf-8", "replace")


def parse_feed(xml_bytes: bytes, feed: dict) -> list[dict]:
    xml_bytes = xml_bytes.lstrip(b" \t\r\n\xef\xbb\xbf")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        root = ET.fromstring(
            sanitise_xml(xml_bytes.decode("utf-8", "replace")))
    items = []
    nodes = [e for e in root.iter()
             if local(e.tag) in ("item", "entry")]
    for node in nodes[:MAX_ITEMS_PER_FEED]:
        title = strip_html(child_text(node, {"title"}))
        link = child_text(node, {"link"})
        if not link:                          # Atom: <link href="..."/>
            link = child_attr(node, {"link"}, "href")
        link = link.strip()
        if not title or not link:
            continue
        content = ""
        for c in find_descendants(node, "encoded"):
            if c.text:
                content = c.text
                break
        if not content:
            for c in find_descendants(node, "content"):
                if c.text and c.get("type", "text").lower() in (
                        "text", "html", "xhtml"):
                    content = c.text
                    break
        desc = child_text(node, {"description", "summary"})
        body = content or desc
        date_raw = (child_text(node, {"pubdate", "published", "updated",
                                      "date"})
                    or child_text(node, {"date"}))
        items.append({
            "title": title,
            "link": link,
            "raw_text": body,
            "date_raw": date_raw,
            "date": parse_date(date_raw),
        })
    return items


# ---------------------------------------------------------------------------
# Excerpt rules (excerpt-only feeds: 200-word hard ceiling)
# ---------------------------------------------------------------------------

def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[\"'“\(\[]?[A-Z0-9])", text)
    return [p.strip() for p in parts if p.strip()]


def break_long_paragraph(para: str, max_len: int = MAX_PARA_CHARS) -> list[str]:
    if len(para) <= max_len:
        return [para]
    sents = split_sentences(para)
    if len(sents) <= 1:
        words = para.split()
        chunks, cur = [], ""
        for w in words:
            if cur and len(cur) + 1 + len(w) > max_len:
                chunks.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip() if cur else w
        if cur:
            chunks.append(cur)
        return chunks
    chunks, cur = [], ""
    for s in sents:
        if cur and len(cur) + 1 + len(s) > max_len:
            chunks.append(cur)
            cur = s
        else:
            cur = (cur + " " + s).strip() if cur else s
    if cur:
        chunks.append(cur)
    return chunks


def to_display_paragraphs(text: str, max_paras: int, max_words: int,
                          max_chars: int) -> str:
    src_paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not src_paras:
        return ""
    kept, words, truncated = [], 0, False
    for p in src_paras:
        pw = p.split()
        room = max_words - words
        if room <= 0:
            truncated = True
            break
        if len(pw) > room:
            kept.append(" ".join(pw[:room]))
            words += room
            truncated = True
            break
        kept.append(p)
        words += len(pw)
    disp = []
    for p in kept:
        disp.extend(break_long_paragraph(p))
    if len(disp) > max_paras:
        disp = disp[:max_paras]
        truncated = True
    out = "\n\n".join(disp)
    if len(out) > max_chars:
        cut = out[:max_chars - 1]
        idx = max(cut.rfind(" "), cut.rfind("\n"))
        if idx > 0:
            cut = cut[:idx]
        out = cut.rstrip(" .,;:\n") + "…"
        truncated = True
    elif truncated:
        out = out.rstrip(" .,;:\n") + "…"
    return out


def apply_excerpt(raw_text: str) -> tuple[str, int]:
    """Excerpt-only rule: the short excerpt the RSS feed supplies, HARD
    ceiling 200 words; the card shows a readable teaser (first 3
    paragraphs / ~300 words / ~1500 characters, tighter limit wins)."""
    text = strip_html(raw_text)
    limit = min(MAX_WORDS_EXCERPT, MAX_WORDS_DISPLAY)
    text = to_display_paragraphs(text, MAX_PARAS_DISPLAY, limit,
                                 MAX_CHARS_DISPLAY)
    return text, len(text.split())


def normalise_link(link: str) -> str:
    link = link.strip().split("#")[0]
    if link.endswith("/"):
        link = link[:-1]
    return link


# ---------------------------------------------------------------------------
# Near-duplicate detection (same story, different feed/headline)
# ---------------------------------------------------------------------------

TITLE_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "at", "by", "from", "its", "it", "is", "are", "as", "new", "this",
    "that", "these", "those", "will", "would", "can", "could", "has",
    "have", "had", "be", "been", "was", "were", "into", "over", "under",
    "after", "before", "between", "about", "against", "through", "during",
    "per", "via", "vs",
}
NEAR_DUP_JACCARD = 0.50
NEAR_DUP_JACCARD_MIN = 4
NEAR_DUP_OVERLAP = 0.80
NEAR_DUP_OVERLAP_MIN = 5
AGGREGATOR_WINDOW_MIN = 120


def title_word_set(title: str) -> frozenset:
    t = (title or "").strip()
    for sep in (" | ", " - "):
        idx = t.rfind(sep)
        if idx > 0 and len(t[idx + len(sep):].split()) <= 5:
            t = t[:idx]
            break
    t = t.lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    words = set()
    for w in t.split():
        if w in TITLE_STOPWORDS:
            continue
        if len(w) == 1 and w.isalpha():
            continue
        words.add(w)
    return frozenset(words)


def titles_near_duplicate(a: frozenset, b: frozenset) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 6 and len(b) >= 6 and len(a ^ b) <= 2:
        return False
    inter = len(a & b)
    if inter == 0:
        return False
    jaccard = inter / len(a | b)
    if jaccard >= NEAR_DUP_JACCARD and inter >= NEAR_DUP_JACCARD_MIN:
        return True
    overlap = inter / min(len(a), len(b))
    if overlap >= NEAR_DUP_OVERLAP and inter >= NEAR_DUP_OVERLAP_MIN:
        return True
    return False


def same_event_aggregator(a: dict, kept_a: dict, ws, ks,
                          freq: dict) -> bool:
    feed = a["feed"]
    if not (feed.startswith("Google News")
            or feed.startswith("Bing News")):
        return False
    if feed != kept_a["feed"]:
        return False
    da, db = a["date"], kept_a["date"]
    if not da or not db or da[:10] != db[:10]:
        return False
    if abs((a["_date_sort"] - kept_a["_date_sort"]).total_seconds()) \
            > AGGREGATOR_WINDOW_MIN * 60:
        return False
    shared = ws & ks
    if len(shared) >= 3:
        return True
    rare = [w for w in shared if freq.get(w, 0) <= 2]
    return len(shared) >= 2 and len(rare) >= 2


# ---------------------------------------------------------------------------
# Per-feed worker
# ---------------------------------------------------------------------------

def process_feed(feed: dict) -> dict:
    result = {"feed": feed, "items": [], "error": None, "count": 0}
    try:
        raw = fetch_url(feed["url"])
        if not raw.strip():
            raise ValueError("empty response")
        head = raw.lstrip()[:200].lower()
        if head.startswith(b"<html") or head.startswith(b"<!doctype html"):
            raise ValueError("returned an HTML page, not a feed")
        parsed = parse_feed(raw, feed)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    # Relevance filter (optional, per feed): The War Zone covers UAP as
    # one beat among general defense reporting, so only its UFO/UAP
    # items belong in this section. Other feeds are UAP-first or
    # topic-query feeds, so they need no filter.
    filt = feed.get("filter")
    if filt:
        rx = re.compile(filt, re.I)
        before = len(parsed)
        parsed = [it for it in parsed if rx.search(it["title"])]
        result["filtered"] = before - len(parsed)
    articles = []
    for it in parsed:
        excerpt, wc = apply_excerpt(it["raw_text"])
        articles.append({
            "title": it["title"],
            "link": it["link"],
            "source": feed["publisher"],
            "publisher": feed["publisher"],
            "feed": feed["name"],
            "topic": "UFOs & UAPs",
            "date": it["date"].isoformat() if it["date"] else None,
            "_date_sort": it["date"] or datetime.min.replace(
                tzinfo=timezone.utc),
            "excerpt": excerpt,
            "_words": wc,
        })
    result["items"] = articles
    result["count"] = len(articles)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="UFO / UAP RSS aggregator")
    ap.add_argument("--feeds", default=str(FEEDS_JSON))
    ap.add_argument("--out", default=str(OUT_JSON))
    args = ap.parse_args()

    try:
        cfg = json.loads(Path(args.feeds).read_text(encoding="utf-8"))
        feeds = cfg["feeds"] if isinstance(cfg, dict) else cfg
    except Exception as exc:
        print(f"FATAL: cannot read feed list {args.feeds}: {exc}",
              file=sys.stderr)
        return 1
    print(f"Feeds in list: {len(feeds)}")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for res in ex.map(process_feed, feeds):
            results.append(res)

    succeeded = [r for r in results if r["error"] is None]
    failed = [r for r in results if r["error"] is not None]
    print(f"Feeds succeeded: {len(succeeded)} / {len(feeds)}")
    for r in results:
        if r.get("filtered"):
            print(f"  Filtered {r['filtered']} off-topic items from "
                  f"{r['feed']['name']}")
    for r in failed:
        print(f"  FAILED {r['feed']['name']} "
              f"({r['feed']['url']}): {r['error']}")

    all_items = [a for r in succeeded for a in r["items"]]
    all_items.sort(key=lambda a: a["_date_sort"], reverse=True)
    seen, deduped = set(), []
    dupes = 0
    for a in all_items:
        key = normalise_link(a["link"])
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        deduped.append(a)
    print(f"Items fetched: {len(all_items)}; duplicates removed: {dupes}; "
          f"unique: {len(deduped)}")

    deduped = deduped[:MAX_ITEMS_TOTAL]
    print(f"Capped at newest {MAX_ITEMS_TOTAL}: {len(deduped)} articles")

    from collections import defaultdict
    _word_feeds = defaultdict(set)
    for _a in deduped:
        for _w in title_word_set(_a["title"]):
            _word_feeds[_w].add(_a["feed"])
    _freq = {w: len(fs) for w, fs in _word_feeds.items()}
    kept_sets, kept_arts, final = [], [], []
    near_dupes = 0
    for a in deduped:
        ws = title_word_set(a["title"])
        hit = None
        for i, ks in enumerate(kept_sets):
            if titles_near_duplicate(ws, ks):
                hit = i
                break
            if same_event_aggregator(a, kept_arts[i], ws, ks, _freq):
                hit = i
                break
        if hit is None:
            kept_sets.append(ws)
            kept_arts.append(a)
            final.append(a)
        else:
            near_dupes += 1
    deduped = final
    print(f"Near-duplicates removed: {near_dupes}; "
          f"articles after dedupe: {len(deduped)}")

    over = [a for a in deduped if a["_words"] > MAX_WORDS_EXCERPT]
    print(f"Excerpt-feed items over {MAX_WORDS_EXCERPT} words: {len(over)}")

    articles = []
    for a in deduped:
        articles.append({
            "title": a["title"],
            "link": a["link"],
            "source": a["source"],
            "publisher": a["publisher"],
            "feed": a["feed"],
            "topic": a["topic"],
            "date": a["date"],
            "excerpt": a["excerpt"],
        })

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(articles, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"Wrote {args.out}: {len(articles)} articles")
    if not succeeded:
        print("FATAL: no feed succeeded", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
