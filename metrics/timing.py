import pandas as pd


def add_hours_before_resolution(
    transactions_df: pd.DataFrame, resolution_time: pd.Timestamp
) -> pd.DataFrame:
    """Add hoursBeforeResolution column to transactions DataFrame."""
    df = transactions_df.copy()
    df['hoursBeforeResolution'] = (
        (resolution_time - df['timestamp_est']).dt.total_seconds() / 3600
    )
    return df


def compute(
    transactions_df: pd.DataFrame,
    late_window: int = 24,
    group_by: str = 'proxyWallet',
) -> pd.DataFrame:
    """Compute userLastTradeHoursBeforeResolution_market and userLateVolumeRatio_market.

    Requires hoursBeforeResolution column (added by add_hours_before_resolution, or
    computed inline for profile --sniff mode).

    userLastTradeHoursBeforeResolution_market: minimum hoursBeforeResolution per group
        (i.e. how close to resolution the last trade was).
    userLateVolumeRatio_market: fraction of USDC volume placed within late_window hours
        of resolution.
    group_by controls the grouping dimension (default: proxyWallet; use conditionId for
    profile --sniff mode).
    """
    user_timing = (
        transactions_df.groupby(group_by)['hoursBeforeResolution']
        .min()
        .reset_index()
    )
    user_timing.columns = [group_by, 'userLastTradeHoursBeforeResolution_market']

    all_keys = transactions_df[group_by].unique()

    late_num = (
        transactions_df[transactions_df['hoursBeforeResolution'] <= late_window]
        .groupby(group_by)['usdcSize']
        .sum()
        .reindex(all_keys, fill_value=0)
    )
    late_denom = transactions_df.groupby(group_by)['usdcSize'].sum()

    user_late = (late_num / late_denom.replace(0, float('nan'))).fillna(0)
    user_late_volume = user_late.reset_index()
    user_late_volume.columns = [group_by, 'userLateVolumeRatio_market']

    return user_timing.merge(user_late_volume, on=group_by)
