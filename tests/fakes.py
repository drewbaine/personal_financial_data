"""Fake Plaid gateway returning canned /transactions/sync pages. No network."""

from finance.plaid_client import MutationDuringPagination

ACCOUNT = {
    "account_id": "acc_checking",
    "name": "Plaid Checking",
    "official_name": "Plaid Gold Standard 0% Interest Checking",
    "mask": "0000",
    "type": "depository",
    "subtype": "checking",
    "balances": {"current": 110.0, "available": 100.0, "iso_currency_code": "USD"},
}


def txn(transaction_id, amount, date="2026-09-15", name="Coffee", category="FOOD_AND_DRINK", pending=False):
    return {
        "transaction_id": transaction_id,
        "account_id": ACCOUNT["account_id"],
        "amount": amount,
        "date": date,
        "authorized_date": None,
        "name": name,
        "merchant_name": name,
        "iso_currency_code": "USD",
        "pending": pending,
        "payment_channel": "in store",
        "personal_finance_category": {"primary": category, "detailed": f"{category}_OTHER"},
    }


class FakeGateway:
    def __init__(self, pages_by_cursor=None, mutate_once_at=None):
        # Maps incoming cursor (None for the first call) -> response page.
        self.pages_by_cursor = pages_by_cursor or {}
        self.mutate_once_at = mutate_once_at
        self.calls = []

    def sandbox_create_public_token(self, institution_id):
        return f"public-sandbox-{institution_id}"

    def exchange_public_token(self, public_token):
        return "access-sandbox-secret", "item_1"

    def transactions_sync(self, access_token, cursor):
        assert access_token == "access-sandbox-secret"
        self.calls.append(cursor)
        if cursor == self.mutate_once_at:
            self.mutate_once_at = object()  # only once
            raise MutationDuringPagination
        page = self.pages_by_cursor.get(cursor)
        if page is None:
            return {
                "added": [],
                "modified": [],
                "removed": [],
                "accounts": [ACCOUNT],
                "next_cursor": cursor,
                "has_more": False,
            }
        return {"accounts": [ACCOUNT], "modified": [], "removed": [], "added": [], **page}
