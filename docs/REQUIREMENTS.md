# MarginX — Requirements Specification

## 1. Functional Requirements

### FR-001 — Product / Service Information

The system shall allow the user to enter the name of the product or service being evaluated.

### FR-002 — Source Market

The system shall allow the user to specify the country or market where the product/service originates.

### FR-003 — Target Market

The system shall allow the user to specify the country or market where the product/service will be sold.

### FR-004 — Currency Selection

The system shall allow the user to select the source and target currencies.

### FR-005 — Product / Service Cost

The system shall allow the user to enter the original cost of the product or service.

### FR-006 — Selling Price

The system shall allow the user to enter the intended selling price in the target market.

### FR-007 — Shipping Cost

The system shall allow the user to enter estimated shipping or delivery costs.

### FR-008 — Platform Fees

The system shall allow the user to specify platform fees as either a percentage or fixed amount.

### FR-009 — Payment Processing Fees

The system shall allow the user to specify payment processing fees as either a percentage or fixed amount.

### FR-010 — Additional Costs

The system shall allow the user to enter additional expenses such as packaging, marketing, handling, or other operational costs.

### FR-011 — Taxes

The system shall allow simplified tax or tax-related costs to be included in the calculation.

> MarginX is an analytical tool and does not provide professional tax or legal advice.

### FR-012 — Exchange Rate

The system shall support currency conversion using an exchange rate.

The exchange rate may initially be entered manually and may later be retrieved from an external exchange-rate API.

### FR-013 — Currency Conversion

The system shall convert relevant values between the source and target currencies using the selected exchange rate.

### FR-014 — Revenue Calculation

The system shall calculate the expected revenue from the entered selling price.

### FR-015 — Total Cost Calculation

The system shall calculate the total estimated cost including applicable:

- Product/service cost
- Shipping
- Platform fees
- Payment fees
- Taxes
- Additional costs

### FR-016 — Net Profit

The system shall calculate estimated net profit:

**Net Profit = Revenue − Total Cost**

### FR-017 — Profit Margin

The system shall calculate estimated profit margin:

**Profit Margin = (Net Profit / Revenue) × 100**

### FR-018 — Break-Even Price

The system shall calculate the minimum selling price required to cover the estimated costs.

The calculation shall account for percentage-based fees where applicable.

### FR-019 — Cost Breakdown

The system shall display the individual cost components contributing to the total cost.

### FR-020 — Profitability Summary

The system shall provide a clear summary indicating whether the analyzed scenario produces:

- Positive profit
- Zero profit / break-even
- Negative profit / loss

### FR-021 — Scenario Analysis

The system shall allow users to evaluate multiple financial scenarios.

Initial scenarios shall include:

- Best Case
- Base Case
- Worst Case

### FR-022 — Scenario Variables

Scenario calculations may modify variables such as:

- Selling price
- Exchange rate
- Shipping cost
- Platform fees
- Payment fees
- Additional costs

### FR-023 — Scenario Comparison

The system shall allow users to compare scenario results including:

- Revenue
- Total cost
- Net profit
- Profit margin
- Break-even price

### FR-024 — Sensitivity Analysis

The system should eventually show how changes in important variables affect profitability.

Potential variables include:

- Exchange rate
- Shipping cost
- Selling price
- Platform fees

### FR-025 — Exchange Rate Data

When live exchange-rate data is implemented, the system shall record:

- Exchange rate
- Data source
- Retrieval timestamp

### FR-026 — External API Failure Handling

If an external exchange-rate service is unavailable, the system shall provide an understandable error message and prevent unreliable calculations.

### FR-027 — Input Validation

The system shall validate:

- Required fields
- Numeric values
- Currency selections
- Positive/valid monetary values
- Percentage ranges
- Scenario inputs

### FR-028 — Calculation Accuracy

The financial engine shall use deterministic calculations so that identical inputs always produce identical results.

### FR-029 — AI Assistant

The system may provide an AI assistant capable of:

- Explaining calculation results
- Explaining major cost factors
- Comparing scenarios
- Discussing profitability changes
- Answering questions about the analysis
- Extracting financial inputs from natural-language descriptions

The AI shall not be the authoritative source for numerical calculations.

### FR-030 — Saved Analyses

A future version shall allow authenticated users to save financial analyses.

### FR-031 — Analysis History

A future version shall allow users to view previously saved analyses.

### FR-032 — User Dashboard

A future version shall provide a dashboard containing saved analyses and financial insights.

### FR-033 — Blockchain Verification

A future version may provide verification of finalized analyses using a cryptographic hash recorded on a blockchain.

Sensitive financial information shall not be stored directly on-chain.

---

# 2. Non-Functional Requirements

### NFR-001 — Accuracy

Financial calculations shall be deterministic and reproducible.

### NFR-002 — Numerical Precision

The financial engine shall use appropriate decimal handling for monetary calculations and minimize floating-point precision errors.

### NFR-003 — Performance

Normal financial calculations should complete immediately without noticeable delay.

### NFR-004 — Reliability

The system shall handle failures from external services gracefully.

### NFR-005 — Security

The system shall:

- Protect API keys and secrets.
- Validate user input.
- Avoid exposing sensitive server-side credentials.
- Isolate user data when authentication is implemented.

### NFR-006 — Maintainability

The financial calculation engine shall remain separated from:

- UI components
- API routes
- Database logic
- AI functionality

### NFR-007 — Testability

Core financial formulas shall be covered by automated tests.

### NFR-008 — Error Handling

Errors shall be presented in a clear and understandable manner.

### NFR-009 — Usability

The interface should make financial results easy to understand without requiring advanced financial knowledge.

### NFR-010 — Responsive Design

The application shall function on:

- Desktop
- Tablet
- Mobile

### NFR-011 — Accessibility

The interface should provide:

- Readable text
- Clear labels
- Keyboard accessibility
- Visible focus states
- Understandable validation messages

### NFR-012 — Deployment

The initial application shall be compatible with Vercel Hobby for deployment.

### NFR-013 — Scalability

The architecture should allow the system to evolve from a simple calculator into a larger financial intelligence platform.

---

# 3. Project Constraints

MarginX shall initially operate under the following constraints:

1. MarginX will not process real financial transactions.
2. MarginX will not hold user funds.
3. MarginX will not execute trades.
4. MarginX will not provide personalized financial advice.
5. Tax calculations are estimates and are not professional tax advice.
6. Exchange-rate data may have delays depending on the external data provider.
7. Blockchain functionality is not required for the initial MVP.
8. Authentication and database functionality are not required for the first financial-engine version.

---

# 4. MVP Requirements

The first working version of MarginX shall contain:

- Product/service input
- Source country
- Target country
- Source currency
- Target currency
- Product/service cost
- Selling price
- Shipping cost
- Platform fee
- Payment fee
- Additional costs
- Exchange rate
- Revenue calculation
- Total cost calculation
- Net profit calculation
- Profit margin calculation
- Break-even calculation
- Cost breakdown
- Best/Base/Worst scenarios
- Basic input validation

The MVP shall **not** require:

- Authentication
- Database
- AI
- Blockchain
- Real payments
- Real trading
- Complex tax systems

---

# 5. Acceptance Criteria

MarginX will be considered ready for the initial MVP when:

- A user can enter a complete financial scenario.
- The system validates the provided inputs.
- Currency conversion works correctly.
- Total costs are calculated correctly.
- Net profit is calculated correctly.
- Profit margin is calculated correctly.
- Break-even price is calculated correctly.
- Individual costs are displayed clearly.
- Best, Base, and Worst scenarios can be compared.
- Invalid inputs produce understandable errors.
- Identical inputs produce identical results.
- The financial engine can be tested independently from the UI.
- The application can be deployed to Vercel.

---

# 6. Requirement Priority

### Must Have

Core MVP functionality:

- Financial inputs
- Currency conversion
- Cost calculation
- Profit calculation
- Margin calculation
- Break-even calculation
- Scenario analysis
- Validation
- Responsive UI

### Should Have

Features that significantly improve the product:

- Live exchange rates
- Sensitivity analysis
- Charts
- Saved analyses
- Analysis history
- AI explanation

### Could Have

Advanced features:

- Market comparison
- Advanced financial risk indicators
- AI natural-language analysis
- Blockchain verification

### Not Planned for MVP

- Real payment processing
- Real trading
- Cryptocurrency transactions
- Holding user funds
- Automated financial transactions
