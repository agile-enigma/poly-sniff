import pandas as pd


def compute(transactions_df: pd.DataFrame, group_by: str = 'proxyWallet') -> pd.DataFrame:
    """Compute per-group activity metrics.

    userTradeCount_market: number of trades in this market.
    userTotalUsdcVolume_market: total USDC traded in this market.
    userAvgTradeSize_market: mean USDC per trade in this market.
    userMaxTradeSize_market: largest single trade in USDC in this market.
    userAccountAgeAtFirstTrade_market: days between joinDate_est and earliest trade in
        the group. Only computed when joinDate_est is present in transactions_df.
    group_by controls the grouping dimension (default: proxyWallet; use conditionId for
    profile --sniff mode).
    """
    user_activity = transactions_df.groupby(group_by).agg(
        userTradeCount_market=('size', 'count'),
        userTotalUsdcVolume_market=('usdcSize', 'sum'),
        userAvgTradeSize_market=('usdcSize', 'mean'),
        userMaxTradeSize_market=('usdcSize', 'max'),
    ).reset_index()

    if 'joinDate_est' in transactions_df.columns:
        user_dates = transactions_df.groupby(group_by).agg(
            _firstTrade=('timestamp_est', 'min'),
            joinDate_est=('joinDate_est', 'first'),
        ).reset_index()
        user_dates['userAccountAgeAtFirstTrade_market'] = (
            user_dates['_firstTrade'] - user_dates['joinDate_est']
        ).dt.days
        user_activity = user_activity.merge(
            user_dates[[group_by, 'userAccountAgeAtFirstTrade_market']], on=group_by
        )

    return user_activity
