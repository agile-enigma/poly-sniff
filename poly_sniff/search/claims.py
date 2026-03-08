import re
import requests
from .config import RESEARCHTOOLS_URL


def _extract_claims(title: str, description: str) -> list[str]:
    """Extract claim-like statements from title and description."""
    claims = []

    if title:
        claims.append(title.strip())

    if description:
        sentences = re.split(r'[.!?]+', description)
        question_words = {'will', 'can', 'could', 'should', 'is', 'are', 'does', 'do', 'has', 'have', 'would'}
        action_words = {'win', 'lose', 'drop', 'rise', 'fall', 'pass', 'fail', 'approve', 'reject',
                        'resign', 'elect', 'ban', 'launch', 'reach', 'exceed', 'collapse', 'invade',
                        'sign', 'veto', 'default', 'announce', 'confirm', 'deny', 'acquire', 'merge'}

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue
            words = set(sentence.lower().split())
            if words & question_words or words & action_words:
                claims.append(sentence)

    return claims[:10]


def extract_from_url(url: str) -> dict:
    """Extract claims from a URL via the researchtoolspy analyze-url endpoint."""
    try:
        resp = requests.post(
            f"{RESEARCHTOOLS_URL}/api/tools/analyze-url",
            json={"url": url, "checkSEO": False},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        metadata = data.get('metadata', data)
        title = metadata.get('title', '')
        description = metadata.get('description', '')

        return {
            'title': title,
            'description': description,
            'claims': _extract_claims(title, description),
            'source_url': url,
        }
    except requests.RequestException as e:
        print(f"  Warning: Failed to analyze URL via researchtoolspy: {e}")
        print(f"  Falling back to URL as claim text.")
        return {
            'title': url,
            'description': '',
            'claims': [url],
            'source_url': url,
        }


def extract_from_text(claim_text: str) -> dict:
    """Wrap direct claim text into the standard claims format."""
    return {
        'title': claim_text,
        'description': '',
        'claims': [claim_text],
        'source_url': None,
    }
