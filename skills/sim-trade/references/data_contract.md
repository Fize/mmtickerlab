# Market data contract

The simulator treats provider data as untrusted input. A successful HTTP response alone is not sufficient for matching or valuation.

## Matching snapshot

A matching snapshot must contain:

- a supported six-digit A-share code and non-empty name;
- source and source timestamp in `Asia/Shanghai`;
- timestamp date equal to the order's trading date;
- age no greater than 30 seconds and no more than 5 seconds in the future;
- positive last price and previous close;
- explicit positive upper and lower price limits from the provider;
- a parseable listing date;
- `TRADING` status during order matching;
- at least one positive-price, positive-quantity level across the five-level bid/ask book.

An empty ask book at the upper limit and an empty bid book at the lower limit are valid matching snapshots when the opposite side exists, but provide no executable liquidity on that side. After the close, a snapshot may have no book and remain valid for valuation; it is never valid for matching. A security without explicit price limits is unsupported rather than guessed.

The East Money adapter requires provider status code `f292=2` for normal listing/trading eligibility and maps `f292=6` to `SUSPENDED`. Unknown values fail closed. A normal status without an executable book is `NO_BOOK`, not `TRADING`.

Store every snapshot used to evaluate an order in SQLite, including the raw provider payload. Never replace missing values with the order price, cost, previous close, zero, or an adjusted historical close.

## Valuation snapshot

Valuation requires positive identity and last-price fields. Its quote date must equal the latest official trading day on or before the report date. During an active session, apply the same 30-second freshness limit as matching. After the close or on a non-trading day, accept the latest official close snapshot.

If any held security fails valuation, return its valuation as `UNAVAILABLE`. Do not include a fabricated market value in account totals.

## Calendar

Use `AKShare.tool_trade_date_hist_sina` and persist the returned dates. A missing target date is not evidence that the exchange is closed when the calendar fetch itself failed. Fail closed until a successful calendar source or persisted date confirms the result.

## Provider implementation

The live adapter uses East Money for identity, listing date, explicit limits, and provider status. When East Money omits the order book for a normal security, it requires a Sina quote with the same code/name, previous close, a timestamp within 30 seconds, and a last-price difference no greater than the larger of CNY 0.05 or 0.5% of previous close before using its timestamp, last/pre-close, and five-level book. Any consistency mismatch or incomplete source fails closed. AKShare supplies the official trading-date series. Import `akshare_patch` before importing `akshare` so retries and East Money TLS handling are active.
