import pandas as pd


def compute(transactions_df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-user activity metrics.

    userTradeCount_market: number of trades in this market.
    userTotalUsdcVolume_market: total USDC traded in this market.
    userAvgTradeSize_market: mean USDC per trade in this market.
    userMaxTradeSize_market: largest single trade in USDC in this market.
    userAccountAgeAtFirstTrade_market: days between joinDate_est and earliest trade in market.
    """
    user_activity = transactions_df.groupby('proxyWallet').agg(
        userTradeCount_market=('size', 'count'),
        userTotalUsdcVolume_market=('usdcSize', 'sum'),
        userAvgTradeSize_market=('usdcSize', 'mean'),
        userMaxTradeSize_market=('usdcSize', 'max'),
    ).reset_index()

    # userAccountAgeAtFirstTrade_market: days from account creation to first trade in the target market
    user_dates = transactions_df.groupby('proxyWallet').agg(
        _firstTrade=('timestamp_est', 'min'),
        joinDate_est=('joinDate_est', 'first'),
    ).reset_index()
    user_dates['userAccountAgeAtFirstTrade_market'] = (
        user_dates['_firstTrade'] - user_dates['joinDate_est']
    ).dt.days
    user_activity = user_activity.merge(
        user_dates[['proxyWallet', 'userAccountAgeAtFirstTrade_market']], on='proxyWallet'
    )

    return user_activity
