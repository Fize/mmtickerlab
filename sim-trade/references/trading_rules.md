# Trading rules

Rule version: `cn-a-share-2026-01`

## Supported instruments

Support A-share stocks on Shanghai, Shenzhen, ChiNext, STAR, and Beijing exchanges. Reject funds, ETFs, bonds, options, B-shares, and unknown code ranges.

## Orders and matching

- Accept limit orders only.
- Require a ¥0.01 price tick.
- Require buy quantities in multiples of 100 shares.
- Require sell quantities in multiples of 100 unless the order liquidates all currently free sellable shares for that code.
- Match buys from ask 1 upward where ask price is at or below the limit.
- Match sells from bid 1 downward where bid price is at or above the limit.
- Limit each processing attempt to visible five-level quantity. Keep unfilled quantity open.
- Expire DAY orders after the trading date closes. Permit cancellation before expiration.

## Sessions and settlement

Use `Asia/Shanghai`. Accept placement and processing only on a confirmed trading day during 09:30–11:30 or 13:00–15:00. Shares bought on trading day T become sellable on the next confirmed trading day, not the next calendar day.

## Price limits

Require explicit provider upper/lower prices and validate the order price against them. Do not infer limits solely from the name or code. Reject securities in a no-price-limit period until a dedicated rule and reliable provider flag are implemented.

## Fees

Store account commission terms independently from exchange rules. Defaults:

- commission: 0.025% each side, minimum ¥5 per order;
- transfer fee: 0.001% each side;
- stamp tax: 0.05% on sells only.

Calculate with decimal arithmetic and round each order-level charge to fen using half-up rounding. For a partially filled order, charge only the incremental amount needed to bring cumulative commission to `max(minimum, cumulative turnover × rate)`.

Include buy fees in lot cost. Calculate sell realized P/L as net proceeds less FIFO disposed lot cost.

Official references:

- Shanghai Stock Exchange trading rules: https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml
- Shenzhen Stock Exchange trading rules: https://www.szse.cn/lawrules/rule/trade/current/t20260424_620190.html
- Ministry of Finance stamp-tax reduction: https://xj.mof.gov.cn/zcfagui/202311/t20231108_3915476.htm
- ChinaClear transfer fees: https://www.chinaclear.cn/zdjs/editor_file/20220701154723234.pdf
