"""Thin wrapper around the Plaid SDK.

Everything Plaid-specific lives here and returns plain dicts, so the sync
logic can be tested against a fake gateway without network access.
"""

from typing import Any, Protocol

import plaid
from plaid.api import plaid_api
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import (
    SandboxPublicTokenCreateRequest,
)
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from finance.config import Settings

# "First Platypus Bank" — Plaid's default sandbox institution.
DEFAULT_SANDBOX_INSTITUTION = "ins_109508"


class MutationDuringPagination(Exception):
    """Plaid data changed mid-pagination; restart from the original cursor."""


class PlaidGateway(Protocol):
    def sandbox_create_public_token(self, institution_id: str) -> str: ...

    def exchange_public_token(self, public_token: str) -> tuple[str, str]:
        """Return (access_token, item_id)."""
        ...

    def transactions_sync(self, access_token: str, cursor: str | None) -> dict[str, Any]: ...


class PlaidSDKGateway:
    def __init__(self, settings: Settings):
        if not settings.plaid_client_id or not settings.plaid_secret.get_secret_value():
            raise RuntimeError("PLAID_CLIENT_ID and PLAID_SECRET must be set (see .env.example).")
        host = {
            "sandbox": plaid.Environment.Sandbox,
            "production": plaid.Environment.Production,
        }[settings.plaid_env]
        configuration = plaid.Configuration(
            host=host,
            api_key={
                "clientId": settings.plaid_client_id,
                "secret": settings.plaid_secret.get_secret_value(),
            },
        )
        self._client = plaid_api.PlaidApi(plaid.ApiClient(configuration))
        self._env = settings.plaid_env

    def sandbox_create_public_token(self, institution_id: str) -> str:
        if self._env != "sandbox":
            raise RuntimeError("sandbox_create_public_token only works with PLAID_ENV=sandbox")
        request = SandboxPublicTokenCreateRequest(
            institution_id=institution_id,
            initial_products=[Products("transactions")],
        )
        return self._client.sandbox_public_token_create(request)["public_token"]

    def exchange_public_token(self, public_token: str) -> tuple[str, str]:
        response = self._client.item_public_token_exchange(ItemPublicTokenExchangeRequest(public_token=public_token))
        return response["access_token"], response["item_id"]

    def transactions_sync(self, access_token: str, cursor: str | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"access_token": access_token, "count": 500}
        if cursor:
            kwargs["cursor"] = cursor
        try:
            response = self._client.transactions_sync(TransactionsSyncRequest(**kwargs))
        except plaid.ApiException as exc:
            if "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION" in str(exc.body):
                raise MutationDuringPagination from exc
            raise
        return response.to_dict()
