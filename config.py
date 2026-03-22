"""Class to handle the configuration for Plaid2Firefly"""

import json
from pathlib import Path
from typing import Any

import logging

_LOGGER = logging.getLogger(__name__)


class Config:
    """Configuration class for Plaid2Firefly"""

    _TRUELAYER_CREDENTIAL_KEYS = {
        "truelayer_access_token": "access_token",
        "truelayer_refresh_token": "refresh_token",
        "truelayer_credentials_id": "credentials_id",
        "truelayer_expiration_date": "expiration_date",
    }

    def __init__(self) -> None:
        self.path = Path("data/config.json")
        if not self.path.exists():
            _LOGGER.info("Creating configuration file at %s", self.path)
            self.path.write_text("{}", encoding="utf-8")
        self._load()

    def _load(self) -> None:
        """Load the configuration from the JSON file"""
        with open(self.path, "r", encoding="utf-8") as f:
            self._config = json.load(f)
        self._migrate_truelayer_legacy_credentials()

    def _migrate_truelayer_legacy_credentials(self) -> None:
        """Move legacy top-level TrueLayer credential fields to nested object."""
        legacy_values = {
            key: self._config[key]
            for key in self._TRUELAYER_CREDENTIAL_KEYS
            if key in self._config
        }
        if not legacy_values:
            return

        credentials = self._config.get("truelayer_credentials", {})
        if not isinstance(credentials, dict):
            credentials = {}

        for legacy_key, credential_key in self._TRUELAYER_CREDENTIAL_KEYS.items():
            if legacy_key in legacy_values and credential_key not in credentials:
                credentials[credential_key] = legacy_values[legacy_key]

        self._config["truelayer_credentials"] = credentials

        for key in legacy_values:
            del self._config[key]

        self._save()

    def _get_truelayer_credentials(self) -> dict[str, Any]:
        """Return nested TrueLayer credentials object from config."""
        credentials = self._config.get("truelayer_credentials", {})
        if isinstance(credentials, dict):
            return credentials
        return {}

    def get(self, key: str, default=None) -> Any:
        """Get a configuration value, always using the latest available"""
        self._load()
        if key in self._TRUELAYER_CREDENTIAL_KEYS:
            credential_key = self._TRUELAYER_CREDENTIAL_KEYS[key]
            credentials = self._get_truelayer_credentials()
            if credential_key in credentials:
                return credentials[credential_key]
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value"""
        if key in self._TRUELAYER_CREDENTIAL_KEYS:
            credential_key = self._TRUELAYER_CREDENTIAL_KEYS[key]
            credentials = self._get_truelayer_credentials()
            credentials[credential_key] = value
            self._config["truelayer_credentials"] = credentials
            self._config.pop(key, None)
        else:
            self._config[key] = value
        _LOGGER.info("Saving configuration: %s to %s", key, value)
        self._save()

    def update(self, new_values: dict) -> None:
        """Update multiple configuration values"""
        for key, value in new_values.items():
            if key in self._TRUELAYER_CREDENTIAL_KEYS:
                credential_key = self._TRUELAYER_CREDENTIAL_KEYS[key]
                credentials = self._get_truelayer_credentials()
                credentials[credential_key] = value
                self._config["truelayer_credentials"] = credentials
                self._config.pop(key, None)
                continue
            self._config[key] = value
        self._save()

    def delete(self, key: str) -> None:
        """Delete a configuration value"""
        if key in self._TRUELAYER_CREDENTIAL_KEYS:
            credential_key = self._TRUELAYER_CREDENTIAL_KEYS[key]
            credentials = self._get_truelayer_credentials()
            if credential_key in credentials:
                del credentials[credential_key]
                self._config["truelayer_credentials"] = credentials
                self._save()
                return

        if key in self._config:
            del self._config[key]
            _LOGGER.info("Deleting configuration: %s", key)
            self._save()
        else:
            _LOGGER.warning("Key %s not found in configuration", key)

    def reset(self) -> None:
        """Reset the configuration"""
        _LOGGER.info("Resetting configuration")
        self._config = {}
        self._save()

    def _save(self) -> None:
        """Save the current configuration to the JSON file"""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=4)
