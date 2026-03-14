import pandas as pd


# Columns static per market in profile --sniff context — forward/back fill per conditionId
_MARKET_STATIC_COLS = [
    'title', 'slug',
    'userDirectionalConsistency_market', 'userWeightedDirectionalConsistency_market',
    'userDominantSideRatio_market', 'userDominantSide_market', 'userPriceConvictionScore_market',
    'userTradeCount_market', 'userTotalUsdcVolume_market', 'userAvgTradeSize_market', 'userMaxTradeSize_market',
    'userLastTradeHoursBeforeResolution_market', 'userLateVolumeRatio_market',
    'userAccountAgeAtFirstTrade_market', 'userRealizedPnl_market',
]

# Columns that are static per user — forward/back fill across the grid
_PROFILE_COLS = [
    # Market metadata
    'conditionId', 'title', 'slug', 'icon', 'eventSlug',
    # User profile
    'userName', 'pseudonym', 'anonymousUser', 'bio',
    'profileImage', 'profileImageOptimized',
    'joinDate_est', 'userMarketsTraded_lifetime', 'xUsername',
    # User behavior metrics (one value per user per market)
    'userDirectionalConsistency_market', 'userWeightedDirectionalConsistency_market',
    'userDominantSideRatio_market', 'userDominantSide_market', 'userPriceConvictionScore_market',
    'userTradeCount_market', 'userTotalUsdcVolume_market', 'userAvgTradeSize_market', 'userMaxTradeSize_market',
    'userLastTradeHoursBeforeResolution_market', 'userLateVolumeRatio_market',
    'userAccountAgeAtFirstTrade_market',
]

# Transaction-level numerics — fill with 0 for empty hours
_TRANSACTION_NUMERIC_COLS = [
    'size', 'usdcSize', 'price',
    'netPosition', 'weightedPosition',
    'netYes', 'netNo', 'weightedNetYes', 'weightedNetNo',
]


def build(transactions_df: pd.DataFrame) -> pd.DataFrame:
    """Build hourly scaffold for Tableau visualization.

    Creates a full hour × wallet grid. User-level metrics are forward/back
    filled. Transaction numerics are zero-filled. Cumulative position columns
    are appended.
    """
    df = transactions_df.copy()

    # Floor timestamps to hour
    df['timestamp_est'] = pd.to_datetime(df['timestamp_est']).dt.floor('h')

    # Build aggregation dict from columns that exist in the DataFrame
    agg_dict = {}

    first_cols = [
        # Market metadata
        'conditionId', 'title', 'slug', 'icon', 'eventSlug',
        # User profile
        'userName', 'pseudonym', 'anonymousUser', 'bio',
        'profileImage', 'profileImageOptimized',
        'joinDate_est', 'userMarketsTraded_lifetime', 'xUsername',
        # Transaction metadata
        'transactionHash', 'asset', 'outcomeIndex', 'side', 'outcome',
        # User metrics
        'userDirectionalConsistency_market', 'userWeightedDirectionalConsistency_market',
        'userDominantSideRatio_market', 'userDominantSide_market', 'userPriceConvictionScore_market',
        'userTradeCount_market', 'userTotalUsdcVolume_market', 'userAvgTradeSize_market', 'userMaxTradeSize_market',
        'userLastTradeHoursBeforeResolution_market', 'userLateVolumeRatio_market',
        'userAccountAgeAtFirstTrade_market',
        'userAvgPrice_market', 'userTotalBought_market',
        'userTotalPnl_market', 'userRealizedPnl_market',
    ]
    for col in first_cols:
        if col in df.columns:
            agg_dict[col] = 'first'

    sum_cols = [
        'size', 'usdcSize', 'netPosition', 'weightedPosition',
        'netYes', 'netNo', 'weightedNetYes', 'weightedNetNo',
    ]
    for col in sum_cols:
        if col in df.columns:
            agg_dict[col] = 'sum'

    if 'price' in df.columns:
        agg_dict['price'] = 'mean'

    if 'hoursBeforeResolution' in df.columns:
        agg_dict['hoursBeforeResolution'] = 'min'

    df = df.groupby(['timestamp_est', 'proxyWallet']).agg(agg_dict).reset_index()

    # Expand to full hour × wallet grid
    hours = pd.date_range(df['timestamp_est'].min(), df['timestamp_est'].max(), freq='h')
    wallets = df['proxyWallet'].unique()
    full_grid = pd.MultiIndex.from_product(
        [hours, wallets], names=['timestamp_est', 'proxyWallet']
    )

    df = (
        df.set_index(['timestamp_est', 'proxyWallet'])
        .reindex(full_grid)
        .reset_index()
    )

    # Forward/back fill user-level columns per wallet
    fill_cols = [c for c in _PROFILE_COLS if c in df.columns]
    df[fill_cols] = df.groupby('proxyWallet')[fill_cols].transform(
        lambda x: x.ffill().bfill()
    )

    # Zero-fill transaction numeric columns
    zero_cols = [c for c in _TRANSACTION_NUMERIC_COLS if c in df.columns]
    df[zero_cols] = df[zero_cols].fillna(0)

    # Cumulative position (requires sort by wallet then time)
    df = df.sort_values(['proxyWallet', 'timestamp_est']).reset_index(drop=True)
    df['cumNetPosition'] = df.groupby('proxyWallet')['netPosition'].cumsum()
    df['cumWeightedPosition'] = df.groupby('proxyWallet')['weightedPosition'].cumsum()

    return df


def build_profile_sniff(transactions_df: pd.DataFrame) -> pd.DataFrame:
    """Build hourly scaffold for profile --sniff Tableau visualization.

    Creates a full hour × conditionId grid. Market-level metrics are forward/back
    filled per conditionId. Transaction numerics are zero-filled. Cumulative position
    columns are appended.
    """
    df = transactions_df.copy()

    # Floor timestamps to hour
    df['timestamp_est'] = pd.to_datetime(df['timestamp_est']).dt.floor('h')

    agg_dict = {}

    first_cols = [
        'title', 'slug',
        'transactionHash', 'asset', 'outcomeIndex', 'side', 'outcome',
        'userDirectionalConsistency_market', 'userWeightedDirectionalConsistency_market',
        'userDominantSideRatio_market', 'userDominantSide_market', 'userPriceConvictionScore_market',
        'userTradeCount_market', 'userTotalUsdcVolume_market', 'userAvgTradeSize_market', 'userMaxTradeSize_market',
        'userLastTradeHoursBeforeResolution_market', 'userLateVolumeRatio_market',
        'userAccountAgeAtFirstTrade_market', 'userRealizedPnl_market',
    ]
    for col in first_cols:
        if col in df.columns:
            agg_dict[col] = 'first'

    sum_cols = [
        'size', 'usdcSize', 'netPosition', 'weightedPosition',
        'netYes', 'netNo', 'weightedNetYes', 'weightedNetNo',
    ]
    for col in sum_cols:
        if col in df.columns:
            agg_dict[col] = 'sum'

    if 'price' in df.columns:
        agg_dict['price'] = 'mean'

    if 'hoursBeforeResolution' in df.columns:
        agg_dict['hoursBeforeResolution'] = 'min'

    df = df.groupby(['timestamp_est', 'conditionId']).agg(agg_dict).reset_index()

    # Expand to full hour × conditionId grid
    hours = pd.date_range(df['timestamp_est'].min(), df['timestamp_est'].max(), freq='h')
    markets = df['conditionId'].unique()
    full_grid = pd.MultiIndex.from_product(
        [hours, markets], names=['timestamp_est', 'conditionId']
    )

    df = (
        df.set_index(['timestamp_est', 'conditionId'])
        .reindex(full_grid)
        .reset_index()
    )

    # Forward/back fill market-level columns per conditionId
    fill_cols = [c for c in _MARKET_STATIC_COLS if c in df.columns]
    df[fill_cols] = df.groupby('conditionId')[fill_cols].transform(
        lambda x: x.ffill().bfill()
    )

    # Zero-fill transaction numeric columns
    zero_cols = [c for c in _TRANSACTION_NUMERIC_COLS if c in df.columns]
    df[zero_cols] = df[zero_cols].fillna(0)

    # Cumulative position (requires sort by conditionId then time)
    df = df.sort_values(['conditionId', 'timestamp_est']).reset_index(drop=True)
    df['cumNetPosition'] = df.groupby('conditionId')['netPosition'].cumsum()
    df['cumWeightedPosition'] = df.groupby('conditionId')['weightedPosition'].cumsum()

    return df
