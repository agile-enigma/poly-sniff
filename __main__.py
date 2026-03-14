import argparse
import sys

import pandas as pd

pd.set_option('future.no_silent_downcasting', True)

from . import config
from .data import loader, preprocessing, scraper
from .metrics import activity, conviction, directional, dominance, timing
from . import scaffold as scaffold_module
from . import output


def _merge(
    transactions_df: pd.DataFrame,
    metric_df: pd.DataFrame,
    join_on: str = 'proxyWallet',
) -> pd.DataFrame:
    """Drop pre-existing metric columns then left-merge metric_df by join_on."""
    new_cols = [c for c in metric_df.columns if c != join_on]
    transactions_df.drop(
        columns=[c for c in new_cols if c in transactions_df.columns], inplace=True
    )
    return transactions_df.merge(metric_df, on=join_on, how='left')


def _enrich_profile_sniff(
    transactions_df: pd.DataFrame, profile_row: dict
) -> pd.DataFrame:
    """Compute base columns for profile --sniff transactions.

    Mirrors preprocessing.enrich() but without the profile merge. Uses the
    per-trade reference_time column (tagged by scraper) to compute
    hoursBeforeResolution inline.
    """
    df = transactions_df.copy()

    # Convert unix timestamp to US/Eastern timezone-naive datetime
    df['timestamp'] = (
        pd.to_datetime(df['timestamp'], unit='s')
        .dt.tz_localize('UTC')
        .dt.tz_convert('US/Eastern')
        .dt.tz_localize(None)
    )
    df.rename(columns={'timestamp': 'timestamp_est'}, inplace=True)

    # Broadcast joinDate from profile_row to every row
    join_date_utc = profile_row.get('joinDate_utc')
    if join_date_utc:
        df['joinDate_est'] = (
            pd.to_datetime(join_date_utc, utc=True)
            .tz_convert('US/Eastern')
            .tz_localize(None)
        )
    else:
        df['joinDate_est'] = pd.NaT

    # USDC value of each trade
    df['usdcSize'] = df['size'] * df['price']

    # Vectorized side/outcome boolean masks
    is_yes = df['outcome'] == 'Yes'
    is_no = df['outcome'] == 'No'
    is_buy = df['side'] == 'BUY'
    is_sell = df['side'] == 'SELL'

    df['yesBought'] = df['size'].where(is_yes & is_buy, 0)
    df['yesSold'] = df['size'].where(is_yes & is_sell, 0)
    df['noBought'] = df['size'].where(is_no & is_buy, 0)
    df['noSold'] = df['size'].where(is_no & is_sell, 0)

    df['netYes'] = (
        df['size'].where(is_yes & is_buy, 0)
        - df['size'].where(is_yes & is_sell, 0)
    )
    df['netNo'] = (
        df['size'].where(is_no & is_buy, 0)
        - df['size'].where(is_no & is_sell, 0)
    )

    df['weightedNetYes'] = df['netYes'] * df['price']
    df['weightedNetNo'] = df['netNo'] * df['price']

    side_sign = df['side'].map({'BUY': 1, 'SELL': -1})
    outcome_sign = df['outcome'].map({'Yes': 1, 'No': -1})
    df['netPosition'] = df['size'] * side_sign * outcome_sign
    df['weightedPosition'] = df['netPosition'] * df['price']

    # Per-trade hoursBeforeResolution using tagged reference_time
    df['hoursBeforeResolution'] = (
        (df['reference_time'] - df['timestamp_est']).dt.total_seconds() / 3600
    )

    return df


def run(args: argparse.Namespace) -> None:
    # 1. Scrape
    print(f"\nFetching data for market '{args.market_slug}'...")
    market = scraper.fetch_market_info(args.market_slug)
    condition_id = market['conditionId']
    reference_time = scraper.get_reference_time(market, args.reference_time)
    print(f"  conditionId  : {condition_id}")
    print(f"  reference    : {reference_time}")
    profile_rows, transaction_rows = scraper.fetch(
        condition_id,
        position_side=args.position_side,
        limit=args.limit,
    )
    print(f"  holders      : {len(profile_rows)}")

    # 2. Load
    profiles_df = loader.parse_profiles(profile_rows)
    transactions_df = loader.parse_transactions(transaction_rows)
    print(f"  transactions : {len(transactions_df)}")

    # 3. Preprocess — merge profiles, compute base columns
    transactions_df = preprocessing.enrich(transactions_df, profiles_df)

    # 4. Add per-transaction timing column
    transactions_df = timing.add_hours_before_resolution(transactions_df, reference_time)

    # 5. Compute per-user metrics
    print("\nComputing metrics...")
    directional_df = directional.compute(transactions_df)
    dominance_df = dominance.compute(transactions_df)
    conviction_df = conviction.compute(transactions_df)
    timing_df = timing.compute(transactions_df, late_window=args.late_window)
    activity_df = activity.compute(transactions_df)

    # 6. Merge metrics back — drop stale columns before each merge
    for metric_df in [directional_df, dominance_df, conviction_df, timing_df, activity_df]:
        transactions_df = _merge(transactions_df, metric_df)

    # 7. Flag users
    flagged_df = output.flag_users(
        transactions_df,
        min_directional=args.min_directional,
        min_dominant=args.min_dominant,
        max_conviction=args.max_conviction,
        min_late_volume=args.min_late_volume,
        resolved_outcome=args.resolved_outcome,
    )
    print(f"  flagged      : {len(flagged_df)} user(s)")

    # 8. Print to terminal
    print()
    output.print_table(flagged_df)

    # 9. Export xlsx files if requested
    do_export = args.export_all or any([
        args.export_profiles,
        args.export_transactions,
        args.export_scaffold,
        args.export_flagged,
    ])

    if do_export:
        output_dir = output.make_output_dir(condition_id, subcommand='sniff')

        scaffold_df = None
        if args.export_all or args.export_scaffold:
            scaffold_df = scaffold_module.build(transactions_df)

        output.write_sniff_exports(
            output_dir,
            profiles_df=profiles_df if (args.export_all or args.export_profiles) else None,
            transactions_df=transactions_df if (args.export_all or args.export_transactions) else None,
            scaffold_df=scaffold_df,
            flagged_df=flagged_df if (args.export_all or args.export_flagged) else None,
        )
        print(f"\nExports written to: {output_dir}/")


def run_profile(args: argparse.Namespace) -> None:
    # Validate wallet address
    if not (args.proxy_wallet.startswith('0x') and len(args.proxy_wallet) == 42):
        sys.exit("Error: proxyWallet must start with '0x' and be 42 characters long.")

    # Warn if threshold flags are provided without --sniff
    if not args.sniff:
        threshold_flags = [
            ('late_window', '--late-window'),
            ('min_directional', '--min-directional'),
            ('min_dominant', '--min-dominant'),
            ('max_conviction', '--max-conviction'),
            ('min_late_volume', '--min-late-volume'),
        ]
        for attr, flag in threshold_flags:
            if getattr(args, attr, None) is not None:
                print(f"Warning: {flag} has no effect without --sniff.")

    print(f"\nFetching positions for wallet '{args.proxy_wallet}'...")
    closed_rows, active_rows = scraper.fetch_profile_positions(
        args.proxy_wallet,
        limit=args.limit,
        fetch_closed=not args.active_only,
        fetch_active=not args.closed_only,
    )
    print(f"  closed positions : {len(closed_rows)}")
    print(f"  active positions : {len(active_rows)}")

    closed_df = pd.DataFrame(closed_rows) if closed_rows else pd.DataFrame()
    active_df = pd.DataFrame(active_rows) if active_rows else pd.DataFrame()

    if not args.sniff:
        print()
        output.print_positions_tables(closed_df, active_df)
        if args.export_positions:
            output_dir = output.make_output_dir(args.proxy_wallet, subcommand='profile')
            output.write_profile_exports(output_dir, closed_df=closed_df, active_df=active_df)
            print(f"Export written to: {output_dir}/")
        return

    # ── sniff mode ────────────────────────────────────────────────────────────
    if args.active_only:
        sys.exit("Error: --active-only is incompatible with --sniff (only closed markets can be analyzed).")

    if not closed_rows:
        sys.exit("No closed positions found for this wallet.")

    if active_rows:
        print("Warning: --sniff only analyzes closed markets. Active positions will be skipped.")

    print()
    profile_row, transaction_rows = scraper.fetch_profile_sniff_data(
        args.proxy_wallet, closed_rows
    )

    if not transaction_rows:
        sys.exit("No transactions found for this wallet's closed markets.")

    transactions_df = loader.parse_transactions(transaction_rows)
    transactions_df = _enrich_profile_sniff(transactions_df, profile_row)

    # Resolve threshold values (user override or config default)
    late_window = args.late_window if args.late_window is not None else config.LATE_WINDOW_HOURS
    min_directional = args.min_directional if args.min_directional is not None else config.MIN_DIRECTIONAL
    min_dominant = args.min_dominant if args.min_dominant is not None else config.MIN_DOMINANT
    max_conviction = args.max_conviction if args.max_conviction is not None else config.MAX_CONVICTION
    min_late_volume = args.min_late_volume if args.min_late_volume is not None else config.MIN_LATE_VOLUME

    # Compute per-market metrics
    print("\nComputing metrics...")
    directional_df = directional.compute(transactions_df, group_by='conditionId')
    dominance_df = dominance.compute(transactions_df, group_by='conditionId')
    conviction_df = conviction.compute(transactions_df, group_by='conditionId')
    timing_df = timing.compute(transactions_df, late_window=late_window, group_by='conditionId')
    activity_df = activity.compute(transactions_df, group_by='conditionId')

    for metric_df in [directional_df, dominance_df, conviction_df, timing_df, activity_df]:
        transactions_df = _merge(transactions_df, metric_df, join_on='conditionId')

    flagged_df = output.flag_markets(
        transactions_df,
        min_directional=min_directional,
        min_dominant=min_dominant,
        max_conviction=max_conviction,
        min_late_volume=min_late_volume,
    )
    print(f"  flagged markets : {len(flagged_df)}")

    print()
    output.print_flagged_markets_table(flagged_df)

    # Exports
    do_export = args.export_all or any([
        args.export_positions,
        args.export_profile,
        args.export_transactions,
        args.export_scaffold,
        args.export_flagged,
    ])

    if do_export:
        output_dir = output.make_output_dir(args.proxy_wallet, subcommand='profile')

        scaffold_df = None
        if args.export_all or args.export_scaffold:
            scaffold_df = scaffold_module.build_profile_sniff(transactions_df)

        profile_df = pd.DataFrame([profile_row])
        output.write_profile_exports(
            output_dir,
            closed_df=closed_df if (args.export_all or args.export_positions) else None,
            active_df=None,  # sniff only exports closed positions
            profiles_df=profile_df if (args.export_all or args.export_profile) else None,
            transactions_df=transactions_df if (args.export_all or args.export_transactions) else None,
            scaffold_df=scaffold_df,
            flagged_df=flagged_df if (args.export_all or args.export_flagged) else None,
        )
        print(f"\nExports written to: {output_dir}/")


# def _fmt(prog):
#     return argparse.HelpFormatter(prog, max_help_position=40, width=115)

def _fmt(prog):
    class BlankLineFormatter(argparse.HelpFormatter):
        def _split_lines(self, text, width):
            lines = super()._split_lines(text, width)
            return lines + ['']
    return BlankLineFormatter(prog, max_help_position=40, width=115)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Polymarket analysis toolkit',
        formatter_class=_fmt,
    )
    subparsers = parser.add_subparsers(dest='command', metavar='<command>')
    subparsers.required = True

    # ── sniff subcommand ──────────────────────────────────────────────────────
    sniff = subparsers.add_parser(
        'sniff',
        help='Detect suspected insider traders in a market',
        formatter_class=_fmt,
    )
    sniff.add_argument(
        'market_slug',
        help='slug of the Polymarket market to analyze',
    )
    sniff.add_argument(
        '--reference-time',
        default=None,
        metavar='DATETIME',
        help='Reference time for timing metrics (e.g. "2025-03-15" or "2025-03-15 14:00"). '
             'Overrides closedTime for resolved markets. Must not be in the future.',
    )
    sniff.add_argument(
        '--resolved-outcome',
        choices=['Yes', 'No'],
        default=None,
        metavar='STR',
        help='If provided, only flags users whose dominant side matches the winning outcome',
    )
    sniff.add_argument(
        '--position-side',
        choices=['Yes', 'No'],
        default=config.POSITION_SIDE,
        metavar='STR',
        help="Which side's top position holders to scrape (default: Yes)",
    )
    sniff.add_argument(
        '--limit',
        type=int,
        default=config.SCRAPER_LIMIT,
        metavar='INT',
        help='Number of top position holders to scrape (default: 20)',
    )
    sniff.add_argument(
        '--late-window',
        type=int,
        default=config.LATE_WINDOW_HOURS,
        metavar='HOURS',
        help='Hours before resolution that count as "late" trading (default: 24)',
    )
    sniff.add_argument(
        '--min-directional',
        type=float,
        default=config.MIN_DIRECTIONAL,
        metavar='FLOAT',
        help='Minimum User Directional Consistency threshold to flag (default: 0.85)',
    )
    sniff.add_argument(
        '--min-dominant',
        type=float,
        default=config.MIN_DOMINANT,
        metavar='FLOAT',
        help='Minimum User Dominant Side Ratio threshold to flag (default: 0.90)',
    )
    sniff.add_argument(
        '--max-conviction',
        type=float,
        default=config.MAX_CONVICTION,
        metavar='FLOAT',
        help='Maximum User Max Conviction threshold to flag (default: 0)',
    )
    sniff.add_argument(
        '--min-late-volume',
        type=float,
        default=config.MIN_LATE_VOLUME,
        metavar='FLOAT',
        help='Minimum User Late Volume ratio to flag (default: 0.50)',
    )
    sniff.add_argument(
        '--export-profiles',
        action='store_true',
        help='Export user profile information to profiles.xlsx',
    )
    sniff.add_argument(
        '--export-transactions',
        action='store_true',
        help='Export transactions to transactions.xlsx',
    )
    sniff.add_argument(
        '--export-scaffold',
        action='store_true',
        help='Export hourly scaffold to scaffold.xlsx',
    )
    sniff.add_argument(
        '--export-flagged',
        action='store_true',
        help='Export flagged users table to flagged_users.xlsx',
    )
    sniff.add_argument(
        '--export-all',
        action='store_true',
        help='Export all four xlsx files',
    )
    sniff.set_defaults(func=run)

    # ── profile subcommand ────────────────────────────────────────────────────
    profile = subparsers.add_parser(
        'profile',
        help='Look up positions for a wallet; optionally flag suspicious markets (--sniff)',
        formatter_class=_fmt,
    )
    profile.add_argument(
        'proxy_wallet',
        help='Ethereum wallet address to look up (must start with 0x, 42 characters)',
    )
    profile.add_argument(
        '--sniff',
        action='store_true',
        help='Analyze closed markets for suspicious trading behavior for queried user',
    )
    profile_scope = profile.add_mutually_exclusive_group()
    profile_scope.add_argument(
        '--active-only',
        action='store_true',
        help='Fetch only active positions; skip closed positions. Not applicable when using --sniff',
    )
    profile_scope.add_argument(
        '--closed-only',
        action='store_true',
        help='Fetch only closed positions; skip active positions. Redundant when using --sniff',
    )
    profile.add_argument(
        '--limit',
        type=int,
        default=config.SCRAPER_LIMIT,
        metavar='INT',
        help='Maximum number of closed and active positions to fetch, as applicable (default: 20)',
    )
    profile.add_argument(
        '--late-window',
        type=int,
        default=config.LATE_WINDOW_HOURS,
        metavar='HOURS',
        help='Hours before resolution that count as "late" trading (default: 24). Requires --sniff.',
    )
    profile.add_argument(
        '--min-directional',
        type=float,
        default=config.MIN_DIRECTIONAL,
        metavar='FLOAT',
        help='Minimum User Directional Consistency threshold to flag (default: 0.85). Requires --sniff.',
    )
    profile.add_argument(
        '--min-dominant',
        type=float,
        default=config.MIN_DOMINANT,
        metavar='FLOAT',
        help='Minimum User Dominant Side Ratio threshold to flag (default: 0.90). Requires --sniff.',
    )
    profile.add_argument(
        '--max-conviction',
        type=float,
        default=config.MAX_CONVICTION,
        metavar='FLOAT',
        help='Maximum User Price Conviction threshold to flag (default: 0). Requires --sniff.',
    )
    profile.add_argument(
        '--min-late-volume',
        type=float,
        default=config.MIN_LATE_VOLUME,
        metavar='FLOAT',
        help='Minimum User Late Volume Ratio threshold to flag (default: 0.50). Requires --sniff.',
    )
    profile.add_argument(
        '--export-positions',
        action='store_true',
        help='Export positions to positions.xlsx. With --sniff, exports only closed positions.',
    )
    profile.add_argument(
        '--export-profile',
        action='store_true',
        help='Export user profile information to profile.xlsx. Requires --sniff.',
    )
    profile.add_argument(
        '--export-transactions',
        action='store_true',
        help='Export transactions to transactions.xlsx. Requires --sniff.',
    )
    profile.add_argument(
        '--export-scaffold',
        action='store_true',
        help='Export hourly scaffold to scaffold.xlsx. Requires --sniff.',
    )
    profile.add_argument(
        '--export-flagged',
        action='store_true',
        help='Export flagged markets to flagged_markets.xlsx. Requires --sniff.',
    )
    profile.add_argument(
        '--export-all',
        action='store_true',
        help='Export all xlsx files. Only applicable when using --sniff.',
    )
    profile.set_defaults(func=run_profile)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
