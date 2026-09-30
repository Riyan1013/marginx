# MarginX — Financial Engine Specification

## 1. Purpose

The Financial Engine is the core calculation system of MarginX.

It receives structured financial inputs and produces deterministic financial results.

The engine is independent from:

- React
- Next.js UI components
- AI
- Database
- External APIs

The same inputs must always produce the same results.

---

# 2. Input Model

A financial analysis may contain the following inputs:

```text
Product / Service
Source Country
Target Country

Source Currency
Target Currency

Product Cost
Selling Price
Shipping Cost

Platform Fee
Payment Fee
Other Costs
Taxes

Exchange Rate
```

All monetary values should be normalized into a common calculation currency before the final analysis is performed.

---

# 3. Currency Conversion

The system must support conversion between the source and target currencies.

For example:

```text
1 USD = 85 INR
```

If the source cost is:

```text
₹500
```

Then:

```text
USD Cost = 500 / 85
         ≈ $5.88
```

The exact conversion direction depends on the selected source and target currencies.

The engine should explicitly represent the exchange-rate direction to avoid accidental inversion.

---

# 4. Revenue

Revenue is based on the selling price.

```text
Revenue = Selling Price
```

Example:

```text
Selling Price = $20

Revenue = $20
```

---

# 5. Platform Fee

Platform fees may be either:

- Percentage-based
- Fixed

## Percentage Fee

If the platform charges 10%:

```text
Platform Fee = Selling Price × Platform Fee Rate
```

Example:

```text
Selling Price = $20
Platform Fee = 10%

Platform Fee = 20 × 0.10
             = $2
```

## Fixed Fee

If the platform charges a fixed $2:

```text
Platform Fee = $2
```

---

# 6. Payment Processing Fee

Payment processing fees may also be:

- Percentage-based
- Fixed

## Percentage Fee

```text
Payment Fee = Selling Price × Payment Fee Rate
```

Example:

```text
Selling Price = $20
Payment Fee = 3%

Payment Fee = 20 × 0.03
            = $0.60
```

## Fixed Fee

```text
Payment Fee = Fixed Payment Fee
```

---

# 7. Total Cost

Total cost consists of all expenses associated with the transaction.

```text
Total Cost =
    Product Cost
  + Shipping Cost
  + Platform Fee
  + Payment Fee
  + Other Costs
  + Taxes
```

Example:

```text
Product Cost = $5.88
Shipping = $5.00
Platform Fee = $2.00
Payment Fee = $0.60
Other Costs = $1.00
Taxes = $0.00

Total Cost = $14.48
```

---

# 8. Net Profit

Net profit represents the amount remaining after all modeled costs.

```text
Net Profit = Revenue − Total Cost
```

Example:

```text
Revenue = $20
Total Cost = $14.48

Net Profit = 20 − 14.48
           = $5.52
```

---

# 9. Profit Margin

Profit margin represents profit as a percentage of revenue.

```text
Profit Margin =
(Net Profit / Revenue) × 100
```

Example:

```text
Net Profit = $5.52
Revenue = $20

Profit Margin =
(5.52 / 20) × 100

= 27.6%
```

If revenue is zero, the engine must not perform a division.

Instead, it should return an appropriate validation/calculation error.

---

# 10. Break-Even Selling Price

Break-even is the selling price at which:

```text
Profit = 0
```

The calculation becomes more important when percentage-based fees exist.

Assume:

```text
Fixed Costs = Product Cost
            + Shipping
            + Other Costs
            + Taxes

Percentage Fees = Platform Fee Rate
                + Payment Fee Rate
```

Then:

```text
Break-Even Price =
Fixed Costs / (1 − Percentage Fees)
```

Example:

```text
Product Cost = $5.88
Shipping = $5.00
Other Costs = $1.00

Fixed Costs = $11.88

Platform Fee = 10%
Payment Fee = 3%

Total Percentage Fees = 13%

Break-Even Price =
11.88 / (1 − 0.13)

= 11.88 / 0.87

≈ $13.66
```

At approximately $13.66:

```text
Revenue ≈ Total Cost
Profit ≈ $0
```

---

# 11. Fixed Payment Fees and Break-Even

If a payment provider charges both a percentage and a fixed fee, the fixed fee must be included in fixed costs.

Example:

```text
Product Cost = $5.88
Shipping = $5
Other Costs = $1
Fixed Payment Fee = $0.30

Fixed Costs = $12.18
```

If:

```text
Platform Fee = 10%
Payment Percentage Fee = 3%
```

Then:

```text
Break-Even Price =
12.18 / (1 − 0.13)

≈ $14.00
```

---

# 12. Profitability Status

The engine should classify the result using the calculated profit.

```text
If Profit > 0:
    PROFITABLE

If Profit = 0:
    BREAK-EVEN

If Profit < 0:
    LOSS
```

This status is descriptive only.

It does not represent financial advice.

---

# 13. Scenario Analysis

MarginX will support three primary scenarios:

```text
Best Case
Base Case
Worst Case
```

Each scenario contains its own financial assumptions.

---

## 13.1 Base Case

The Base Case represents the user's normal expected conditions.

Example:

```text
Selling Price = $20
Shipping = $5
Exchange Rate = 85 INR/USD
```

---

## 13.2 Best Case

The Best Case represents favorable assumptions.

Example:

```text
Selling Price = $22
Shipping = $4
Exchange Rate = 87 INR/USD
```

---

## 13.3 Worst Case

The Worst Case represents unfavorable assumptions.

Example:

```text
Selling Price = $18
Shipping = $7
Exchange Rate = 83 INR/USD
```

The system must not assume that every scenario changes every variable.

Only explicitly modified variables should change.

---

# 14. Scenario Calculation

Each scenario is processed independently through the same financial engine.

```text
Base Inputs
    │
    ├── Best Case Inputs ──→ Financial Engine ──→ Best Result
    │
    ├── Base Case Inputs ──→ Financial Engine ──→ Base Result
    │
    └── Worst Case Inputs ─→ Financial Engine ──→ Worst Result
```

This ensures that scenario calculations use the same formulas.

---

# 15. Scenario Comparison

The engine should produce comparable results.

Example:

| Metric     |   Best |   Base |  Worst |
| ---------- | -----: | -----: | -----: |
| Revenue    | $22.00 | $20.00 | $18.00 |
| Total Cost | $13.20 | $14.48 | $16.10 |
| Net Profit |  $8.80 |  $5.52 |  $1.90 |
| Margin     |  40.0% |  27.6% |  10.6% |

The UI can later visualize these values using charts or cards.

---

# 16. Sensitivity Analysis

A future version may evaluate how changing one variable affects profitability.

Example:

```text
Shipping Cost
$3 → $4 → $5 → $6 → $7
```

The engine calculates the resulting profit for each value.

Example:

| Shipping | Profit |
| -------: | -----: |
|       $3 |  $7.52 |
|       $4 |  $6.52 |
|       $5 |  $5.52 |
|       $6 |  $4.52 |
|       $7 |  $3.52 |

This allows MarginX to identify variables that strongly affect profitability.

---

# 17. Financial Result Object

The financial engine should eventually return a structured result similar to:

```typescript
{
  revenue: 20,
  totalCost: 14.48,
  netProfit: 5.52,
  profitMargin: 27.6,
  breakEvenPrice: 13.66,

  costs: {
    product: 5.88,
    shipping: 5,
    platformFee: 2,
    paymentFee: 0.60,
    other: 1,
    taxes: 0
  },

  status: "PROFITABLE"
}
```

This is an example structure.

The actual TypeScript types will be defined during implementation.

---

# 18. Monetary Precision

Financial calculations must avoid unnecessary floating-point errors.

For example, directly relying on binary floating-point arithmetic can produce results such as:

```text
0.1 + 0.2 = 0.30000000000000004
```

MarginX should use an appropriate monetary calculation strategy.

Possible implementation approaches include:

- Integer minor units such as cents
- Decimal arithmetic libraries
- Controlled rounding

The final implementation choice will be made during development.

---

# 19. Rounding

The engine should maintain sufficient internal precision during calculations.

Rounding should generally occur when presenting values to the user rather than after every intermediate calculation.

Example:

```text
Internal:
13.6578947368

Displayed:
$13.66
```

This prevents accumulated rounding errors.

---

# 20. Validation Rules

The financial engine should reject invalid inputs.

Examples:

### Selling Price

```text
Selling Price <= 0
```

should be rejected.

### Product Cost

```text
Product Cost < 0
```

should be rejected.

### Percentage Fees

Percentage values should be within a valid range.

For example:

```text
0% ≤ Fee ≤ 100%
```

### Exchange Rate

```text
Exchange Rate <= 0
```

should be rejected.

### Revenue

A zero revenue value must not be used to calculate profit margin.

---

# 21. Error Handling

The financial engine should return structured errors rather than silently producing invalid results.

Examples:

```text
INVALID_SELLING_PRICE
INVALID_PRODUCT_COST
INVALID_EXCHANGE_RATE
INVALID_FEE_PERCENTAGE
DIVISION_BY_ZERO
INVALID_CURRENCY
```

The UI can later convert these errors into user-friendly messages.

---

# 22. Testing Requirements

The financial engine must be independently testable.

Tests should cover:

### Currency Conversion

- Normal conversion
- Reverse conversion
- Invalid exchange rate

### Fees

- Percentage platform fee
- Fixed platform fee
- Percentage payment fee
- Fixed payment fee
- Combined fees

### Profit

- Positive profit
- Zero profit
- Negative profit

### Margin

- Normal margin
- Zero revenue
- Negative profit margin

### Break-Even

- No percentage fees
- Percentage fees
- Fixed payment fees
- Combined percentage and fixed fees

### Scenarios

- Best case
- Base case
- Worst case
- Scenario comparison

---

# 23. Core Principle

The MarginX financial engine follows one central rule:

> **Calculate first. Explain second.**

The financial engine produces the numerical truth.

The UI presents it.

The AI explains it.

Future blockchain functionality may verify it.

```text
Financial Inputs
       ↓
Financial Engine
       ↓
Verified Calculations
       ↓
┌───────────────┬───────────────┐
│               │               │
▼               ▼               ▼
UI              AI          Blockchain
Display       Explain       Verify
```

This separation ensures that advanced features do not compromise the reliability of the financial calculations.
