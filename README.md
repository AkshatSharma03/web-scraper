# Google Search Scraper

A Python tool for extracting real Google search results across multiple countries and languages — built for research. Powered by [Serper.dev](https://serper.dev).

## Setup

**1. Get a free API key**
- Sign up at [serper.dev](https://serper.dev) — no credit card, 2,500 free searches included
- Copy your API key from the dashboard

**2. Set the environment variable**
```bash
export SERPER_API_KEY="your_api_key"
```

To make it permanent, add it to your `~/.zshrc`:
```bash
echo 'export SERPER_API_KEY="your_api_key"' >> ~/.zshrc && source ~/.zshrc
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

---

## CLI Usage

### Basic search
```bash
python google_scraper.py "your search query"
```

### Target a specific country and language
```bash
# Convenience flags
python google_scraper.py "intelligence artificielle" --country fr --language fr

# Raw API params (more control)
python google_scraper.py "Klimawandel" --gl de --hl de
```

### Filter by date
```bash
python google_scraper.py "AI news" --date-restrict d7      # past week
python google_scraper.py "climate change" --date-restrict m1  # past month
python google_scraper.py "research" --date-restrict y1     # past year
```

### Control output
```bash
python google_scraper.py "query" --max-results 50 --output results.csv
```

### All flags
| Flag | Description | Example |
|---|---|---|
| `--country` | Country for geo targeting (alias for `--gl`) | `fr`, `de`, `us`, `jp` |
| `--language` | Language of results (alias for `--hl`) | `fr`, `de`, `en`, `ja` |
| `--gl` | Raw country code (overrides `--country`) | `fr` |
| `--hl` | Raw language code (overrides `--language`) | `fr` |
| `--date-restrict` | Recency filter | `d1`, `d7`, `m1`, `m3`, `y1` |
| `--max-results` | Number of results, 1–100 (default: 20) | `50` |
| `--batch` | Path to a CSV or JSON batch file | `queries.csv` |
| `--output` | Output CSV filename (default: timestamped) | `results.csv` |

---

## Batch Mode

Run multiple queries at once — each with its own country, language, and date settings. All results are combined into a single CSV with provenance columns.

### CSV batch file (`queries.csv`)
```
query,gl,hl,max_results,date_restrict
machine learning,us,en,20,
intelligence artificielle,fr,fr,20,
Klimawandel,de,de,15,m1
AI news,jp,ja,10,d7
```

### JSON batch file (`queries.json`)
```json
[
  { "query": "machine learning" },
  { "query": "intelligence artificielle", "gl": "fr", "hl": "fr" },
  { "query": "Klimawandel", "gl": "de", "hl": "de", "date_restrict": "m1" },
  { "query": "AI news", "gl": "jp", "hl": "ja", "max_results": 10 }
]
```

### Run batch
```bash
python google_scraper.py --batch queries.csv --output combined.csv
python google_scraper.py --batch queries.json
```

### Batch output columns
`query_index`, `query`, `gl`, `hl`, `title`, `url`, `description`, `content`

---

## REST API

```bash
python api.py
# Visit http://localhost:8000/docs for interactive UI
```

### POST `/api/search`
```json
{
  "query": "intelligence artificielle",
  "gl": "fr",
  "hl": "fr",
  "max_results": 20,
  "date_restrict": "m1"
}
```

### GET `/health`
Returns API status and whether `SERPER_API_KEY` is configured.

---

## Output

Each result row contains:

| Column | Description |
|---|---|
| `title` | Page title |
| `url` | Page URL |
| `description` | Google snippet |
| `content` | Extracted page text (up to 2,000 chars) |

---

## Docker

```bash
docker build -t google-scraper .
docker run -e SERPER_API_KEY="your_key" google-scraper "your query"
```

---

## License

MIT
