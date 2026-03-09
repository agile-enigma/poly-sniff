import pandas as pd


def compute(transactions_df: pd.DataFrame) -> pd.DataFrame:
    """Compute userDirectionalConsistency_market and userWeightedDirectionalConsistency_market.

    userDirectionalConsistency_market  = abs(sum(netPosition)) / sum(abs(netPosition))
    userWeightedDirectionalConsistency_market = abs(sum(weightedPosition)) / sum(abs(weightedPosition))

    Range 0–1. 1.0 means all trades point the same direction.
    """
    user_directional = (
        transactions_df.groupby('proxyWallet')['netPosition']
        .agg(lambda x: abs(x.sum()) / x.abs().sum() if x.abs().sum() != 0 else 0)
        .reset_index()
    )
    user_directional.columns = ['proxyWallet', 'userDirectionalConsistency_market']

    user_weighted = (
        transactions_df.groupby('proxyWallet')['weightedPosition']
        .agg(lambda x: abs(x.sum()) / x.abs().sum() if x.abs().sum() != 0 else 0)
        .reset_index()
    )
    user_weighted.columns = ['proxyWallet', 'userWeightedDirectionalConsistency_market']

    return user_directional.merge(user_weighted, on='proxyWallet')
