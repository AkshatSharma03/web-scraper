#!/usr/bin/env python3
"""FastAPI REST API for Google Search Scraper"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
import time
import os
from datetime import datetime
from pathlib import Path
import google_scraper

app = FastAPI(
    title="Google Search Scraper API",
    description="REST API for scraping Google search results via the Custom Search API",
    version="1.0.0",
    docs_url="/docs"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

startup_time = time.time()


class SearchQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    max_results: int = Field(20, ge=1, le=100)
    gl: str = Field("", max_length=2, description="Geo bias country code, e.g. 'fr', 'de', 'us'.")
    lr: str = Field("", max_length=10, description="Language restrict, e.g. 'lang_fr', 'lang_en'.")
    cr: str = Field("", max_length=12, description="Country restrict, e.g. 'countryFR', 'countryUS'.")
    hl: str = Field("en", max_length=5, description="Interface language, e.g. 'en', 'fr'.")
    date_restrict: str = Field("", max_length=5, description="Date restrict, e.g. 'd7', 'm1', 'y1'.")


class SearchResult(BaseModel):
    title: str
    url: str
    description: str
    content: Optional[str] = None


class SearchResponse(BaseModel):
    success: bool
    query: str
    gl: str
    lr: str
    cr: str
    results_count: int
    results: List[SearchResult]
    execution_time: float


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "uptime": time.time() - startup_time,
        "credentials_configured": bool(os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_CSE_ID")),
    }


@app.get("/")
async def root():
    return {
        "name": "Google Search Scraper API",
        "docs": "/docs"
    }


@app.post("/api/search", response_model=SearchResponse)
async def search(request: SearchQuery):
    if not os.getenv("GOOGLE_API_KEY") or not os.getenv("GOOGLE_CSE_ID"):
        raise HTTPException(
            status_code=503,
            detail=(
                "Google API credentials not configured. "
                "Set GOOGLE_API_KEY and GOOGLE_CSE_ID environment variables. "
                "See https://developers.google.com/custom-search/v1/overview for setup."
            ),
        )

    start_time = time.time()
    try:
        print(f"🔍 Searching for: {request.query}")
        results = google_scraper.extract_google_results(
            query=request.query,
            max_results=request.max_results,
            gl=request.gl,
            lr=request.lr,
            cr=request.cr,
            hl=request.hl,
            date_restrict=request.date_restrict,
        )

        if not results:
            raise HTTPException(status_code=404, detail="No results found")

        results = google_scraper.fetch_all_content(results)
        search_results = [SearchResult(**r) for r in results]

        return SearchResponse(
            success=True,
            query=request.query,
            gl=request.gl,
            lr=request.lr,
            cr=request.cr,
            results_count=len(search_results),
            results=search_results,
            execution_time=time.time() - start_time,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("startup")
async def startup_event():
    Path("output").mkdir(exist_ok=True)
    print("✅ API Ready!")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
