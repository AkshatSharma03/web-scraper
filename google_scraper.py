#!/usr/bin/env python3
"""
Lightweight Google Search Scraper
Extracts first 20 Google search results and their page content
"""

import requests
import sys
import time
import csv
from pathlib import Path
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing required packages...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "beautifulsoup4", "requests"])
    from bs4 import BeautifulSoup

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

GOOGLE_SEARCH_URL = "https://www.google.com/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
MAX_RESULTS = 20
REQUEST_TIMEOUT = 10
THREAD_POOL_SIZE = 5
OUTPUT_CSV = f"search_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

def extract_google_results(query: str) -> list:
    """Extract Google search results for given query."""
    print(f"🔍 Searching Google for: '{query}'")
    params = {"q": query, "num": 100, "hl": "en"}
    
    try:
        response = requests.get(GOOGLE_SEARCH_URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"❌ Error: {e}")
        return []
    
    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    
    for result in soup.select("div.g, div.Gd5Gd"):
        if len(results) >= MAX_RESULTS:
            break
        
        try:
            title_elem = result.select_one("h3")
            if not title_elem:
                continue
            title = title_elem.get_text(strip=True)
            
            link_elem = result.select_one("a[href]")
            if not link_elem:
                continue
            
            url = link_elem.get("href", "")
            if url.startswith("/url?q="):
                url = url.split("/url?q=")[1].split("&")[0]
            
            if not url.startswith("http"):
                continue
            
            desc_elem = result.select_one("div.VwiC3b")
            description = desc_elem.get_text(strip=True) if desc_elem else ""
            
            results.append({"title": title, "url": url, "description": description, "content": None})
        except Exception:
            continue
    
    print(f"✅ Found {len(results)} results")
    return results

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
            for script in soup(["script", "style"]):
                script.decompose()
            content = soup.get_text()
        
        content = " ".join(content.split())[:2000]
        return content if content else None
    except Exception:
        return None

def fetch_all_content(results: list) -> list:
    """Fetch content from all results in parallel."""
    print(f"\n📥 Fetching content from {len(results)} pages...")
    
    with ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE) as executor:
        future_to_idx = {executor.submit(extract_page_content, result["url"]): i for i, result in enumerate(results)}
        
        completed = 0
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                content = future.result()
                results[idx]["content"] = content
                completed += 1
                print(f"  [{completed}/{len(results)}] ✓")
            except Exception:
                pass
    
    return results

def save_to_csv(results: list, filename: str):
    """Save results to CSV file."""
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "url", "description", "content"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\n💾 Results saved to: {filename}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python google_scraper.py \"your search query\"")
        sys.exit(1)
    
    query = " ".join(sys.argv[1:])
    results = extract_google_results(query)
    
    if not results:
        print("No results found.")
        return
    
    results = fetch_all_content(results)
    save_to_csv(results, OUTPUT_CSV)

if __name__ == "__main__":
    main()
