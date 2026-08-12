# Command reference

Place global options before the command:

```bash
simtrade.py [--json] [--db PATH] COMMAND
```

## Commands

```text
doctor [--code 600519]
quote CODE
account create --name NAME --cash AMOUNT
account list
account show [--account-id ID]
account configure [--account-id ID] [--commission-rate RATE] [--minimum-commission AMOUNT]
account archive --account-id ID --yes
order buy CODE SHARES --price PRICE [--account-id ID]
order sell CODE SHARES --price PRICE [--account-id ID]
order list [--account-id ID] [--status STATUS]
order show ORDER_ID
order cancel ORDER_ID
order process [--order-id ORDER_ID] [--account-id ID]
portfolio [--account-id ID]
history [--account-id ID] [--code CODE] [--limit N]
audit [--account-id ID]
```

## Order statuses

- `OPEN`: no visible executable quantity has filled.
- `PARTIALLY_FILLED`: some quantity filled; the remainder is still active.
- `FILLED`: the full quantity filled.
- `CANCELLED`: the user cancelled the remaining quantity.
- `EXPIRED`: the DAY order reached its expiry.
- `REJECTED`: validation rejected the attempted order before funds or shares were frozen.

All writes are SQLite transactions. Account archival requires an exact account ID, `--yes`, and no active orders.
