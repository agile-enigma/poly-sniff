import requests
from .config import RESEARCHTOOLS_URL


def _keyword_fallback(claim: str, candidates: list[dict]) -> list[dict]:
    """Simple keyword matching fallback when LLM ranking is unavailable."""
    claim_words = set(claim.lower().split())
    claim_words -= {'the', 'a', 'an', 'is', 'are', 'will', 'be', 'to', 'of', 'in', 'for',
                    'on', 'with', 'at', 'by', 'from', 'that', 'this', 'and', 'or', 'but'}

    results = []
    for c in candidates:
        text = f"{c.get('title', '')} {c.get('description', '')}".lower()
        text_words = set(text.split())
        overlap = len(claim_words & text_words)
        score = min(100, int((overlap / max(len(claim_words), 1)) * 100))
        results.append({
            'slug': c['slug'],
            'title': c.get('title', ''),
            'relevance': score,
            'reasoning': f"Keyword match: {overlap}/{len(claim_words)} terms",
        })

    results.sort(key=lambda x: x['relevance'], reverse=True)
    return results


def rank_candidates(claim: str, candidates: list[dict], researchtools_url: str = None) -> list[dict]:
    """Rank candidate markets by relevance to the claim using LLM re-ranking."""
    if not candidates:
        return []

    url = researchtools_url or RESEARCHTOOLS_URL

    payload = {
        'claim': claim,
        'candidates': [
            {
                'slug': c['slug'],
                'title': c.get('title', ''),
                'description': c.get('description', ''),
            }
            for c in candidates
        ],
    }

    try:
        resp = requests.post(
            f"{url}/api/tools/claim-match",
            json=payload,
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get('results', [])
        results.sort(key=lambda x: x.get('relevance', 0), reverse=True)
        return results

    except requests.RequestException as e:
        print(f"  Warning: LLM ranking unavailable ({e}), using keyword fallback.")
        return _keyword_fallback(claim, candidates)
