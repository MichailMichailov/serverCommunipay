import os

def env_bool(name: str, default: bool=False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1","true","yes","y","on"}

def get_client_ip(request) -> str | None:
    return request.META.get("REMOTE_ADDR")
