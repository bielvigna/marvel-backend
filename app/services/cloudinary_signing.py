import hashlib


def create_upload_signature(timestamp: int, api_secret: str, public_id: str | None = None) -> str:
    """Sign only the timestamp and optional fixed avatar destination for an upload."""
    parameters: dict[str, str | int] = {"timestamp": timestamp}
    if public_id is not None:
        parameters.update({"overwrite": "true", "public_id": public_id})
    serialized = "&".join(f"{key}={parameters[key]}" for key in sorted(parameters))
    payload = f"{serialized}{api_secret}".encode()
    return hashlib.sha1(payload).hexdigest()
