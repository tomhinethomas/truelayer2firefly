"""Tests for importer mapping and account matching behaviour."""

from __future__ import annotations

from typing import Any

import importer2firefly
from importer2firefly import Import2Firefly


class DummyResponse:
    """Simple response double that mimics the few httpx attributes we use."""

    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = ""

    def json(self) -> dict[str, Any]:
        """Return JSON payload."""
        return self._payload


class DummyTrueLayerClient:
    """TrueLayer client double for importer tests."""

    def __init__(
        self,
        sources: list[dict[str, Any]],
        transactions_by_account_id: dict[str, list[dict[str, Any]]],
    ) -> None:
        self._sources = sources
        self._transactions_by_account_id = transactions_by_account_id

    async def get_accounts_and_cards(self) -> list[dict[str, Any]]:
        return self._sources

    async def get_transactions(self, account_id: str) -> DummyResponse:
        return DummyResponse(200, {"results": self._transactions_by_account_id[account_id]})

    async def get_card_transactions(self, card_id: str) -> DummyResponse:
        return DummyResponse(200, {"results": self._transactions_by_account_id[card_id]})


class DummyFireflyClient:
    """Firefly client double for importer tests."""

    def __init__(self, accounts: list[dict[str, Any]]) -> None:
        self._accounts = accounts
        self.created_transactions: list[dict[str, Any]] = []

    async def get_account_paginated(self) -> list[dict[str, Any]]:
        return self._accounts

    async def create_transaction(self, transaction_data: dict[str, Any]) -> DummyResponse:
        self.created_transactions.append(transaction_data)
        return DummyResponse(200, {"data": {"id": "tx-1"}})

    async def create_account(self, account_data: dict[str, Any]) -> DummyResponse:
        return DummyResponse(200, {"data": {"id": "acct-1", "attributes": account_data}})


async def _collect_events(importer: Import2Firefly) -> list[Any]:
    events: list[Any] = []
    async for event in importer.start_import():
        events.append(event)
    return events


async def test_import_maps_merchant_category_tags_and_note(monkeypatch) -> None:
    """Importer maps merchant, classifications, and normalized provider id."""
    monkeypatch.setattr(
        importer2firefly,
        "get_truelayer_connections",
        lambda _config: [{"credentials_id": "cred-1"}],
    )
    monkeypatch.setattr(importer2firefly, "activate_truelayer_connection", lambda *_: None)
    monkeypatch.setattr(importer2firefly, "upsert_active_truelayer_connection", lambda *_: None)

    importer = Import2Firefly()
    importer._truelayer_client = DummyTrueLayerClient(
        sources=[
            {
                "kind": "account",
                "account_id": "acc-1",
                "display_name": "Some Account",
                "account_number": {"number": "12345678"},
            }
        ],
        transactions_by_account_id={
            "acc-1": [
                {
                    "transaction_id": "txn-1",
                    "timestamp": "2026-01-01T10:00:00Z",
                    "description": "Coffee",
                    "merchant_name": "Coffee Corner",
                    "transaction_type": "DEBIT",
                    "amount": -3.25,
                    "transaction_classification": ["food", "coffee"],
                    "normalised_provider_transaction_id": "np-123",
                    "meta": {},
                }
            ]
        },
    )
    importer._firefly_client = DummyFireflyClient(
        accounts=[
            {
                "id": "ff-asset-1",
                "attributes": {
                    "name": "Main Firefly Asset",
                    "type": "asset",
                    "account_role": "sharedAsset",
                    "account_number": "12 345678",
                    "iban": None,
                },
            }
        ]
    )

    events = await _collect_events(importer)

    created = importer._firefly_client.created_transactions
    assert len(created) == 1

    split = created[0]["transactions"][0]
    assert split["destination_name"] == "Coffee Corner"
    assert split["category_name"] == "food"
    assert split["tags"] == ["food", "coffee"]
    assert split["notes"] == "normalised_provider_transaction_id: np-123"

    assert all("Transaction has no IBAN" not in str(event) for event in events)
    assert all("not a default asset" not in str(event) for event in events)


async def test_import_matches_account_by_name(monkeypatch) -> None:
    """Importer can match TrueLayer account to Firefly account by account name."""
    monkeypatch.setattr(
        importer2firefly,
        "get_truelayer_connections",
        lambda _config: [{"credentials_id": "cred-1"}],
    )
    monkeypatch.setattr(importer2firefly, "activate_truelayer_connection", lambda *_: None)
    monkeypatch.setattr(importer2firefly, "upsert_active_truelayer_connection", lambda *_: None)

    importer = Import2Firefly()
    importer._truelayer_client = DummyTrueLayerClient(
        sources=[
            {
                "kind": "account",
                "account_id": "acc-2",
                "display_name": "Everyday Account",
                "account_number": {},
            }
        ],
        transactions_by_account_id={
            "acc-2": [
                {
                    "transaction_id": "txn-2",
                    "timestamp": "2026-01-02T10:00:00Z",
                    "description": "Groceries",
                    "transaction_type": "DEBIT",
                    "amount": -12.40,
                    "transaction_classification": [],
                    "meta": {},
                }
            ]
        },
    )
    importer._firefly_client = DummyFireflyClient(
        accounts=[
            {
                "id": "ff-asset-2",
                "attributes": {
                    "name": "Everyday Account",
                    "type": "asset",
                    "account_role": "anything",
                    "account_number": None,
                    "iban": None,
                },
            }
        ]
    )

    await _collect_events(importer)

    created = importer._firefly_client.created_transactions
    assert len(created) == 1
    split = created[0]["transactions"][0]
    assert split["account_id"] == "ff-asset-2"
    assert split["source_id"] == "ff-asset-2"
