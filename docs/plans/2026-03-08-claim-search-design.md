# Claim-to-Market Search Design

## Overview

Add search capability to poly-sniff that takes claims (from URLs via researchtools.net or direct text) and finds matching Polymarket prediction markets using keyword search + LLM semantic re-ranking.

## Architecture

```
User Input (--url or --claim)
  → Claim Extraction (researchtoolspy API or local parsing)
  → Keyword Query Generation (Python)
  → Polymarket Gamma API search (candidate markets)
  → LLM Re-ranking (researchtoolspy /api/tools/claim-match)
  → Ranked results with relevance scores
```

## Components

### poly-sniff (Python CLI)

New `search/` package:

- `search/claims.py` — Claim extraction. URL mode calls researchtoolspy `/api/tools/analyze-url`. Text mode parses claim directly.
- `search/polymarket.py` — Searches Polymarket Gamma API for candidate markets matching extracted keywords.
- `search/ranker.py` — Sends claim + candidates to researchtoolspy `/api/tools/claim-match` for LLM scoring.
- `search/config.py` — API URLs, match thresholds, defaults.

CLI additions to `__main__.py`:
- `search` subcommand with `--claim` and `--url` flags
- `--analyze` flag to immediately run insider detection on top match
- `--top-n` to control how many results to display (default: 5)
- `--min-relevance` threshold (default: 50)

### researchtoolspy (Cloudflare Pages)

New endpoint: `POST /api/tools/claim-match`

Request:
```json
{
  "claim": "Will Biden drop out of the 2024 race?",
  "candidates": [
    { "slug": "will-biden-drop-out", "title": "Will Biden drop out?", "description": "..." },
    { "slug": "biden-nominee-2024", "title": "Will Biden be the Democratic nominee?", "description": "..." }
  ]
}
```

Response:
```json
{
  "results": [
    { "slug": "will-biden-drop-out", "relevance": 95, "reasoning": "Direct match..." },
    { "slug": "biden-nominee-2024", "relevance": 72, "reasoning": "Related but indirect..." }
  ]
}
```

Uses existing OPENAI_API_KEY. Model: gpt-4o-mini for cost efficiency.

## Secrets

- poly-sniff `.env`: `RESEARCHTOOLS_URL` (production or localhost)
- researchtoolspy: Already has `OPENAI_API_KEY`
- GitHub secrets: `RESEARCHTOOLS_URL` for CI

## Dependencies

New Python dependency: `python-dotenv` (for .env loading)
