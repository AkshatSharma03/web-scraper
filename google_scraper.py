#!/usr/bin/env python3
"""
Google Search Scraper
Uses Google Custom Search API to extract search results and page content.

Setup (one-time):
  1. Get a free API key at: https://console.cloud.google.com/apis/credentials
     (Enable "Custom Search API" in the API library)
  2. Create a search engine at: https://programmablesearchengine.google.com/
     (Turn on "Search the entire web")
  3. Set env vars:
       export GOOGLE_API_KEY="your_api_key"
       export GOOGLE_CSE_ID="your_search_engine_id"

Free tier: 100 queries/day. More info: https://developers.google.com/custom-search/v1/overview
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

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")
GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"

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
    "lr": "",
    "cr": "",
    "hl": "en",
    "max_results": MAX_RESULTS,
    "date_restrict": "",
}


def _check_credentials():
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        print(
            "\n❌  Google API credentials not set.\n"
            "\n"
            "Quick setup (free, takes ~5 minutes):\n"
            "  1. Go to: https://console.cloud.google.com/apis/credentials\n"
            "     → Create a new API key\n"
            "     → Enable 'Custom Search API' in the API Library\n"
            "\n"
            "  2. Go to: https://programmablesearchengine.google.com/\n"
            "     → Create a new search engine\n"
            "     → Enable 'Search the entire web'\n"
            "     → Copy the Search Engine ID (cx)\n"
            "\n"
            "  3. Set environment variables:\n"
            "       export GOOGLE_API_KEY='your_api_key'\n"
            "       export GOOGLE_CSE_ID='your_search_engine_id'\n"
            "\n"
            "  Free tier: 100 queries/day\n"
        )
        sys.exit(1)


def extract_google_results(
    query: str,
    max_results: int = MAX_RESULTS,
    gl: str = "",
    lr: str = "",
    cr: str = "",
    hl: str = "en",
    date_restrict: str = "",
) -> list:
    """
    Extract Google search results using the Custom Search API.

    Args:
        query:        Search query string.
        max_results:  Number of results to return (1-100).
        gl:           Geo bias country code, e.g. 'fr', 'de', 'us'.
        lr:           Language restrict, e.g. 'lang_fr', 'lang_en'.
        cr:           Country restrict, e.g. 'countryFR', 'countryUS'.
        hl:           Interface language, e.g. 'en', 'fr'. Default 'en'.
        date_restrict: Date restrict, e.g. 'd7' (7 days), 'm1' (1 month).
    """
    locale_parts = [
        f"gl={gl}" if gl else "",
        f"lr={lr}" if lr else "",
        f"cr={cr}" if cr else "",
        f"date={date_restrict}" if date_restrict else "",
    ]
    locale_info = " | ".join(p for p in locale_parts if p)
    suffix = f" [{locale_info}]" if locale_info else ""
    print(f"🔍 Searching Google for: '{query}'{suffix}")

    results = []
    for start in range(1, max_results + 1, 10):
        if start > 91:
            break
        batch_size = min(10, max_results - len(results))
        params = {
            "key": GOOGLE_API_KEY,
            "cx": GOOGLE_CSE_ID,
            "q": query,
            "num": batch_size,
            "start": start,
            "hl": hl or "en",
        }
        if gl:
            params["gl"] = gl
        if lr:
            params["lr"] = lr
        if cr:
            params["cr"] = cr
        if date_restrict:
            params["dateRestrict"] = date_restrict

        try:
            resp = requests.get(GOOGLE_CSE_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"❌ API error: {e}")
            break

        data = resp.json()

        if "error" in data:
            err = data["error"]
            print(f"❌ API error {err.get('code')}: {err.get('message')}")
            break

        items = data.get("items", [])
        if not items:
            break

        for item in items:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "description": item.get("snippet", "").replace("\n", " "),
                "content": None,
            })

        if len(results) >= max_results:
            break

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

        content = " ".join(content.split())[:2000]
        return content if content else None
    except Exception:
        return None


def fetch_all_content(results: list) -> list:
    """Fetch content from all result pages in parallel."""
    print(f"\n📥 Fetching content from {len(results)} pages...")

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
    fieldnames = ["query_index", "query", "gl", "lr", "cr", "title", "url", "description", "content"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(batch_results)
    print(f"\n💾 Batch results saved to: {filename}")


def load_batch_file(path: str) -> list:
    """
    Load a batch query file (CSV or JSON) and return a normalised list of job dicts.

    CSV format — header row required:
        query, gl, lr, cr, hl, max_results, date_restrict
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
                print(f"  ⚠️  Invalid max_results for query '{item['query']}', using default {MAX_RESULTS}.")
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
                    print(f"  ⚠️  Invalid max_results for query '{job['query']}', using default {MAX_RESULTS}.")
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
            gl=job["gl"],
            lr=job["lr"],
            cr=job["cr"],
            hl=job["hl"],
            date_restrict=job["date_restrict"],
        )
        if not results:
            print(f"  No results, skipping.")
            continue

        results = fetch_all_content(results)

        for row in results:
            row["query_index"] = idx + 1
            row["query"] = job["query"]
            row["gl"] = job["gl"]
            row["lr"] = job["lr"]
            row["cr"] = job["cr"]

        all_results.extend(results)

    if all_results:
        save_batch_to_csv(all_results, output_file)
    else:
        print("No results collected from any batch job.")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Google Search Scraper — extracts results via Google Custom Search API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # Single query (default settings)
  python google_scraper.py "machine learning"

  # Convenience country + language flags
  python google_scraper.py "intelligence artificielle" --country fr --language fr

  # All three locale params + date filter
  python google_scraper.py "climat" --gl fr --lr lang_fr --cr countryFR --date-restrict d30

  # More results with custom output file
  python google_scraper.py "AI research" --max-results 50 --output ai.csv

  # Batch mode (CSV or JSON input)
  python google_scraper.py --batch queries.csv
  python google_scraper.py --batch queries.json --output combined.csv
        """,
    )

    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Search query string (omit when using --batch).",
    )

    # Convenience aliases
    parser.add_argument(
        "--country",
        dest="country_shortcut",
        default="",
        metavar="CODE",
        help="2-letter country code for geo bias (alias for --gl). E.g. 'fr', 'de', 'us'.",
    )
    parser.add_argument(
        "--language",
        dest="language_shortcut",
        default="",
        metavar="CODE",
        help="2-letter language code (alias for --lr; auto-prefixed with 'lang_'). E.g. 'fr' → 'lang_fr'.",
    )

    # Raw API params
    parser.add_argument(
        "--gl",
        default="",
        metavar="CODE",
        help="Geo bias country code (overrides --country). E.g. 'fr'.",
    )
    parser.add_argument(
        "--lr",
        default="",
        metavar="LANG_CODE",
        help="Language restrict (overrides --language). E.g. 'lang_fr'.",
    )
    parser.add_argument(
        "--cr",
        default="",
        metavar="COUNTRY_CODE",
        help="Country restrict — pages from this country. E.g. 'countryFR'.",
    )
    parser.add_argument(
        "--hl",
        default="en",
        metavar="CODE",
        help="Interface language. Default: 'en'.",
    )
    parser.add_argument(
        "--date-restrict",
        dest="date_restrict",
        default="",
        metavar="PERIOD",
        help="Restrict to recent results. E.g. 'd7' (7 days), 'm1' (1 month), 'y1' (1 year).",
    )

    parser.add_argument(
        "--max-results",
        dest="max_results",
        type=int,
        default=MAX_RESULTS,
        metavar="N",
        help=f"Number of results to fetch (1-100). Default: {MAX_RESULTS}.",
    )
    parser.add_argument(
        "--batch",
        default=None,
        metavar="FILE",
        help="Path to a CSV or JSON batch file with multiple queries.",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help="Output CSV filename. Default: auto-generated timestamped name.",
    )

    args = parser.parse_args()

    # Resolve convenience aliases vs raw params (raw takes precedence)
    gl_final = args.gl or args.country_shortcut
    if args.lr:
        lr_final = args.lr
    elif args.language_shortcut:
        lang = args.language_shortcut.strip().lower()
        lr_final = lang if lang.startswith("lang_") else f"lang_{lang}"
    else:
        lr_final = ""

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
        lr=lr_final,
        cr=args.cr,
        hl=args.hl,
        date_restrict=args.date_restrict,
    )

    if not results:
        print("No results found.")
        return

    results = fetch_all_content(results)
    save_to_csv(results, output_file)


if __name__ == "__main__":
    main()
