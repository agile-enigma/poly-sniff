import pandas as pd


def compute(transactions_df: pd.DataFrame, group_by: str = 'proxyWallet') -> pd.DataFrame:
    """Compute userPriceConvictionScore_market.

    USDC-weighted average of (price - 0.50) flipped by side.
    Negative = contrarian/informed (buying before market agrees).
    Positive = following consensus.
    group_by controls the grouping dimension (default: proxyWallet; use conditionId for
    profile --sniff mode).
    """
    df = transactions_df.copy()
    df['_conviction_num'] = (
        (df['price'] - 0.50)
        * df['usdcSize']
        * df['side'].map({'BUY': 1, 'SELL': -1})
    )

    user_num = df.groupby(group_by)['_conviction_num'].sum()
    user_denom = df.groupby(group_by)['usdcSize'].sum()

    user_conviction = (user_num / user_denom.replace(0, float('nan'))).fillna(0)
    result = user_conviction.reset_index()
    result.columns = [group_by, 'userPriceConvictionScore_market']
    return result
