"""MCP server for Monarch Money integration."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from monarchmoney import MonarchMoney, RequireMFAException

from backend.services.monarch_auth import get_monarch_credentials

mcp = FastMCP("monarch")

# Resolve paths
# src/backend/mcp_servers/monarch_server.py -> ... -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOKEN_DIR = PROJECT_ROOT / "data" / "tokens"
SESSION_FILE = TOKEN_DIR / "monarch_session.pickle"

_monarch_client: Optional[MonarchMoney] = None
_client_lock = asyncio.Lock()


async def _get_client(force_refresh: bool = False) -> MonarchMoney:
    """Get an authenticated MonarchMoney client."""
    global _monarch_client
    if _monarch_client and not force_refresh:
        return _monarch_client

    async with _client_lock:
        if _monarch_client and not force_refresh:
            return _monarch_client

        creds = get_monarch_credentials()
        if not creds:
            raise ValueError("Monarch Money credentials not configured.")

        # Initialize with correct session file path
        mm = MonarchMoney(session_file=str(SESSION_FILE))

        # Try to load existing session only if not forcing refresh
        if not force_refresh and SESSION_FILE.exists():
            try:
                mm.load_session(str(SESSION_FILE))
            except Exception:
                pass

        # Check if logged in
        is_logged_in = False
        if not force_refresh:
            try:
                # Try a lightweight call to check if session is valid
                await mm.get_subscription_details()
                is_logged_in = True
            except Exception:
                is_logged_in = False

        if not is_logged_in:
            # Perform fresh login
            try:
                # Clean MFA secret if present
                mfa_secret = (
                    creds.mfa_secret.strip().replace(" ", "")
                    if creds.mfa_secret
                    else None
                )

                await mm.login(
                    email=creds.email,
                    password=creds.password,
                    mfa_secret_key=mfa_secret,
                    use_saved_session=False,  # Force fresh login
                )
            except RequireMFAException:
                raise ValueError(
                    "MFA required but no secret provided. Please update settings."
                )

            # Save session
            TOKEN_DIR.mkdir(parents=True, exist_ok=True)
            mm.save_session(str(SESSION_FILE))

        _monarch_client = mm
        return _monarch_client


@mcp.tool("get_monarch_accounts")
async def get_monarch_accounts() -> dict[str, Any]:
    """Retrieve all Monarch Money accounts with their balances."""
    try:
        mm = await _get_client()
        data = await mm.get_accounts()
        # The library returns a dict with 'accounts' key
        accounts = data.get("accounts", [])

        # Simplify output for LLM
        simplified = []
        for acc in accounts:
            simplified.append(
                {
                    "name": acc.get("displayName"),
                    "type": acc.get("type"),
                    "subtype": acc.get("subtype"),
                    "balance": acc.get("currentBalance"),
                    "currency": acc.get("currency"),
                    "updated_at": acc.get("updatedAt"),
                }
            )

        return {"accounts": simplified, "total_count": len(simplified)}
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_accounts()
                accounts = data.get("accounts", [])
                simplified = []
                for acc in accounts:
                    simplified.append(
                        {
                            "name": acc.get("displayName"),
                            "type": acc.get("type"),
                            "subtype": acc.get("subtype"),
                            "balance": acc.get("currentBalance"),
                            "currency": acc.get("currency"),
                            "updated_at": acc.get("updatedAt"),
                        }
                    )
                return {"accounts": simplified, "total_count": len(simplified)}
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_account_types")
async def get_monarch_account_types() -> dict[str, Any]:
    """List available account types and subtypes for manual accounts."""
    try:
        mm = await _get_client()
        data = await mm.get_account_type_options()
        options = data.get("accountTypeOptions", [])

        simplified = []
        seen_types = set()

        for opt in options:
            type_info = opt.get("type", {})
            type_name = type_info.get("name")

            if type_name in seen_types:
                continue
            seen_types.add(type_name)

            subtypes = [
                {"name": s.get("name"), "display": s.get("display")}
                for s in type_info.get("possibleSubtypes", [])
            ]

            simplified.append(
                {
                    "type": type_name,
                    "display": type_info.get("display"),
                    "group": type_info.get("group"),
                    "subtypes": subtypes,
                }
            )

        return {"account_types": simplified}
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_account_type_options()
                options = data.get("accountTypeOptions", [])

                simplified = []
                seen_types = set()

                for opt in options:
                    type_info = opt.get("type", {})
                    type_name = type_info.get("name")

                    if type_name in seen_types:
                        continue
                    seen_types.add(type_name)

                    subtypes = [
                        {"name": s.get("name"), "display": s.get("display")}
                        for s in type_info.get("possibleSubtypes", [])
                    ]

                    simplified.append(
                        {
                            "type": type_name,
                            "display": type_info.get("display"),
                            "group": type_info.get("group"),
                            "subtypes": subtypes,
                        }
                    )
                return {"account_types": simplified}
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("create_monarch_manual_account")
async def create_monarch_manual_account(
    name: str,
    type: str,
    subtype: str,
    balance: float = 0.0,
    include_in_net_worth: bool = True,
) -> dict[str, Any]:
    """
    Create a new manual account.
    Use get_monarch_account_types to find valid type/subtype values.
    """
    try:
        mm = await _get_client()
        data = await mm.create_manual_account(
            account_name=name,
            account_type=type,
            account_sub_type=subtype,
            account_balance=balance,
            is_in_net_worth=include_in_net_worth,
        )
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.create_manual_account(
                    account_name=name,
                    account_type=type,
                    account_sub_type=subtype,
                    account_balance=balance,
                    is_in_net_worth=include_in_net_worth,
                )
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("update_monarch_account")
async def update_monarch_account(
    account_id: str,
    name: Optional[str] = None,
    balance: Optional[float] = None,
    include_in_net_worth: Optional[bool] = None,
    hide_from_list: Optional[bool] = None,
    hide_transactions: Optional[bool] = None,
) -> dict[str, Any]:
    """
    Update an existing account.
    Only provide fields that need to be updated.
    """
    try:
        mm = await _get_client()
        data = await mm.update_account(
            account_id=account_id,
            account_name=name,
            account_balance=balance,
            include_in_net_worth=include_in_net_worth,
            hide_from_summary_list=hide_from_list,
            hide_transactions_from_reports=hide_transactions,
        )
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.update_account(
                    account_id=account_id,
                    account_name=name,
                    account_balance=balance,
                    include_in_net_worth=include_in_net_worth,
                    hide_from_summary_list=hide_from_list,
                    hide_transactions_from_reports=hide_transactions,
                )
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("delete_monarch_account")
async def delete_monarch_account(account_id: str) -> dict[str, Any]:
    """Delete an account."""
    try:
        mm = await _get_client()
        data = await mm.delete_account(account_id)
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.delete_account(account_id)
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_transactions")
async def get_monarch_transactions(
    limit: int = 10,
    search: Optional[str] = None,
    category: Optional[str] = None,
) -> dict[str, Any]:
    """
    Retrieve recent transactions from Monarch Money.

    Args:
        limit: Number of transactions to return (default 10)
        search: Optional search query string
        category: Optional category name to filter by
    """
    try:
        mm = await _get_client()
        # get_transactions arguments: limit, offset, search, category, etc.
        # Note: The library might have specific argument names.
        # Checking common usage: get_transactions(limit=..., search=...)

        data = await mm.get_transactions(limit=limit, search=search or "")
        all_txs = data.get("allTransactions", {}).get("results", [])

        # Filter by category if requested (client-side filtering if API doesn't support it easily)
        if category:
            all_txs = [
                t
                for t in all_txs
                if t.get("category", {}).get("name", "").lower() == category.lower()
            ]

        simplified = []
        for tx in all_txs:
            simplified.append(
                {
                    "date": tx.get("date"),
                    "merchant": tx.get("merchant", {}).get("name"),
                    "amount": tx.get("amount"),
                    "category": tx.get("category", {}).get("name"),
                    "notes": tx.get("notes"),
                    "pending": tx.get("pending"),
                }
            )

        return {"transactions": simplified, "count": len(simplified)}
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_transactions(limit=limit, search=search or "")
                all_txs = data.get("allTransactions", {}).get("results", [])
                if category:
                    all_txs = [
                        t
                        for t in all_txs
                        if t.get("category", {}).get("name", "").lower()
                        == category.lower()
                    ]
                simplified = []
                for tx in all_txs:
                    simplified.append(
                        {
                            "date": tx.get("date"),
                            "merchant": tx.get("merchant", {}).get("name"),
                            "amount": tx.get("amount"),
                            "category": tx.get("category", {}).get("name"),
                            "notes": tx.get("notes"),
                            "pending": tx.get("pending"),
                        }
                    )
                return {"transactions": simplified, "count": len(simplified)}
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_budgets")
async def get_monarch_budgets() -> dict[str, Any]:
    """Retrieve budget status and remaining amounts."""
    try:
        mm = await _get_client()
        # get_budgets returns budget data
        data = await mm.get_budgets()
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_budgets()
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("refresh_monarch_data")
async def refresh_monarch_data() -> dict[str, Any]:
    """Trigger a refresh of data from connected institutions."""
    try:
        mm = await _get_client()
        # request_accounts_refresh requires account_ids
        accounts_data = await mm.get_accounts()
        account_ids = [acc["id"] for acc in accounts_data.get("accounts", [])]

        if account_ids:
            await mm.request_accounts_refresh(account_ids)
            return {"status": "Refresh requested", "account_count": len(account_ids)}
        else:
            return {"status": "No accounts found to refresh"}
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                accounts_data = await mm.get_accounts()
                account_ids = [acc["id"] for acc in accounts_data.get("accounts", [])]
                if account_ids:
                    await mm.request_accounts_refresh(account_ids)
                    return {
                        "status": "Refresh requested",
                        "account_count": len(account_ids),
                    }
                else:
                    return {"status": "No accounts found to refresh"}
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_cashflow")
async def get_monarch_cashflow(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    """
    Analyze cashflow (income vs expenses).
    Dates should be in YYYY-MM-DD format.
    """
    try:
        mm = await _get_client()
        data = await mm.get_cashflow(start_date=start_date, end_date=end_date)

        # Simplify
        # The API returns 'summary' as a list of AggregateData objects
        summary_list = data.get("summary", [])
        summary_data = {}
        if summary_list and isinstance(summary_list, list) and len(summary_list) > 0:
            summary_data = summary_list[0].get("summary", {})

        return {
            "income": summary_data.get("sumIncome"),
            "expenses": summary_data.get("sumExpense"),
            "savings": summary_data.get("savings"),
            "savings_rate": summary_data.get("savingsRate"),
        }
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_cashflow(start_date=start_date, end_date=end_date)

                summary_list = data.get("summary", [])
                summary_data = {}
                if (
                    summary_list
                    and isinstance(summary_list, list)
                    and len(summary_list) > 0
                ):
                    summary_data = summary_list[0].get("summary", {})

                return {
                    "income": summary_data.get("sumIncome"),
                    "expenses": summary_data.get("sumExpense"),
                    "savings": summary_data.get("savings"),
                    "savings_rate": summary_data.get("savingsRate"),
                }
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_holdings")
async def get_monarch_holdings(account_id: str) -> dict[str, Any]:
    """Retrieve investment holdings for a specific account."""
    try:
        mm = await _get_client()
        # Library expects int for account_id
        data = await mm.get_account_holdings(int(account_id))
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_account_holdings(int(account_id))
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_net_worth_history")
async def get_monarch_net_worth_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    account_type: Optional[str] = None,
) -> dict[str, Any]:
    """
    Retrieve net worth history (aggregate snapshots).
    Dates should be in YYYY-MM-DD format.
    """
    try:
        mm = await _get_client()

        # Validate date format if provided, but pass strings to the library
        # The library expects strings for the GraphQL variables
        if start_date:
            datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            datetime.strptime(end_date, "%Y-%m-%d")

        data = await mm.get_aggregate_snapshots(
            start_date=start_date,  # type: ignore
            end_date=end_date,  # type: ignore
            account_type=account_type,
        )
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)

                if start_date:
                    datetime.strptime(start_date, "%Y-%m-%d")
                if end_date:
                    datetime.strptime(end_date, "%Y-%m-%d")

                data = await mm.get_aggregate_snapshots(
                    start_date=start_date,  # type: ignore
                    end_date=end_date,  # type: ignore
                    account_type=account_type,
                )
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_recurring_transactions")
async def get_monarch_recurring_transactions(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    """
    Retrieve upcoming recurring transactions (bills, subscriptions).
    Dates should be in YYYY-MM-DD format.
    """
    try:
        mm = await _get_client()
        data = await mm.get_recurring_transactions(
            start_date=start_date, end_date=end_date
        )
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_recurring_transactions(
                    start_date=start_date, end_date=end_date
                )
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_spending_summary")
async def get_monarch_spending_summary() -> dict[str, Any]:
    """Retrieve summary of transaction aggregates (income, expense, savings)."""
    try:
        mm = await _get_client()
        data = await mm.get_transactions_summary()

        # Simplify
        aggregates = data.get("aggregates", [])
        summary_data = {}
        if aggregates and isinstance(aggregates, list) and len(aggregates) > 0:
            summary_data = aggregates[0].get("summary", {})

        return summary_data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_transactions_summary()

                aggregates = data.get("aggregates", [])
                summary_data = {}
                if aggregates and isinstance(aggregates, list) and len(aggregates) > 0:
                    summary_data = aggregates[0].get("summary", {})

                return summary_data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_categories")
async def get_monarch_categories() -> dict[str, Any]:
    """List all transaction categories."""
    try:
        mm = await _get_client()
        data = await mm.get_transaction_categories()
        # Simplify output
        categories = data.get("categories", [])
        simplified = [
            {
                "name": c.get("name"),
                "group": c.get("group", {}).get("name"),
                "type": c.get("group", {}).get("type"),
            }
            for c in categories
        ]
        return {"categories": simplified, "count": len(simplified)}
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_transaction_categories()
                categories = data.get("categories", [])
                simplified = [
                    {
                        "name": c.get("name"),
                        "group": c.get("group", {}).get("name"),
                        "type": c.get("group", {}).get("type"),
                    }
                    for c in categories
                ]
                return {"categories": simplified, "count": len(simplified)}
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_tags")
async def get_monarch_tags() -> dict[str, Any]:
    """List all transaction tags."""
    try:
        mm = await _get_client()
        data = await mm.get_transaction_tags()
        tags = data.get("householdTransactionTags", [])
        return {"tags": tags, "count": len(tags)}
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_transaction_tags()
                tags = data.get("householdTransactionTags", [])
                return {"tags": tags, "count": len(tags)}
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_account_history")
async def get_monarch_account_history(account_id: str) -> dict[str, Any]:
    """Retrieve historical balances for a specific account."""
    try:
        mm = await _get_client()
        # Library expects int for account_id in get_account_history
        data = await mm.get_account_history(int(account_id))
        # data is a list of snapshots
        return {"history": data, "count": len(data) if isinstance(data, list) else 0}
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_account_history(int(account_id))
                return {
                    "history": data,
                    "count": len(data) if isinstance(data, list) else 0,
                }
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_institutions")
async def get_monarch_institutions() -> dict[str, Any]:
    """List all connected financial institutions."""
    try:
        mm = await _get_client()
        data = await mm.get_institutions()

        # The API returns 'credentials' which contain institution info
        credentials = data.get("credentials", [])
        simplified = []
        for cred in credentials:
            inst = cred.get("institution", {})
            simplified.append(
                {
                    "id": inst.get("id"),
                    "name": inst.get("name"),
                    "status": inst.get("status"),
                    "updated_at": cred.get("displayLastUpdatedAt"),
                    "data_provider": cred.get("dataProvider"),
                }
            )
        return {"institutions": simplified, "count": len(simplified)}
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_institutions()

                credentials = data.get("credentials", [])
                simplified = []
                for cred in credentials:
                    inst = cred.get("institution", {})
                    simplified.append(
                        {
                            "id": inst.get("id"),
                            "name": inst.get("name"),
                            "status": inst.get("status"),
                            "updated_at": cred.get("displayLastUpdatedAt"),
                            "data_provider": cred.get("dataProvider"),
                        }
                    )
                return {"institutions": simplified, "count": len(simplified)}
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("create_monarch_transaction")
async def create_monarch_transaction(
    date: str,
    account_id: str,
    amount: float,
    merchant_name: str,
    category_id: str,
    notes: str = "",
) -> dict[str, Any]:
    """
    Create a new manual transaction.

    Args:
        date: Transaction date in YYYY-MM-DD format
        account_id: ID of the account
        amount: Transaction amount
        merchant_name: Name of the merchant
        category_id: ID of the category
        notes: Optional notes
    """
    try:
        mm = await _get_client()
        # Validate date format
        datetime.strptime(date, "%Y-%m-%d")

        data = await mm.create_transaction(
            date=date,
            account_id=account_id,
            amount=amount,
            merchant_name=merchant_name,
            category_id=category_id,
            notes=notes,
        )
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                datetime.strptime(date, "%Y-%m-%d")

                data = await mm.create_transaction(
                    date=date,
                    account_id=account_id,
                    amount=amount,
                    merchant_name=merchant_name,
                    category_id=category_id,
                    notes=notes,
                )
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("update_monarch_transaction")
async def update_monarch_transaction(
    transaction_id: str,
    notes: Optional[str] = None,
    category_id: Optional[str] = None,
    merchant_name: Optional[str] = None,
    amount: Optional[float] = None,
    date: Optional[str] = None,
) -> dict[str, Any]:
    """
    Update an existing transaction.
    Only provide fields that need to be updated.
    """
    try:
        mm = await _get_client()

        if date:
            datetime.strptime(date, "%Y-%m-%d")

        data = await mm.update_transaction(
            transaction_id=transaction_id,
            notes=notes,
            category_id=category_id,
            merchant_name=merchant_name,
            amount=amount,
            date=date,
        )
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)

                if date:
                    datetime.strptime(date, "%Y-%m-%d")

                data = await mm.update_transaction(
                    transaction_id=transaction_id,
                    notes=notes,
                    category_id=category_id,
                    merchant_name=merchant_name,
                    amount=amount,
                    date=date,
                )
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("delete_monarch_transaction")
async def delete_monarch_transaction(transaction_id: str) -> dict[str, Any]:
    """Delete a transaction."""
    try:
        mm = await _get_client()
        success = await mm.delete_transaction(transaction_id)
        return {"success": success}
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                success = await mm.delete_transaction(transaction_id)
                return {"success": success}
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_transaction_details")
async def get_monarch_transaction_details(transaction_id: str) -> dict[str, Any]:
    """Get full details for a specific transaction."""
    try:
        mm = await _get_client()
        data = await mm.get_transaction_details(transaction_id)
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_transaction_details(transaction_id)
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("set_monarch_budget_amount")
async def set_monarch_budget_amount(
    amount: float,
    category_id: str,
    start_date: str,
    apply_to_future: bool = False,
) -> dict[str, Any]:
    """
    Set budget amount for a category.

    Args:
        amount: Budget amount
        category_id: ID of the category
        start_date: Start date in YYYY-MM-DD format (usually first of month)
        apply_to_future: Whether to apply to future months
    """
    try:
        mm = await _get_client()
        # Validate date
        datetime.strptime(start_date, "%Y-%m-%d")

        data = await mm.set_budget_amount(
            amount=amount,
            category_id=category_id,
            start_date=start_date,
            apply_to_future=apply_to_future,
        )
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                datetime.strptime(start_date, "%Y-%m-%d")

                data = await mm.set_budget_amount(
                    amount=amount,
                    category_id=category_id,
                    start_date=start_date,
                    apply_to_future=apply_to_future,
                )
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("set_monarch_transaction_tags")
async def set_monarch_transaction_tags(
    transaction_id: str,
    tag_ids: list[str],
) -> dict[str, Any]:
    """Set tags for a transaction (overwrites existing tags)."""
    try:
        mm = await _get_client()
        data = await mm.set_transaction_tags(transaction_id, tag_ids)
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.set_transaction_tags(transaction_id, tag_ids)
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("create_monarch_tag")
async def create_monarch_tag(name: str, color: str) -> dict[str, Any]:
    """
    Create a new transaction tag.
    Color should be a hex code (e.g. #FF0000).
    """
    try:
        mm = await _get_client()
        data = await mm.create_transaction_tag(name, color)
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.create_transaction_tag(name, color)
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_category_groups")
async def get_monarch_category_groups() -> dict[str, Any]:
    """List all transaction category groups."""
    try:
        mm = await _get_client()
        data = await mm.get_transaction_category_groups()
        groups = data.get("categoryGroups", [])
        simplified = [
            {
                "id": g.get("id"),
                "name": g.get("name"),
                "type": g.get("type"),
            }
            for g in groups
        ]
        return {"category_groups": simplified, "count": len(simplified)}
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_transaction_category_groups()
                groups = data.get("categoryGroups", [])
                simplified = [
                    {
                        "id": g.get("id"),
                        "name": g.get("name"),
                        "type": g.get("type"),
                    }
                    for g in groups
                ]
                return {"category_groups": simplified, "count": len(simplified)}
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("create_monarch_category")
async def create_monarch_category(
    name: str,
    group_id: str,
    icon: str = "❓",
) -> dict[str, Any]:
    """
    Create a new transaction category.

    Args:
        name: Category name
        group_id: ID of the category group (use get_monarch_category_groups to find one)
        icon: Emoji icon for the category
    """
    try:
        mm = await _get_client()
        data = await mm.create_transaction_category(
            group_id=group_id, transaction_category_name=name, icon=icon
        )
        return data
    except Exception as e:
        error_msg = str(e)
        if "createCategory" in error_msg and "Something went wrong" in error_msg:
            return {
                "error": f"Failed to create category. Please verify the group_id '{group_id}' is valid using get_monarch_category_groups. Original error: {error_msg}"
            }

        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.create_transaction_category(
                    group_id=group_id, transaction_category_name=name, icon=icon
                )
                return data
            except Exception as retry_e:
                retry_error_msg = str(retry_e)
                if (
                    "createCategory" in retry_error_msg
                    and "Something went wrong" in retry_error_msg
                ):
                    return {
                        "error": f"Failed to create category. Please verify the group_id '{group_id}' is valid using get_monarch_category_groups. Original error: {retry_error_msg}"
                    }
                return {"error": f"Retry failed: {retry_error_msg}"}
        return {"error": error_msg}


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
