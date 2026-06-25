from services.document_reindex import build_reindex_guidance


def test_build_reindex_guidance_when_collection_ok():
    guidance = build_reindex_guidance(
        collection_status="ok",
        reindex_recommended=False,
        registered_document_count=3,
    )
    assert guidance["recommended"] is False


def test_build_reindex_guidance_when_collection_empty_with_documents():
    guidance = build_reindex_guidance(
        collection_status="empty",
        reindex_recommended=False,
        registered_document_count=2,
    )
    assert guidance["recommended"] is True
    assert "dry-run" in guidance["dry_run_command"]


def test_build_reindex_guidance_when_collection_mixed():
    guidance = build_reindex_guidance(
        collection_status="mixed",
        reindex_recommended=True,
        registered_document_count=0,
    )
    assert guidance["recommended"] is True
    assert guidance["run_command"].endswith("--run")
