from policy.embeddings import chunk_text


def test_chunk_text_splits_long_text():
    text = "sentence. " * 300  # ~3000 chars
    chunks = chunk_text(text, max_chars=800)
    assert len(chunks) > 1
    assert all(len(c) <= 800 for c in chunks)


def test_chunk_text_keeps_short_text_whole():
    chunks = chunk_text("short policy note.", max_chars=800)
    assert chunks == ["short policy note."]
