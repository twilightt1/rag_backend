import pytest
from app.utils.chunker import (
    _recursive_split,
    _split_by_headings,
    _split_parents,
    build_parent_child_chunks,
    extract_text,
    PARENT_SIZE,
    PARENT_OVERLAP,
    CHILD_SIZE,
    CHILD_OVERLAP,
)

@pytest.mark.unit
def test_recursive_split():
    text = "a" * 1000
    chunks = _recursive_split(text, size=400, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 400 for c in chunks)
    assert chunks[0][-50:] == chunks[1][:50]  # Check overlap roughly (if exact chars split)

@pytest.mark.unit
def test_split_by_headings():
    text = """# Title
Some intro text.
## Section 1
Content 1.
### Subsection 1.1
Content 1.1
## Section 2
Content 2."""
    chunks = _split_by_headings(text)
    assert len(chunks) == 3
    assert chunks[0].startswith("## Section 1")
    assert chunks[1].startswith("### Subsection 1.1")
    assert chunks[2].startswith("## Section 2")

@pytest.mark.unit
def test_split_parents_with_headings():
    text = """## Section 1\n""" + "a" * (PARENT_SIZE * 2 + 100) + """\n## Section 2\n""" + "b" * 100
    chunks = _split_parents(text)
    # Section 1 is too large, it should be recursively split
    assert len(chunks) >= 3
    assert any("b" * 100 in c for c in chunks)

@pytest.mark.unit
def test_build_parent_child_chunks():
    text = "This is a simple document text to test the parent-child chunking strategy. " * 100
    document_id = "doc_123"
    conversation_id = "conv_456"
    filename = "test.txt"

    parents, children = build_parent_child_chunks(text, document_id, conversation_id, filename)

    assert len(parents) > 0
    assert len(children) > 0

    # Check parent metadata
    assert parents[0].metadata["document_id"] == document_id
    assert parents[0].metadata["chunk_type"] == "parent"

    # Check child relationships
    assert children[0].parent_id == parents[0].id
    assert children[0].metadata["chunk_type"] == "child"
    assert children[0].metadata["parent_id"] == parents[0].id

    # Ensure all children map to a valid parent
    parent_ids = {p.id for p in parents}
    for child in children:
        assert child.parent_id in parent_ids

@pytest.mark.unit
def test_extract_text_plain():
    text = b"Hello world"
    extracted = extract_text(text, "text/plain")
    assert extracted == "Hello world"

@pytest.mark.unit
def test_extract_text_fallback():
    text = "Héllö".encode("latin-1")
    extracted = extract_text(text, None)
    assert extracted == "Héllö"
