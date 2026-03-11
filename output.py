import os
import pandas as pd
from datetime import datetime

try:
    from tabulate import tabulate
    _HAS_TABULATE = True
except ImportError:
    _HAS_TABULATE = False

_METRIC_COLS = [
    'userDirectionalConsistency_market',
    'userWeightedDirectionalConsistency_market',
    'userDominantSideRatio_market',
    'userDominantSide_market',
    'userPriceConvictionScore_market',
    'userTradeCount_market',
    'userMarketsTraded_lifetime',
    'userTotalUsdcVolume_market',
    'userAvgTradeSize_market',
    'userMaxTradeSize_market',
    'userLastTradeHoursBeforeResolution_market',
    'userLateVolumeRatio_market',
    'userAccountAgeAtFirstTrade_market',
    'userTotalPnl_market',
    'userRealizedPnl_market',
]


def flag_users(
    transactions_df: pd.DataFrame,
    min_directional: float,
    min_dominant: float,
    max_conviction: float,
    min_late_volume: float,
    resolved_outcome: str = None,
) -> pd.DataFrame:
    """Apply conjunctive flagging filter and return one row per flagged user.

    If resolved_outcome is 'Yes', keeps only bullish users.
    If resolved_outcome is 'No', keeps only bearish users.
    """
    mask = (
        (transactions_df['userDirectionalConsistency_market'] >= min_directional)
        & (transactions_df['userDominantSideRatio_market'] >= min_dominant)
        & (transactions_df['userPriceConvictionScore_market'] < max_conviction)
        & (transactions_df['userLateVolumeRatio_market'] >= min_late_volume)
    )

    if resolved_outcome == 'Yes':
        mask = mask & (transactions_df['userDominantSide_market'] == 'bullish')
    elif resolved_outcome == 'No':
        mask = mask & (transactions_df['userDominantSide_market'] == 'bearish')

    base_cols = ['proxyWallet', 'userName', 'joinDate_est', 'xUsername']
    metric_cols = [c for c in _METRIC_COLS if c in transactions_df.columns]

    return (
        transactions_df.loc[mask, base_cols + metric_cols]
        .drop_duplicates(subset=['proxyWallet'])
        .reset_index(drop=True)
    )


def print_table(flagged_df: pd.DataFrame) -> None:
    """Print flagged users table to terminal."""
    if flagged_df.empty:
        print("No users flagged.")
        return

    display = flagged_df[['userName', 'proxyWallet', 'joinDate_est', 'xUsername', 'userDominantSide_market', 'userRealizedPnl_market', 'userTotalUsdcVolume_market', 'userTradeCount_market', 'userMarketsTraded_lifetime']].copy()
    display['proxyWallet'] = display['proxyWallet'].str[:7] + '...'
    display['joinDate_est'] = pd.to_datetime(display['joinDate_est']).dt.strftime('%Y-%m-%d')
    display.columns = ['User', 'Wallet', 'Joined', 'X Handle', 'Dominant Side', 'Realized PnL', 'USDC Volume', 'Intra-Market Trades', 'Markets Traded']

    if _HAS_TABULATE:
        print(tabulate(display, headers='keys', tablefmt='rounded_grid', showindex=False))
    else:
        print(display.to_string(index=False))


_TERMINAL_LIMIT = 20

_CLOSED_COLS = ['title', 'slug', 'outcome', 'avgPrice', 'totalBought', 'realizedPnl', 'curPrice']
_ACTIVE_COLS = ['title', 'slug', 'size', 'avgPrice', 'totalBought', 'currentValue', 'cashPnl', 'percentPnl', 'realizedPnl', 'curPrice']


def _truncate_str_col(series: pd.Series, max_len: int = 40) -> pd.Series:
    return series.apply(
        lambda x: x[:max_len] + '...' if isinstance(x, str) and len(x) > max_len else x
    )


def make_output_dir(key: str, subcommand: str = 'sniff') -> str:
    """Create and return a timestamped output folder under polysniff_output/{subcommand}/."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    folder = os.path.join('polysniff_output', subcommand, f"{key[:7]}_{timestamp}")
    os.makedirs(folder, exist_ok=True)
    return folder


def write_xlsx(
    output_dir: str,
    profiles_df: pd.DataFrame = None,
    transactions_df: pd.DataFrame = None,
    scaffold_df: pd.DataFrame = None,
    flagged_df: pd.DataFrame = None,
) -> None:
    """Write any non-None DataFrames to xlsx in output_dir."""
    if profiles_df is not None:
        profiles_df.to_excel(os.path.join(output_dir, 'profiles.xlsx'), index=False)
    if transactions_df is not None:
        transactions_df.to_excel(os.path.join(output_dir, 'transactions.xlsx'), index=False)
    if scaffold_df is not None:
        scaffold_df.to_excel(os.path.join(output_dir, 'scaffold.xlsx'), index=False)
    if flagged_df is not None:
        flagged_df.to_excel(os.path.join(output_dir, 'flagged_users.xlsx'), index=False)


def _print_positions_section(
    title: str, df: pd.DataFrame, cols: list, label: str
) -> None:
    """Print a single positions section (closed or active) to terminal."""
    print(title)
    if df.empty:
        print(f"No {label} positions.")
        print()
        return
    display = df[[c for c in cols if c in df.columns]].copy()
    for col in ('title', 'slug'):
        if col in display.columns:
            display[col] = _truncate_str_col(display[col])
    total = len(display)
    if _HAS_TABULATE:
        print(tabulate(display.head(_TERMINAL_LIMIT), headers='keys', tablefmt='rounded_grid', showindex=False))
    else:
        print(display.head(_TERMINAL_LIMIT).to_string(index=False))
    if total > _TERMINAL_LIMIT:
        print(f"Showing {_TERMINAL_LIMIT} of {total} {label} positions. Use --export to see all.")
    print()


def print_positions_tables(closed_df: pd.DataFrame, active_df: pd.DataFrame) -> None:
    """Print closed and active positions tables to terminal (max 20 rows each)."""
    _print_positions_section('Closed Positions', closed_df, _CLOSED_COLS, 'closed')
    _print_positions_section('Active Positions', active_df, _ACTIVE_COLS, 'active')


def write_positions_xlsx(
    output_dir: str,
    closed_df: pd.DataFrame,
    active_df: pd.DataFrame,
) -> None:
    """Write closed and active positions to a two-sheet positions.xlsx."""
    path = os.path.join(output_dir, 'positions.xlsx')
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        closed_df.to_excel(writer, sheet_name='Closed', index=False)
        active_df.to_excel(writer, sheet_name='Active', index=False)
