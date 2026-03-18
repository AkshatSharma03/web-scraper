#!/usr/bin/env python3
"""
Google Search Scraper
Uses Serper.dev API to extract real Google search results and page content.

Setup (one-time, free):
  1. Sign up at: https://serper.dev  (no credit card — 2,500 free searches)
  2. Copy your API key from the dashboard
  3. Set env var:
       export SERPER_API_KEY="your_api_key"
"""

import requests
import sys
import os
import csv
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "beautifulsoup4", "requests"])
    from bs4 import BeautifulSoup

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
SERPER_URL = "https://google.serper.dev/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
MAX_RESULTS = 20
REQUEST_TIMEOUT = 10
THREAD_POOL_SIZE = 5

BATCH_DEFAULTS = {
    "gl": "",
    "hl": "en",
    "max_results": MAX_RESULTS,
    "date_restrict": "",
}

# Map Google-style date_restrict (d7, m1, y1) → Serper tbs param
DATE_RESTRICT_MAP = {
    "d1": "qdr:d",
    "d7": "qdr:w",
    "d30": "qdr:m",
    "m1": "qdr:m",
    "m3": "qdr:m3",
    "m6": "qdr:m6",
    "y1": "qdr:y",
}


def _check_credentials():
    if not SERPER_API_KEY:
        print(
            "\n❌  Serper API key not set.\n"
            "\n"
            "Quick setup (free, 2,500 searches included — no credit card):\n"
            "  1. Go to: https://serper.dev\n"
            "  2. Sign up and copy your API key from the dashboard\n"
            "  3. Set environment variable:\n"
            "       export SERPER_API_KEY='your_api_key'\n"
        )
        sys.exit(1)


def _map_date_restrict(date_restrict: str) -> str:
    """Convert Google-style date_restrict to Serper tbs format."""
    if not date_restrict:
        return ""
    if date_restrict.startswith("qdr:"):
        return date_restrict
    return DATE_RESTRICT_MAP.get(date_restrict, "")


def extract_google_results(
    query: str,
    max_results: int = MAX_RESULTS,
    gl: str = "",
    hl: str = "en",
    date_restrict: str = "",
    # lr / cr kept for CLI/API compat — Serper uses gl+hl instead
    lr: str = "",
    cr: str = "",
) -> list:
    """
    Extract Google search results via Serper.dev API.

    Args:
        query:        Search query string.
        max_results:  Number of results to return (1-100).
        gl:           Country code for geo targeting, e.g. 'fr', 'de', 'us'.
        hl:           Language of results, e.g. 'fr', 'de', 'en' (default 'en').
        date_restrict: Restrict to recent results: 'd1','d7','m1','m3','y1'.
        lr:           (Legacy param — derived to hl if hl not set.)
        cr:           (Legacy param — not used by Serper.)
    """
    # Derive hl from lr if not explicitly set (e.g. "lang_fr" → "fr")
    if not hl and lr and lr.startswith("lang_"):
        hl = lr[5:]

    locale_parts = [
        f"gl={gl}" if gl else "",
        f"hl={hl}" if hl else "",
        f"date={date_restrict}" if date_restrict else "",
    ]
    locale_info = " | ".join(p for p in locale_parts if p)
    suffix = f" [{locale_info}]" if locale_info else ""
    print(f"🔍 Searching Google for: '{query}'{suffix}")

    api_headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    tbs = _map_date_restrict(date_restrict)

    results = []
    page = 1
    # Serper returns 10 results per page; paginate until we have enough
    while len(results) < max_results:
        payload = {
            "q": query,
            "num": 10,
            "page": page,
            "hl": hl or "en",
        }
        if gl:
            payload["gl"] = gl
        if tbs:
            payload["tbs"] = tbs

        try:
            resp = requests.post(SERPER_URL, json=payload, headers=api_headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"❌ API error: {e}")
            break

        data = resp.json()

        if "error" in data:
            print(f"❌ API error: {data['error']}")
            break

        items = data.get("organic", [])
        if not items:
            break

        for item in items:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "description": item.get("snippet", "").replace("\n", " "),
                "content": None,
            })

        page += 1

    print(f"✅ Found {len(results)} results")
    return results[:max_results]


def extract_page_content(url: str) -> Optional[str]:
    """Extract main text content from a webpage."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        response.raise_for_status()

        content = None
        if HAS_TRAFILATURA:
            content = trafilatura.extract(response.text, include_comments=False)

        if not content:
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            content = soup.get_text()

        content = " ".join(content.split())
        return content if content else None
    except Exception:
        return None


def fetch_all_content(results: list) -> list:
    """Fetch content from all result pages in parallel."""
    print(f"\n📥 Fetching page content from {len(results)} result URLs...")

    with ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE) as executor:
        future_to_idx = {
            executor.submit(extract_page_content, r["url"]): i
            for i, r in enumerate(results)
        }
        completed = 0
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx]["content"] = future.result()
                completed += 1
                print(f"  [{completed}/{len(results)}] ✓")
            except Exception:
                pass

    return results


def save_to_csv(results: list, filename: str):
    """Save single-query results to CSV."""
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "url", "description", "content"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\n💾 Results saved to: {filename}")


def save_batch_to_csv(batch_results: list, filename: str):
    """Save batch results (multiple queries) to a single CSV with provenance columns."""
    fieldnames = ["query_index", "query", "gl", "hl", "title", "url", "description", "content"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(batch_results)
    print(f"\n💾 Batch results saved to: {filename}")


def load_batch_file(path: str) -> list:
    """
    Load a batch query file (CSV or JSON) and return a normalised list of job dicts.

    CSV format — header row required:
        query, gl, hl, max_results, date_restrict
        (only 'query' is required; all other columns are optional)

    JSON format — top-level array of objects with the same fields.
        (only 'query' key is required per object)
    """
    p = Path(path)
    if not p.exists():
        print(f"❌ Batch file not found: {path}")
        sys.exit(1)

    suffix = p.suffix.lower()
    jobs = []

    if suffix == ".json":
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            print("❌ JSON batch file must be a top-level array.")
            sys.exit(1)
        for item in raw:
            if "query" not in item:
                print(f"  ⚠️  Skipping item missing 'query': {item}")
                continue
            job = {**BATCH_DEFAULTS, **item}
            try:
                job["max_results"] = int(job["max_results"])
            except (ValueError, TypeError):
                job["max_results"] = MAX_RESULTS
            jobs.append(job)

    elif suffix == ".csv":
        with open(p, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row.get("query", "").strip():
                    continue
                job = {**BATCH_DEFAULTS}
                for key in BATCH_DEFAULTS:
                    if key in row and row[key].strip():
                        job[key] = row[key].strip()
                job["query"] = row["query"].strip()
                try:
                    job["max_results"] = int(job["max_results"])
                except (ValueError, TypeError):
                    job["max_results"] = MAX_RESULTS
                jobs.append(job)
    else:
        print(f"❌ Unsupported batch file format: '{suffix}'. Use .csv or .json")
        sys.exit(1)

    return jobs


def run_batch(jobs: list, output_file: str):
    """Execute all jobs from a batch file and write combined results to one CSV."""
    _check_credentials()
    all_results = []

    for idx, job in enumerate(jobs):
        print(f"\n--- Batch job {idx + 1}/{len(jobs)}: '{job['query']}' ---")
        results = extract_google_results(
            query=job["query"],
            max_results=job["max_results"],
            gl=job.get("gl", ""),
            hl=job.get("hl", "en"),
            date_restrict=job.get("date_restrict", ""),
        )
        if not results:
            print("  No results, skipping.")
            continue

        results = fetch_all_content(results)

        for row in results:
            row["query_index"] = idx + 1
            row["query"] = job["query"]
            row["gl"] = job.get("gl", "")
            row["hl"] = job.get("hl", "en")

        all_results.extend(results)

    if all_results:
        save_batch_to_csv(all_results, output_file)
    else:
        print("No results collected from any batch job.")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Google Search Scraper — extracts real Google results via Serper.dev API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # Single query (default settings)
  python google_scraper.py "machine learning"

  # French results in French
  python google_scraper.py "intelligence artificielle" --country fr --language fr

  # German results, last 30 days
  python google_scraper.py "Klimawandel" --gl de --hl de --date-restrict m1

  # More results with custom output file
  python google_scraper.py "AI research" --max-results 50 --output ai.csv

  # Batch mode (CSV or JSON input)
  python google_scraper.py --batch queries.csv
  python google_scraper.py --batch queries.json --output combined.csv

date-restrict values:
  d1=past day, d7=past week, m1=past month, m3=past 3 months, y1=past year
        """,
    )

    parser.add_argument("query", nargs="?", default=None,
                        help="Search query (omit when using --batch).")

    # Convenience aliases
    parser.add_argument("--country", dest="country_shortcut", default="", metavar="CODE",
                        help="Country code for geo targeting (alias for --gl). E.g. 'fr', 'de', 'us'.")
    parser.add_argument("--language", dest="language_shortcut", default="", metavar="CODE",
                        help="Language of results (alias for --hl). E.g. 'fr', 'de', 'en'.")

    # Raw API params
    parser.add_argument("--gl", default="", metavar="CODE",
                        help="Country code (overrides --country). E.g. 'fr'.")
    parser.add_argument("--hl", default="en", metavar="CODE",
                        help="Language of results (overrides --language). Default: 'en'.")

    # Legacy params kept for batch file compatibility
    parser.add_argument("--lr", default="", metavar="LANG_CODE",
                        help="Language restrict, e.g. 'lang_fr' (derived to --hl if hl not set).")
    parser.add_argument("--cr", default="", metavar="COUNTRY_CODE",
                        help="(Legacy — not used by Serper.dev.)")

    parser.add_argument("--date-restrict", dest="date_restrict", default="", metavar="PERIOD",
                        help="Restrict to recent results: d1, d7, m1, m3, y1.")
    parser.add_argument("--max-results", dest="max_results", type=int, default=MAX_RESULTS,
                        metavar="N", help=f"Number of results (1-100). Default: {MAX_RESULTS}.")
    parser.add_argument("--batch", default=None, metavar="FILE",
                        help="CSV or JSON batch file with multiple queries.")
    parser.add_argument("--output", default=None, metavar="FILE",
                        help="Output CSV filename (default: auto-timestamped).")

    args = parser.parse_args()

    gl_final = args.gl or args.country_shortcut
    hl_final = args.hl if args.hl != "en" else (args.language_shortcut or args.hl)

    output_file = args.output or f"search_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    if args.batch:
        jobs = load_batch_file(args.batch)
        if not jobs:
            print("No valid jobs found in batch file.")
            sys.exit(1)
        print(f"Loaded {len(jobs)} job(s) from '{args.batch}'.")
        run_batch(jobs, output_file)
        return

    if not args.query:
        parser.error("A query argument is required unless --batch is used.")

    _check_credentials()
    results = extract_google_results(
        query=args.query,
        max_results=args.max_results,
        gl=gl_final,
        hl=hl_final,
        date_restrict=args.date_restrict,
        lr=args.lr,
        cr=args.cr,
    )

    if not results:
        print("No results found.")
        return

    results = fetch_all_content(results)
    save_to_csv(results, output_file)


if __name__ == "__main__":
    main()
