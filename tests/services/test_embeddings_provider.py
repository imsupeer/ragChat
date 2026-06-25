from services.embeddings_provider import IMPLEMENTED_EMBEDDINGS_PROVIDERS


def test_implemented_embeddings_providers():
    assert IMPLEMENTED_EMBEDDINGS_PROVIDERS == frozenset(
        {"ollama", "local_hash", "sentence_transformers"}
    )
