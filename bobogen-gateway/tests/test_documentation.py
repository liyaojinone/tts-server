from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_docs_explain_openapi_import_and_dynamic_parameters():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    api_reference = (ROOT / "docs" / "services" / "bobogen-api-reference.md").read_text(encoding="utf-8")
    docs = readme + "\n" + api_reference

    assert "http://127.0.0.1:6006/openapi.json" in docs
    assert "Postman" in docs
    assert "Apifox" in docs
    assert "/v1/models/{model_id}" in docs
    assert "Send and Download" in docs or "保存响应" in docs
