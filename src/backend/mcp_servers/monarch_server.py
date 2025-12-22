"""MCP server for Monarch Money integration."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastmcp import FastMCP
from monarchmoney import MonarchMoney, RequireMFAException

from backend.config import get_settings
from backend.repository import ChatRepository
from backend.services.monarch_auth import get_monarch_credentials


class MonarchAuthError(Exception):
    """Raised when authentication with Monarch Money fails."""

    pass


class MonarchAPIError(Exception):
    """Raised when Monarch Money API calls fail."""

    pass


# Default port for HTTP transport
DEFAULT_HTTP_PORT = 9008

mcp = FastMCP("monarch")


def _project_root() -> Path:
    """Get project root directory."""
    module_path = Path(__file__).resolve()
    # src/backend/mcp_servers -> project root is three parents up
    return module_path.parents[3]


def _resolve_under(base: Path, p: Path) -> Path:
    """Resolve path relative to base, ensuring it doesn't escape."""
    if p.is_absolute():
        return p.resolve()
    resolved = (base / p).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError(f"Configured path {resolved} escapes project root {base}")
    return resolved


def _resolve_session_file() -> Path:
    """Resolve session file path using settings."""
    base = _project_root()
    token_dir = base / "data" / "tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    return token_dir / "monarch_session.pickle"


def _resolve_chat_db_path() -> Path:
    """Resolve chat database path from settings."""
    settings = get_settings()
    return _resolve_under(_project_root(), settings.chat_database_path)


_monarch_client: Optional[MonarchMoney] = None
_client_lock = asyncio.Lock()
_repository: Optional[ChatRepository] = None
_repository_lock = asyncio.Lock()
_repository: Optional[ChatRepository] = None
_repository_lock = asyncio.Lock()


async def _get_repository() -> ChatRepository:
    """Get or initialize the chat repository."""
    global _repository
    if _repository is not None:
        return _repository
    async with _repository_lock:
        if _repository is None:
            repo = ChatRepository(_resolve_chat_db_path())
            await repo.initialize()
            _repository = repo
    return _repository


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
            raise MonarchAuthError("Monarch Money credentials not configured.")

        # Initialize with correct session file path
        session_file = _resolve_session_file()
        mm = MonarchMoney(session_file=str(session_file))

        # Try to load existing session only if not forcing refresh
        if not force_refresh and session_file.exists():
            try:
                mm.load_session(str(session_file))
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
                raise MonarchAuthError(
                    "MFA required but no secret provided. Please update settings."
                )

            # Save session
            mm.save_session(str(session_file))

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
                    "id": acc.get("id"),
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
                            "id": acc.get("id"),
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
                    "id": tx.get("id"),
                    "date": tx.get("date"),
                    "merchant": tx.get("merchant", {}).get("name"),
                    "amount": tx.get("amount"),
                    "category": tx.get("category", {}).get("name"),
                    "notes": tx.get("notes"),
                    "pending": tx.get("pending"),
                    "goal_id": tx.get("goal", {}).get("id") if tx.get("goal") else None,
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
                            "id": tx.get("id"),
                            "date": tx.get("date"),
                            "merchant": tx.get("merchant", {}).get("name"),
                            "amount": tx.get("amount"),
                            "category": tx.get("category", {}).get("name"),
                            "notes": tx.get("notes"),
                            "pending": tx.get("pending"),
                            "goal_id": tx.get("goal", {}).get("id")
                            if tx.get("goal")
                            else None,
                        }
                    )
                return {"transactions": simplified, "count": len(simplified)}
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_account_transactions")
async def get_monarch_account_transactions(
    account_id: str,
    limit: int = 100,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    """
    Retrieve transactions for a specific account.
    Fetches transactions and filters by account ID.

    Args:
        account_id: ID of the account
        limit: Max transactions to fetch before filtering (default 100)
        start_date: Optional start date in YYYY-MM-DD format
        end_date: Optional end date in YYYY-MM-DD format
    """
    try:
        mm = await _get_client()

        # Validate dates if provided
        if start_date:
            datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            datetime.strptime(end_date, "%Y-%m-%d")

        # Get transactions - fetch more to account for filtering
        data = await mm.get_transactions(limit=limit * 2)
        all_txs = data.get("allTransactions", {}).get("results", [])

        # Filter by account_id
        filtered_txs = [
            tx for tx in all_txs if tx.get("account", {}).get("id") == account_id
        ]

        # Apply date filters if provided
        if start_date or end_date:
            filtered_txs = [
                tx
                for tx in filtered_txs
                if (not start_date or tx.get("date", "") >= start_date)
                and (not end_date or tx.get("date", "") <= end_date)
            ]

        # Limit results
        filtered_txs = filtered_txs[:limit]

        simplified = []
        for tx in filtered_txs:
            simplified.append(
                {
                    "id": tx.get("id"),
                    "date": tx.get("date"),
                    "merchant": tx.get("merchant", {}).get("name"),
                    "amount": tx.get("amount"),
                    "category": tx.get("category", {}).get("name"),
                    "notes": tx.get("notes"),
                    "pending": tx.get("pending"),
                    "account": tx.get("account", {}).get("displayName"),
                    "goal_id": tx.get("goal", {}).get("id") if tx.get("goal") else None,
                }
            )

        return {
            "transactions": simplified,
            "count": len(simplified),
            "account_id": account_id,
        }
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e):
            try:
                mm = await _get_client(force_refresh=True)

                if start_date:
                    datetime.strptime(start_date, "%Y-%m-%d")
                if end_date:
                    datetime.strptime(end_date, "%Y-%m-%d")

                data = await mm.get_transactions(limit=limit * 2)
                all_txs = data.get("allTransactions", {}).get("results", [])

                filtered_txs = [
                    tx
                    for tx in all_txs
                    if tx.get("account", {}).get("id") == account_id
                ]

                if start_date or end_date:
                    filtered_txs = [
                        tx
                        for tx in filtered_txs
                        if (not start_date or tx.get("date", "") >= start_date)
                        and (not end_date or tx.get("date", "") <= end_date)
                    ]

                filtered_txs = filtered_txs[:limit]

                simplified = []
                for tx in filtered_txs:
                    simplified.append(
                        {
                            "id": tx.get("id"),
                            "date": tx.get("date"),
                            "merchant": tx.get("merchant", {}).get("name"),
                            "amount": tx.get("amount"),
                            "category": tx.get("category", {}).get("name"),
                            "notes": tx.get("notes"),
                            "pending": tx.get("pending"),
                            "account": tx.get("account", {}).get("displayName"),
                            "goal_id": tx.get("goal", {}).get("id")
                            if tx.get("goal")
                            else None,
                        }
                    )

                return {
                    "transactions": simplified,
                    "count": len(simplified),
                    "account_id": account_id,
                }
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_budgets")
async def get_monarch_budgets(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    """
    Retrieve budget status and remaining amounts.

    Args:
        start_date: Start date in YYYY-MM-DD format (default: last month)
        end_date: End date in YYYY-MM-DD format (default: next month)
    """
    try:
        mm = await _get_client()

        if start_date:
            datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            datetime.strptime(end_date, "%Y-%m-%d")

        data = await mm.get_budgets(
            start_date=start_date,
            end_date=end_date,
        )
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e):
            try:
                mm = await _get_client(force_refresh=True)

                if start_date:
                    datetime.strptime(start_date, "%Y-%m-%d")
                if end_date:
                    datetime.strptime(end_date, "%Y-%m-%d")

                data = await mm.get_budgets(
                    start_date=start_date,
                    end_date=end_date,
                )
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_goals")
async def get_monarch_goals(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    """
    Retrieve financial goals (v2) with planned and actual contributions.

    Returns active goals including:
    - Goal name, priority, completion status
    - Planned monthly contributions
    - Actual monthly contribution summaries

    Args:
        start_date: Start date in YYYY-MM-DD format (default: last month)
        end_date: End date in YYYY-MM-DD format (default: next month)
    """
    try:
        mm = await _get_client()

        if start_date:
            datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            datetime.strptime(end_date, "%Y-%m-%d")

        # Get budgets data which includes goals
        data = await mm.get_budgets(
            start_date=start_date,
            end_date=end_date,
            use_v2_goals=True,
            use_legacy_goals=False,
        )

        goals = data.get("goalsV2", [])

        # Simplify output
        simplified = []
        for goal in goals:
            simplified.append(
                {
                    "id": goal.get("id"),
                    "name": goal.get("name"),
                    "priority": goal.get("priority"),
                    "completed_at": goal.get("completedAt"),
                    "archived_at": goal.get("archivedAt"),
                    "planned_contributions": goal.get("plannedContributions", []),
                    "monthly_summaries": goal.get("monthlyContributionSummaries", []),
                }
            )

        return {
            "goals": simplified,
            "count": len(simplified),
        }
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)

                if start_date:
                    datetime.strptime(start_date, "%Y-%m-%d")
                if end_date:
                    datetime.strptime(end_date, "%Y-%m-%d")

                data = await mm.get_budgets(
                    start_date=start_date,
                    end_date=end_date,
                    use_v2_goals=True,
                    use_legacy_goals=False,
                )

                goals = data.get("goalsV2", [])
                simplified = []
                for goal in goals:
                    simplified.append(
                        {
                            "id": goal.get("id"),
                            "name": goal.get("name"),
                            "priority": goal.get("priority"),
                            "completed_at": goal.get("completedAt"),
                            "archived_at": goal.get("archivedAt"),
                            "planned_contributions": goal.get(
                                "plannedContributions", []
                            ),
                            "monthly_summaries": goal.get(
                                "monthlyContributionSummaries", []
                            ),
                        }
                    )

                return {
                    "goals": simplified,
                    "count": len(simplified),
                }
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("refresh_monarch_data")
async def refresh_monarch_data() -> dict[str, Any]:
    """
    Trigger a refresh of data from connected institutions (non-blocking).
    Use check_monarch_refresh_status to check if refresh is complete.
    This initiates the refresh and returns immediately.
    """
    try:
        mm = await _get_client()
        # Get accounts and their current status
        accounts_data = await mm.get_accounts()
        accounts = accounts_data.get("accounts", [])
        account_ids = [acc["id"] for acc in accounts]

        if not account_ids:
            return {"status": "No accounts found to refresh"}

        # Request refresh (non-blocking)
        await mm.request_accounts_refresh(account_ids)

        return {
            "status": "Refresh initiated",
            "account_count": len(account_ids),
            "message": "Use check_monarch_refresh_status to check completion",
        }
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                accounts_data = await mm.get_accounts()
                accounts = accounts_data.get("accounts", [])
                account_ids = [acc["id"] for acc in accounts]

                if not account_ids:
                    return {"status": "No accounts found to refresh"}

                await mm.request_accounts_refresh(account_ids)

                return {
                    "status": "Refresh initiated",
                    "account_count": len(account_ids),
                    "message": "Use check_monarch_refresh_status to check completion",
                }
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("check_monarch_refresh_status")
async def check_monarch_refresh_status() -> dict[str, Any]:
    """
    Check the status of account data refresh.
    Returns whether refresh is complete and details about each account.
    """
    try:
        mm = await _get_client()

        # Check if refresh is complete
        is_complete = await mm.is_accounts_refresh_complete()

        # Get current account statuses
        accounts_data = await mm.get_accounts()
        accounts = accounts_data.get("accounts", [])

        account_statuses = []
        for acc in accounts:
            # Safely extract nested data
            credential = acc.get("credential") or {}
            institution = credential.get("institution") or {}

            account_statuses.append(
                {
                    "id": acc.get("id"),
                    "name": acc.get("displayName"),
                    "type": acc.get("type"),
                    "sync_disabled": acc.get("syncDisabled"),
                    "updated_at": acc.get("updatedAt"),
                    "data_provider": credential.get("dataProvider"),
                    "institution": institution.get("name"),
                }
            )

        return {
            "refresh_complete": is_complete,
            "status": "Complete" if is_complete else "In progress",
            "accounts": account_statuses,
            "total_accounts": len(account_statuses),
        }
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e):
            try:
                mm = await _get_client(force_refresh=True)

                is_complete = await mm.is_accounts_refresh_complete()
                accounts_data = await mm.get_accounts()
                accounts = accounts_data.get("accounts", [])

                account_statuses = []
                for acc in accounts:
                    # Safely extract nested data
                    credential = acc.get("credential") or {}
                    institution = credential.get("institution") or {}

                    account_statuses.append(
                        {
                            "id": acc.get("id"),
                            "name": acc.get("displayName"),
                            "type": acc.get("type"),
                            "sync_disabled": acc.get("syncDisabled"),
                            "updated_at": acc.get("updatedAt"),
                            "data_provider": credential.get("dataProvider"),
                            "institution": institution.get("name"),
                        }
                    )

                return {
                    "refresh_complete": is_complete,
                    "status": "Complete" if is_complete else "In progress",
                    "accounts": account_statuses,
                    "total_accounts": len(account_statuses),
                }
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
        # Library expects int for account_id, but it might be a UUID string
        # We pass it as is, relying on the library to handle it (it casts to str internally)
        data = await mm.get_account_holdings(account_id)  # type: ignore

        # Simplify output
        holdings = []
        portfolio = data.get("portfolio", {})
        agg_holdings = portfolio.get("aggregateHoldings", {})
        edges = agg_holdings.get("edges", [])

        for edge in edges:
            node = edge.get("node", {})
            security = node.get("security", {})

            holdings.append(
                {
                    "name": security.get("name") or "Unknown",
                    "ticker": security.get("ticker"),
                    "quantity": node.get("quantity"),
                    "price": security.get("currentPrice"),
                    "value": node.get("totalValue"),
                    "basis": node.get("basis"),
                    "return_dollars": node.get("securityPriceChangeDollars"),
                    "return_percent": node.get("securityPriceChangePercent"),
                    "type": security.get("type"),
                }
            )

        return {"holdings": holdings, "count": len(holdings)}
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_account_holdings(account_id)  # type: ignore

                # Simplify output
                holdings = []
                portfolio = data.get("portfolio", {})
                agg_holdings = portfolio.get("aggregateHoldings", {})
                edges = agg_holdings.get("edges", [])

                for edge in edges:
                    node = edge.get("node", {})
                    security = node.get("security", {})

                    holdings.append(
                        {
                            "name": security.get("name") or "Unknown",
                            "ticker": security.get("ticker"),
                            "quantity": node.get("quantity"),
                            "price": security.get("currentPrice"),
                            "value": node.get("totalValue"),
                            "basis": node.get("basis"),
                            "return_dollars": node.get("securityPriceChangeDollars"),
                            "return_percent": node.get("securityPriceChangePercent"),
                            "type": security.get("type"),
                        }
                    )

                return {"holdings": holdings, "count": len(holdings)}
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


@mcp.tool("get_monarch_snapshots_by_account_type")
async def get_monarch_snapshots_by_account_type(
    start_date: str,
    timeframe: str = "month",
) -> dict[str, Any]:
    """
    Retrieve snapshots of net values grouped by account type.
    Returns monthly or yearly aggregations for comparing different account types.

    Args:
        start_date: Start date in YYYY-MM-DD format (e.g., "2024-01-01")
        timeframe: Aggregation period - either "month" or "year" (default: "month")

    Use cases:
        - Compare growth of investment vs checking accounts over time
        - Monthly snapshots of each account type
        - Year-over-year comparison by account type
    """
    try:
        mm = await _get_client()

        # Validate date format
        datetime.strptime(start_date, "%Y-%m-%d")

        # Validate timeframe
        if timeframe not in ["month", "year"]:
            return {"error": "timeframe must be either 'month' or 'year'"}

        data = await mm.get_account_snapshots_by_type(start_date, timeframe)
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                datetime.strptime(start_date, "%Y-%m-%d")

                if timeframe not in ["month", "year"]:
                    return {"error": "timeframe must be either 'month' or 'year'"}

                data = await mm.get_account_snapshots_by_type(start_date, timeframe)
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


@mcp.tool("get_monarch_spending_by_category")
async def get_monarch_spending_by_category(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    """
    Analyze spending patterns by category within a date range.
    Dates should be in YYYY-MM-DD format.
    Returns spending breakdown by category to understand spending patterns.
    """
    try:
        mm = await _get_client()

        # Validate dates if provided
        if start_date:
            datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            datetime.strptime(end_date, "%Y-%m-%d")

        # Get cashflow data which includes category breakdowns
        data = await mm.get_cashflow(start_date=start_date, end_date=end_date)

        # Extract and simplify spending by category
        spending_by_category = []

        # The API returns 'byCategoryGroup' at the top level
        category_groups = data.get("byCategoryGroup", [])

        for group_data in category_groups:
            group_by = group_data.get("groupBy", {})
            category_group = group_by.get("categoryGroup", {})
            group_name = category_group.get("name")
            group_type = category_group.get("type")

            summary = group_data.get("summary", {})
            amount = summary.get("sum", 0)

            # Focus on expense categories (negative amounts)
            if group_type == "expense" and amount < 0:
                spending_by_category.append(
                    {
                        "category_group": group_name,
                        "type": group_type,
                        "amount": abs(amount),
                    }
                )

        # Sort by amount (most spending first)
        spending_by_category.sort(key=lambda x: x.get("amount", 0), reverse=True)

        return {
            "spending_by_category": spending_by_category,
            "start_date": start_date,
            "end_date": end_date,
            "total_categories": len(spending_by_category),
        }
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)

                if start_date:
                    datetime.strptime(start_date, "%Y-%m-%d")
                if end_date:
                    datetime.strptime(end_date, "%Y-%m-%d")

                data = await mm.get_cashflow(start_date=start_date, end_date=end_date)

                spending_by_category = []
                category_groups = data.get("byCategoryGroup", [])

                for group_data in category_groups:
                    group_by = group_data.get("groupBy", {})
                    category_group = group_by.get("categoryGroup", {})
                    group_name = category_group.get("name")
                    group_type = category_group.get("type")

                    summary = group_data.get("summary", {})
                    amount = summary.get("sum", 0)

                    if group_type == "expense" and amount < 0:
                        spending_by_category.append(
                            {
                                "category_group": group_name,
                                "type": group_type,
                                "amount": abs(amount),
                            }
                        )

                spending_by_category.sort(
                    key=lambda x: x.get("amount", 0), reverse=True
                )

                return {
                    "spending_by_category": spending_by_category,
                    "start_date": start_date,
                    "end_date": end_date,
                    "total_categories": len(spending_by_category),
                }
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
                "id": c.get("id"),
                "name": c.get("name"),
                "group": c.get("group", {}).get("name"),
                "type": c.get("group", {}).get("type"),
                "is_system": c.get("isSystemCategory"),
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
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "group": c.get("group", {}).get("name"),
                        "type": c.get("group", {}).get("type"),
                        "is_system": c.get("isSystemCategory"),
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
        # Library expects int for account_id in get_account_history, but we pass as is
        data = await mm.get_account_history(account_id)  # type: ignore
        # data is a list of snapshots
        return {"history": data, "count": len(data) if isinstance(data, list) else 0}
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_account_history(account_id)  # type: ignore
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
    goal_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Update an existing transaction.
    Only provide fields that need to be updated.

    Args:
        transaction_id: ID of the transaction to update
        notes: Optional notes
        category_id: Category ID
        merchant_name: Merchant name
        amount: Transaction amount
        date: Transaction date in YYYY-MM-DD format
        goal_id: Goal ID to associate transaction with (use empty string to clear)
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
            goal_id=goal_id,
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
                    goal_id=goal_id,
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
    Set or delete budget amount for a category.

    Args:
        amount: Budget amount (set to 0.0 to delete/clear the budget)
        category_id: ID of the category
        start_date: Start date in YYYY-MM-DD format (usually first of month)
        apply_to_future: Whether to apply to future months

    To delete a budget: set amount=0.0
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


@mcp.tool("delete_monarch_transaction_category")
async def delete_monarch_transaction_category(category_id: str) -> dict[str, Any]:
    """Delete a transaction category."""
    try:
        mm = await _get_client()
        success = await mm.delete_transaction_category(category_id)
        return {"success": success}
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                success = await mm.delete_transaction_category(category_id)
                return {"success": success}
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("delete_monarch_transaction_categories")
async def delete_monarch_transaction_categories(
    category_ids: list[str],
) -> dict[str, Any]:
    """Delete multiple transaction categories."""
    try:
        mm = await _get_client()
        results = await mm.delete_transaction_categories(category_ids)
        return {"results": results}
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                results = await mm.delete_transaction_categories(category_ids)
                return {"results": results}
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("get_monarch_transaction_splits")
async def get_monarch_transaction_splits(transaction_id: str) -> dict[str, Any]:
    """
    Get split details for a transaction.
    Split transactions allow dividing a single transaction across multiple categories.
    """
    try:
        mm = await _get_client()
        data = await mm.get_transaction_splits(transaction_id)
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.get_transaction_splits(transaction_id)
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("update_monarch_transaction_splits")
async def update_monarch_transaction_splits(
    transaction_id: str,
    splits: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Update split details for a transaction.

    Args:
        transaction_id: ID of the transaction to split
        splits: List of split dictionaries, each containing:
            - amount: Split amount (float)
            - category_id: Category ID for this split (str)
            - notes: Optional notes for this split (str)

    Example splits:
        [
            {"amount": 50.0, "category_id": "cat_123", "notes": "Groceries"},
            {"amount": 30.0, "category_id": "cat_456", "notes": "Household"}
        ]
    """
    try:
        mm = await _get_client()
        data = await mm.update_transaction_splits(transaction_id, splits)
        return data
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e) or "Invalid token" in str(e):
            try:
                mm = await _get_client(force_refresh=True)
                data = await mm.update_transaction_splits(transaction_id, splits)
                return data
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": str(e)}


@mcp.tool("upload_monarch_account_balance_history")
async def upload_monarch_account_balance_history(
    account_id: str,
    csv_content: str,
) -> dict[str, Any]:
    """
    Upload historical balance data for a manual account.

    CSV format must have two columns: date,balance
    - date: YYYY-MM-DD format
    - balance: Numeric value (e.g., 5000.00)

    Example CSV:
        date,balance
        2024-01-01,5000.00
        2024-02-01,5250.00
        2024-03-01,5100.00

    This permanently stores the balance history on Monarch's servers.
    Useful for backfilling historical data when adding a manual account.

    Args:
        account_id: ID of the account to upload history for
        csv_content: CSV string with date,balance columns
    """
    try:
        # Basic validation
        if not csv_content.strip():
            return {"error": "CSV content cannot be empty"}

        # Check for required header
        lines = csv_content.strip().split("\n")
        if len(lines) < 2:
            return {"error": "CSV must have at least a header row and one data row"}

        header = lines[0].strip().lower()
        if "date" not in header or "balance" not in header:
            return {
                "error": "CSV must have 'date' and 'balance' columns. Example: date,balance"
            }

        mm = await _get_client()
        await mm.upload_account_balance_history(account_id, csv_content)

        # Count data rows (excluding header)
        data_rows = len(lines) - 1

        return {
            "success": True,
            "account_id": account_id,
            "rows_uploaded": data_rows,
            "message": f"Successfully uploaded {data_rows} balance records",
        }
    except Exception as e:
        error_msg = str(e)
        if (
            "401" in error_msg
            or "Unauthorized" in error_msg
            or "Invalid token" in error_msg
        ):
            try:
                mm = await _get_client(force_refresh=True)
                await mm.upload_account_balance_history(account_id, csv_content)

                lines = csv_content.strip().split("\n")
                data_rows = len(lines) - 1

                return {
                    "success": True,
                    "account_id": account_id,
                    "rows_uploaded": data_rows,
                    "message": f"Successfully uploaded {data_rows} balance records",
                }
            except Exception as retry_e:
                return {"error": f"Retry failed: {str(retry_e)}"}
        return {"error": error_msg}


def run(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = DEFAULT_HTTP_PORT,
) -> None:  # pragma: no cover - integration entrypoint
    """Run the MCP server with the specified transport."""
    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            json_response=True,
            stateless_http=True,
            uvicorn_config={"access_log": False},
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover - CLI helper
    import argparse
    parser = argparse.ArgumentParser(description="Monarch Money MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport protocol to use",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind HTTP server to",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help="Port for HTTP server",
    )
    args = parser.parse_args()
    run(args.transport, args.host, args.port)
