# poly_sniff

A CLI tool that sniffs out suspicious betting behavior on [Polymarket](https://polymarket.com) prediction markets. It scrapes transaction data for a given market, computes behavioral metrics for each user, and flags those whose trading patterns are suggestive of insider knowledge.

## How it works

poly_sniff pulls the top position holders for a market, retrieves their full transaction histories within that market, and runs four behavioral metrics against each user. Users who pass *all four* thresholds simultaneously are flagged and printed to terminal.

The core idea: an insider doesn't hedge, doesn't follow the crowd, and tends to act late. poly_sniff looks for exactly that — unidirectional conviction, contrarian pricing, capital concentration on one side, and disproportionate activity near resolution.

## Installation

```bash
# Install globally from GitHub
pip install git+https://github.com/agile-enigma/poly_sniff.git

# Or clone and install locally
git clone https://github.com/agile-enigma/poly_sniff.git
cd poly_sniff
pip install .

# Or editable install for development
pip install -e .
```

After installation, `poly_sniff` is available as a global command.

## Usage

```
poly_sniff <command> [options]
```

### Commands

| Command | Description |
|---------|-------------|
| `sniff` | Detect suspected insider traders in a market |
| `profile` | Look up closed and active positions for a wallet address |

---

### `sniff`

```
poly_sniff sniff <market_slug> [options]
```

#### Required

| Argument | Description |
|----------|-------------|
| `market_slug` | Slug of the Polymarket market to analyze. The final path segment found in a market event URL, e.g. `will-x-happen-by-date` in `polymarket.com/event/will-x-happen-by-date` |

#### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--reference-time` | — | Reference time for timing metrics (e.g. `"2025-03-15"` or `"2025-03-15 14:00"`). Overrides `closedTime` for resolved markets. Must not be in the future. Required for active markets. |
| `--resolved-outcome` | — | `Yes` or `No`. Only flag users whose dominant side matches the winning outcome. |
| `--position-side` | `Yes` | Which side's top position holders to scrape. |
| `--limit` | `20` | Number of top position holders to scrape. |
| `--late-window` | `24` | Hours before reference time that count as "late" trading. |
| `--min-directional` | `0.85` | Minimum Directional Consistency to flag. |
| `--min-dominant` | `0.90` | Minimum Dominant Side Ratio to flag. |
| `--max-conviction` | `0` | Maximum Price Conviction Score to flag. |
| `--min-late-volume` | `0.50` | Minimum Late Volume Ratio to flag. |
| `--export-profiles` | — | Export user profiles to `profiles.xlsx`. |
| `--export-transactions` | — | Export transaction data to `transactions.xlsx`. |
| `--export-scaffold` | — | Export hourly scaffold to `scaffold.xlsx`. |
| `--export-flagged` | — | Export flagged users with all metrics to `flagged_users.xlsx`. |
| `--export-all` | — | Export all four xlsx files. |

#### Reference time

The reference time anchors all timing metrics. It is resolved in this priority order:

1. **`--reference-time`** — user-supplied value always wins; must not be in the future
2. **`closedTime`** from the market API — used automatically when the market is resolved
3. **Error** — if the market is still active and no `--reference-time` is provided, the tool exits

This means `sniff` works on both resolved and active markets. For active markets, supply a `--reference-time` to define your analysis window.

#### Examples

```bash
# Basic run — prints flagged users to terminal
poly_sniff sniff will-x-happen-by-date

# Analyze an active market
poly_sniff sniff will-x-happen-by-date --reference-time "2025-03-15 14:00"

# Override reference time on a resolved market
poly_sniff sniff will-x-happen-by-date --reference-time "2025-03-14"

# Scrape top 50 No-side holders, flag only those who bet on the winning side
poly_sniff sniff will-x-happen-by-date --position-side No --limit 50 --resolved-outcome No

# Loosen thresholds to cast a wider net
poly_sniff sniff will-x-happen-by-date --min-directional 0.75 --min-dominant 0.80 --min-late-volume 0.30

# Export everything for further analysis in Tableau
poly_sniff sniff will-x-happen-by-date --export-all
```

---

### `profile`

```
poly_sniff profile <proxy_wallet> [options]
```

Look up the closed and active Polymarket positions for any wallet address.

#### Required

| Argument | Description |
|----------|-------------|
| `proxy_wallet` | Ethereum wallet address to look up. Must start with `0x` and be exactly 42 characters long. Validated before any API call. |

#### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--limit` | `20` | Maximum number of positions to fetch from each endpoint. Paginates automatically if the limit exceeds the API's per-request max (50 for closed, 500 for active). |
| `--export` | — | Export all positions to `positions.xlsx` (two sheets: Closed and Active). |
| `--active-only` | — | Fetch only active positions; skip closed positions. Mutually exclusive with `--closed-only`. |
| `--closed-only` | — | Fetch only closed positions; skip active positions. Mutually exclusive with `--active-only`. |

#### Examples

```bash
# Basic lookup — prints closed and active positions to terminal
poly_sniff profile 0xabc1234567890abcdef1234567890abcdef12345

# Fetch up to 200 positions per endpoint
poly_sniff profile 0xabc1234567890abcdef1234567890abcdef12345 --limit 200

# Active positions only
poly_sniff profile 0xabc1234567890abcdef1234567890abcdef12345 --active-only

# Closed positions only
poly_sniff profile 0xabc1234567890abcdef1234567890abcdef12345 --closed-only

# Export to xlsx
poly_sniff profile 0xabc1234567890abcdef1234567890abcdef12345 --export
```

---

## Terminal output

### sniff

poly_sniff flags users through a conjunctive filter — all four conditions must be satisfied simultaneously. A user who passes only two or three criteria is not flagged.

The four criteria are:

1. **Directional Consistency** ≥ 0.85
2. **Dominant Side Ratio** ≥ 0.90
3. **Price Conviction Score** < 0
4. **Late Volume Ratio** ≥ 0.50

All thresholds are configurable via CLI flags. Defaults live in config.py.

Each metric is detailed in the **Detection metrics** section below.

Optionally, if `--resolved-outcome` is provided, an additional filter is applied: only users whose dominant side matches the winning outcome are kept (bullish for Yes, bearish for No). When omitted, users are flagged in both directions, which is useful for pre-resolution analysis.

Flagged users are printed as a table in the CLI.

```
╭─────────────┬─────────────┬────────────┬──────────┬───────────────┬──────────────┬─────────────┬─────────────────────┬────────────────╮
│ User        │ Wallet      │ Joined     │ X Handle │ Dominant Side │ Realized PnL │ USDC Volume │ Intra-Market Trades │ Markets Traded │
├─────────────┼─────────────┼────────────┼──────────┼───────────────┼──────────────┼─────────────┼─────────────────────┼────────────────┤
│ suspectuser │ 0xa3f91...  │ 2025-02-28 │ @suspect │ bullish       │ 3100.00      │ 8420.50     │ 12                  │ 3              │
│ anonwhale   │ 0x7cb02...  │ 2025-03-01 │          │ bullish       │ 9800.00      │ 15300.00    │ 2                   │ 7              │
╰─────────────┴─────────────┴────────────┴──────────┴───────────────┴──────────────┴─────────────┴─────────────────────┴────────────────╯
```

### profile

Two tables are printed — closed positions first, then active. A maximum of 20 rows per table is shown in terminal. If results exceed 20, a message is printed below the table indicating the total count and suggesting `--export` to see all.

**Closed positions columns:** Title, Slug, Outcome, Avg Price, Total Bought, Realized PnL, Current Price

**Active positions columns:** Title, Slug, Size, Avg Price, Total Bought, Current Value, Cash PnL, % PnL, Realized PnL, Current Price

## Exports

### sniff

When any `--export-*` flag is set, xlsx files are placed in a timestamped folder:

```
polysniff_output/sniff/will-x_20250307_141523/
├── profiles.xlsx
├── transactions.xlsx
├── scaffold.xlsx
└── flagged_users.xlsx
```

The `flagged_users.xlsx` includes all metric values for each flagged user, not just the summary columns shown in terminal.

### profile

When `--export` is set, a single xlsx file with two sheets is written:

```
polysniff_output/profile/0xabc12_20250307_141523/
└── positions.xlsx   ← sheets: Closed, Active
```

Each sheet contains every field returned by the API — no column filtering or truncation. All fetched rows are included, not just the 20 shown in terminal.

## Detection metrics

poly_sniff uses four behavioral metrics. A user must trip *all four* to be flagged — any single metric alone could be innocent, but the combination is hard to explain away.

### Directional consistency

`abs(sum(netPosition)) / sum(abs(netPosition))`

Measures whether a user's trades all point in the same direction. A score of 1.0 means every trade was unidirectional. An insider doesn't flip back and forth — they know the answer and bet accordingly.

Threshold for user flagging is configurable via `--min-directional`.

### Dominant side ratio

Fraction of total USDC volume on the user's dominant side. Buying Yes and selling No both count as bullish; buying No and selling Yes both count as bearish. A ratio above 0.90 means the user committed nearly all their capital to one direction.

Threshold for user flagging is configured via `--min-dominant`.

### Price conviction score

USDC-weighted average of `(price - 0.50)`, flipped by trade side. A negative score means the user was buying at prices where the market hadn't yet moved in their direction — they were contrarian. Insiders trade *before* the market catches up, so they show up as contrarian. Someone buying Yes at 0.30 who turns out to be right is far more suspicious than someone buying Yes at 0.80.

Threshold for user flagging is configured via `--max-conviction`.

### Late volume ratio

Fraction of the user's total USDC volume placed within the final hours before the reference time (configurable via `--late-window`, which defaults to 24). Insiders often act close to resolution because that's when they receive or confirm their information.

Threshold for user flagging is configured via `--min-late-volume`.

### Resolved outcome filter

When `--resolved-outcome` is provided, an additional filter is applied: only users whose dominant side matches the winning outcome are flagged. Someone who bet heavily on the losing side with high confidence isn't an insider — they're just wrong.

## Scaffold export

The `--export-scaffold` option produces an hourly time-series grid (every hour × every user) suitable for Tableau line chart visualization. It includes cumulative position columns (`cumNetPosition`, `cumWeightedPosition`) that show how each user's directional exposure built up over time. An insider's cumulative position will look like a steady ramp in one direction, especially steepening near the end.

## Requirements

- Python 3.10+
- pandas
- openpyxl
- requests

## Disclaimer

This tool is for research and analysis purposes. Flagged users are not necessarily engaged in insider trading — the metrics identify behavioral patterns that *warrant further investigation*, not proof of wrongdoing.

## License

MIT
