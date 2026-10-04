import pytest

from app.core.config import Settings
from app.services.cloudinary_signing import create_upload_signature


def test_signed_upload_timestamp_matches_cloudinary_sha1_example():
    assert create_upload_signature(1315060510, "abcd") == "a21ad0f63beb4de2e5575204b79ab90bffb02c10"


@pytest.mark.asyncio
async def test_avatar_signature_returns_timestamp_and_signature(client, app, monkeypatch):
    from app.api.routes import profiles

    app.state.settings = Settings(cloudinary_api_secret="abcd")
    monkeypatch.setattr(profiles.time, "time", lambda: 1315060510)
    response = await client.post(
        "/v1/profile/avatar-signature", headers={"Authorization": "Bearer valid-token"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "timestamp": 1315060510,
        "signature": "1a53a2765a805e98d284bb62308b212d0888d0fe",
        "public_id": (
            "marvel_battlefield/avatars/"
            "151e56acf6e975470b5a370a1ebbc6f79c48d2a61e7a7102993633ca600cfabb"
        ),
        "overwrite": True,
    }


@pytest.mark.asyncio
async def test_avatar_signature_requires_backend_api_secret(client):
    response = await client.post(
        "/v1/profile/avatar-signature", headers={"Authorization": "Bearer valid-token"}
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "cloudinary_unconfigured"
