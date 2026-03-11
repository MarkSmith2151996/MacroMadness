# Claude Behavioral Instructions — Investment Research System

## On Session Start
1. Call `invest_schwab(action="sync")` to pull latest positions
2. Call `invest_schwab(action="token_status")` to check Schwab token health
3. Call `invest_calendar(action="list", days_ahead=7)` to show upcoming catalysts
4. Call `invest_get_portfolio()` to show current portfolio state

## When a New Ticker is Mentioned
1. Call `invest_screen_candidate(ticker, price, catalyst_type, conviction_pct)` immediately
2. Call `invest_market_data(type="quote", symbol=ticker)` for live price
3. Call `invest_market_data(type="fundamentals", symbol=ticker)` for key metrics

## When a Trade Plan is Finalized
1. Call `invest_create_trade_plan(...)` with all details — this auto-triggers:
   - Principle check against all active principles
   - Candidate screening with consensus/beta data
   - Correlation impact analysis (queued)
2. Review violations and flags before recommending execution
3. Never present a trade without stop-loss and at least one target

## When Order Details are Described
1. Call `invest_verify_order(...)` immediately to check against the trade plan
2. Flag any discrepancies before the user places the order

## When a Position is Closed
1. Call `invest_close_position(ticker, exit_price, exit_date, outcome)`
2. Present 5-dimension scores to the user for their assessment
3. Call the learning tools to record scores
4. Flag "bad_process_good_outcome" prominently — luck is not skill

## NEVER Do These
- Never add a position before a binary catalyst (earnings, FDA, etc.)
- Never widen a stop-loss — only tighten or maintain
- Never skip screening for any ticker
- Never present a trade idea without stop-loss and targets
- Never execute trades — this system is read-only research

## Scoring Rubric (5 Dimensions, 1-10 each)
- **Research Quality:** Thesis accuracy, primary sources used, risk identification
- **Entry Timing:** Price vs plan, technical confirmation waited for
- **Position Sizing:** Size matched conviction level appropriately
- **Stop-Loss Discipline:** Set before entry, never widened, honored when hit
- **Exit Timing:** Sold at targets, trailed stop properly, didn't panic

## Process vs Outcome
- Composite score >= 7.0 = good process
- Always flag "bad_process_good_outcome" — the most dangerous category
