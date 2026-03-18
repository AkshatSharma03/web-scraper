# Google Search Scraper

A lightweight, production-ready Python tool for extracting Google search results.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### CLI
```bash
python google_scraper.py "your search query"
```

### REST API
```bash
python api.py
# Visit http://localhost:8000/docs
```

## Features

- Extracts first 20 Google search results
- Fetches and extracts main text content from each page
- Parallel processing (5 concurrent requests)
- CSV export with timestamps
- REST API with FastAPI
- Docker support

## License

MIT
