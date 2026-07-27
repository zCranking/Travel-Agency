import voyageai

from core.config import settings


def chunk_text(text: str, max_chars: int = 800) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        if current_len + len(word) + 1 > max_chars and current:
            chunks.append(" ".join(current))
            current, current_len = [], 0
        current.append(word)
        current_len += len(word) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def embed(texts: list[str]) -> list[list[float]]:
    client = voyageai.Client(api_key=settings.voyage_api_key)
    result = client.embed(texts, model="voyage-3", input_type="document")
    return result.embeddings
