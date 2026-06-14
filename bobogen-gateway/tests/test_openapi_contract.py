from fastapi.testclient import TestClient


def test_openapi_groups_import_friendly_gateway_routes():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    tag_names = [tag["name"] for tag in schema["tags"]]
    assert tag_names[:6] == [
        "00 Health",
        "01 Models",
        "02 Generate 新统一接口",
        "03 Provider 管理",
        "04 Legacy Provider 旧接口",
        "05 Stable Audio 3 调参",
    ]

    generate = schema["paths"]["/v1/generate"]["post"]
    assert generate["tags"] == ["02 Generate 新统一接口"]
    assert "audio/wav" in generate["responses"]["200"]["content"]
    examples = generate["requestBody"]["content"]["application/json"]["examples"]
    assert "stable-audio3" in examples
    assert "tts-json" in examples
    assert examples["stable-audio3"]["value"]["parameters"]["steps"] == 8


def test_openapi_keeps_legacy_provider_routes_visible():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/{provider_id}/v1/health" in paths
    assert "/{provider_id}/v1/voices" in paths
    assert "/{provider_id}/v1/synthesize" in paths
    assert "/{provider_id}/v1/clone" in paths
    assert paths["/{provider_id}/v1/synthesize"]["post"]["tags"] == ["04 Legacy Provider 旧接口"]
