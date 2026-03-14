import pandas as pd


def compute(transactions_df: pd.DataFrame, group_by: str = 'proxyWallet') -> pd.DataFrame:
    """Compute userDirectionalConsistency_market and userWeightedDirectionalConsistency_market.

    userDirectionalConsistency_market  = abs(sum(netPosition)) / sum(abs(netPosition))
    userWeightedDirectionalConsistency_market = abs(sum(weightedPosition)) / sum(abs(weightedPosition))

    Range 0–1. 1.0 means all trades point the same direction.
    group_by controls the grouping dimension (default: proxyWallet; use conditionId for
    profile --sniff mode).
    """
    user_directional = (
        transactions_df.groupby(group_by)['netPosition']
        .agg(lambda x: abs(x.sum()) / x.abs().sum() if x.abs().sum() != 0 else 0)
        .reset_index()
    )
    user_directional.columns = [group_by, 'userDirectionalConsistency_market']

    user_weighted = (
        transactions_df.groupby(group_by)['weightedPosition']
        .agg(lambda x: abs(x.sum()) / x.abs().sum() if x.abs().sum() != 0 else 0)
        .reset_index()
    )
    user_weighted.columns = [group_by, 'userWeightedDirectionalConsistency_market']

    return user_directional.merge(user_weighted, on=group_by)
