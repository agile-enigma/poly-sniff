import sys

import pandas as pd
import requests


def fetch_market_info(market_slug: str) -> dict:
    """Fetch full market data from the gamma API using market slug.

    Returns the raw market dict. The caller extracts conditionId and passes
    the dict to get_reference_time. This is the only call to the gamma API.
    """
    return requests.get(
        f"https://gamma-api.polymarket.com/markets/slug/{market_slug}"
    ).json()


def get_reference_time(market: dict, user_reference_time: str | None) -> pd.Timestamp:
    """Resolve the reference time used for timing metric calculations.

    Priority:
    1. User-provided --reference-time (must not be in the future).
    2. market['closedTime'] if market['closed'] is True.
    3. Exit with error if market is active and no reference time is provided.
    """
    if user_reference_time:
        ref = pd.to_datetime(user_reference_time)
        if ref > pd.Timestamp.now():
            sys.exit("Error: --reference-time cannot be in the future.")
        return ref

    if market['closed']:
        return (
            pd.to_datetime(market['closedTime'])
            .tz_convert('US/Eastern')
            .tz_localize(None)
        )

    sys.exit("Error: This market is still active. Please provide --reference-time.")


def fetch_profile_positions(proxy_wallet: str, limit: int = 20) -> tuple:
    """Fetch closed and active positions for a wallet address.

    Paginates automatically when limit exceeds the API's per-request max
    (50 for closed positions, 500 for active positions).

    Returns:
        (closed_rows, active_rows): lists of raw API response dicts
    """
    CLOSED_API_MAX = 50
    closed_rows = []
    offset = 0
    remaining = limit
    while remaining > 0:
        per_request = min(remaining, CLOSED_API_MAX)
        res = requests.get(
            f"https://data-api.polymarket.com/closed-positions"
            f"?limit={per_request}&sortBy=REALIZEDPNL&sortDirection=DESC"
            f"&user={proxy_wallet}&offset={offset}"
        ).json()
        closed_rows.extend(res)
        if len(res) < per_request:
            break
        offset += per_request
        remaining -= per_request

    ACTIVE_API_MAX = 500
    active_rows = []
    offset = 0
    remaining = limit
    while remaining > 0:
        per_request = min(remaining, ACTIVE_API_MAX)
        res = requests.get(
            f"https://data-api.polymarket.com/positions"
            f"?sizeThreshold=1&limit={per_request}&sortBy=CURRENT&sortDirection=DESC"
            f"&user={proxy_wallet}&offset={offset}"
        ).json()
        active_rows.extend(res)
        if len(res) < per_request:
            break
        offset += per_request
        remaining -= per_request

    return closed_rows, active_rows


def fetch(market_conditionId: str, position_side: str = 'Yes', limit: int = 50):
    """Fetch top position holders, then profiles and transactions for each.

    Returns:
        profile_rows: list of dicts, one per holder
        transaction_rows: list of raw API response items (may include non-dicts)
    """
    top_position_holders = requests.get(
        f"https://data-api.polymarket.com/v1/market-positions"
        f"?market={market_conditionId}&limit={limit}&offset=0"
        f"&status=ALL&sortBy=TOTAL_PNL&sortDirection=DESC"
    ).json()

    side_idx = 0 if top_position_holders[0]['positions'][0]['outcome'] == position_side else 1
    holders = top_position_holders[side_idx]['positions']

    profile_rows = []
    transaction_rows = []

    for holder in holders:
        proxy_wallet = holder['proxyWallet']
        user_name = holder['name'] if bool(holder['name']) else 'ANONYMOUS USER'

        user_stats = requests.get(
            f"https://data-api.polymarket.com/v1/user-stats?proxyAddress={proxy_wallet}"
        ).json()

        leaderboard = requests.get(
            f"https://data-api.polymarket.com/v1/leaderboard"
            f"?timePeriod=all&orderBy=VOL&limit=1&offset=0&category=overall&user={proxy_wallet}"
        ).json()
        lb_entry = leaderboard[0] if leaderboard else {}

        profile_rows.append({
            'proxyWallet': proxy_wallet,
            'userName': user_name,
            'xUsername': lb_entry.get('xUsername'),
            'joinDate_utc': user_stats.get('joinDate'),
            'profileImage': holder.get('profileImage'),
            'verified': holder.get('verified'),
            'anonymousUser': bool(holder['name']),
            'views': user_stats.get('views'),
            'userRank_lifetime': lb_entry.get('rank'),
            'userVol_lifetime': lb_entry.get('vol'),
            'userPnl_lifetime': lb_entry.get('pnl'),
            'userMarketsTraded_lifetime': user_stats.get('trades'),
            'userLargestWin_lifetime': user_stats.get('largestWin'),
            'userAvgPrice_market': holder.get('avgPrice'),
            'userTotalBought_market': holder.get('totalBought'),
            'userTotalPnl_market': holder.get('totalPnl'),
            'userRealizedPnl_market': holder.get('realizedPnl'),
        })

        offset = 0
        while True:
            res = requests.get(
                f"https://data-api.polymarket.com/trades"
                f"?user={proxy_wallet}&market={market_conditionId}"
                f"&limit=100&offset={offset}&takerOnly=false"
            ).json()
            transaction_rows.extend(res)
            if len(res) < 100:
                break
            offset += 100

    return profile_rows, transaction_rows
