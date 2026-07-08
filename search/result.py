"""
search/result.py — Typed SearchResult dataclass.

Search tools currently return plain dicts. This dataclass provides a typed
alternative with safe defaults. New search tools should return SearchResult
objects and call .to_dict() when passing results to existing pipeline code.
Existing tools will be migrated incrementally.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchResult:
    source: str
    title: str
    snippet: str = ""
    url: str = ""
    pmid: str = ""
    doi: str = ""
    nct_id: str = ""
    year: str = ""

    def to_dict(self) -> dict:
        """Backward-compatible dict conversion. Omits empty fields."""
        return {k: v for k, v in self.__dict__.items() if v}

    @classmethod
    def from_dict(cls, d: dict) -> "SearchResult":
        return cls(
            source=d.get("source", "Unknown"),
            title=d.get("title", ""),
            snippet=d.get("snippet", ""),
            url=d.get("url", ""),
            pmid=d.get("pmid", ""),
            doi=d.get("doi", ""),
            nct_id=d.get("nct_id", ""),
            year=d.get("year", ""),
        )
