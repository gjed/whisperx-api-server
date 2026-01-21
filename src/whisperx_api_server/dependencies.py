import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from whisperx_api_server.config import Config


@lru_cache
def get_config() -> Config:
    return Config()


ConfigDependency = Annotated[Config, Depends(get_config)]

security = HTTPBearer()

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_api_keys_cached(file_path: str, file_mtime: float) -> dict[str, str]:
    """Load and cache API keys from file. Cache is invalidated when file modification time changes."""
    with open(file_path) as f:
        return json.load(f)


def _get_api_keys(api_keys_file: str | None) -> dict[str, str]:
    """Get API keys with caching based on file modification time."""
    if not api_keys_file:
        return {}
    try:
        mtime = Path(api_keys_file).stat().st_mtime
        return _load_api_keys_cached(api_keys_file, mtime)
    except FileNotFoundError:
        logger.error(f"API keys file not found: {api_keys_file}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in API keys file: {e}")
        return {}


async def verify_api_key(
    config: ConfigDependency, credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> None:
    api_keys = _get_api_keys(config.api_keys_file)

    client_name = api_keys.get(credentials.credentials)

    if credentials.credentials != config.api_key and client_name is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key")

    if client_name:
        logger.info(f"Authorized request from client: '{client_name}'")
    else:
        logger.info("Authorized request using the default API key")


ApiKeyDependency = Depends(verify_api_key)
