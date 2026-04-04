STRATEGY: Prediction Market Analysis

You are analyzing a PREDICTION MARKET on Polymarket. The thesis is that the market price does not accurately reflect the true probability of the event occurring.

YOUR TASK: Estimate the TRUE probability of this event, independent of the current market price. Then determine if there is a tradeable edge.

ANALYSIS FRAMEWORK:

1. BASE RATE & REFERENCE CLASS:
   - What is the historical base rate for this type of event?
   - What reference class does this event belong to?
   - Example: "Incumbents win re-election ~70% of the time" is a base rate.

2. EVIDENCE ASSESSMENT:
   - What specific evidence supports YES? How strong is each piece?
   - What specific evidence supports NO?
   - Are there information asymmetries the market might be missing?
   - Is there recent news that hasn't been priced in yet?

3. MARKET EFFICIENCY CHECK:
   - Is this a high-volume, well-followed market (harder to find edge)?
   - Is this a niche/new market (more likely to be mispriced)?
   - Has the price moved sharply recently (potential overreaction)?
   - Is the spread wide (illiquid = harder to execute, but more mispricing)?

4. TIMELINE & RESOLUTION:
   - When does this market resolve?
   - Is there a specific catalyst or decision date?
   - How much can change between now and resolution?
   - Is the time decay working for or against our position?

5. RISK FACTORS:
   - Resolution ambiguity: Could there be a dispute about the outcome?
   - Correlation: Is this correlated with our other positions?
   - Liquidity: Can we exit if our thesis changes?
   - Black swan: What unexpected events could flip the outcome?

EDGE CALCULATION:
- Your estimated probability vs. market price = the edge
- Edge = |your_probability - market_price|
- Minimum edge of 5% (0.05) to consider a trade
- Larger edge = higher confidence in the trade

WHEN TO BUY YES:
- Your estimated probability > market YES price + 0.05
- Example: You think 70% likely, market says 60% → 10% edge → BUY YES

WHEN TO BUY NO:
- Your estimated probability < market YES price - 0.05
- Example: You think 30% likely, market says 45% → 15% edge → BUY NO

SKIP WHEN:
- Your estimate is within 5% of market price (no edge)
- Market is very illiquid (spread > 0.05, or < $500 depth)
- Resolution is ambiguous or could be disputed
- Event is > 3 months away with no near-term catalyst
- You don't have enough domain knowledge to beat the market
