# MarginX — System Architecture

## 1. Architecture Overview

MarginX will use a modular web application architecture.

The system will separate:

- User interface
- Application logic
- Financial calculation engine
- External APIs
- AI services
- Database
- Optional blockchain verification

The most important architectural principle is:

> **The financial engine is the source of truth for all numerical calculations.**

AI may explain or analyze the results, but it must not replace the deterministic financial engine.

---

# 2. Initial Technology Stack

## Frontend

- Next.js
- TypeScript
- React
- Tailwind CSS

## Backend

Next.js server-side functionality will initially handle:

- API endpoints
- Exchange-rate requests
- Server-side logic
- AI requests when implemented

## Financial Engine

The financial engine will be implemented as independent TypeScript modules.

It should not depend on React or UI components.

## Database

A database will be introduced in a later phase for:

- User accounts
- Saved analyses
- Analysis history
- User preferences

The initial MVP does not require a database.

## AI

The AI layer will be added after the deterministic financial engine is complete.

The AI will be responsible for:

- Explaining results
- Comparing scenarios
- Identifying important cost factors
- Answering questions about an analysis

## Deployment

The initial web application will be deployed using Vercel.

---

# 3. High-Level System

```text
                         ┌──────────────────────┐
                         │       User           │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │     MarginX UI       │
                         │   Next.js + React    │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   Application Layer  │
                         │ Validation / API     │
                         └──────────┬───────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
          ┌───────────────────┐          ┌───────────────────┐
          │ Financial Engine  │          │ Exchange Rate API │
          │                   │          │                   │
          │ Profit            │          │ Live FX Data      │
          │ Margin            │          │                   │
          │ Break-even        │          └───────────────────┘
          │ Scenarios         │
          └─────────┬─────────┘
                    │
                    ▼
          ┌───────────────────┐
          │     Results       │
          │                   │
          │ Profit            │
          │ Margin            │
          │ Costs             │
          │ Scenarios         │
          └─────────┬─────────┘
                    │
                    ▼
          ┌───────────────────┐
          │   AI Assistant    │
          │                   │
          │ Explain           │
          │ Analyze           │
          │ Compare           │
          └───────────────────┘
```

---

# 4. Application Layers

## 4.1 Presentation Layer

Responsible for everything the user interacts with.

Examples:

- Landing page
- Analysis form
- Results dashboard
- Scenario comparison
- Charts
- AI assistant interface

The presentation layer should not contain core financial formulas.

---

## 4.2 Application Layer

Responsible for coordinating application operations.

Responsibilities include:

- Receiving user input
- Validating input
- Calling the financial engine
- Requesting exchange-rate data
- Preparing results for the UI
- Calling the AI service when required

---

## 4.3 Financial Engine

This is the core of MarginX.

Responsibilities:

- Currency conversion
- Revenue calculation
- Cost calculation
- Profit calculation
- Margin calculation
- Break-even calculation
- Scenario calculation
- Sensitivity analysis

The financial engine must remain deterministic.

Example:

```text
Input
  ↓
Financial Engine
  ↓
Calculated Result
```

The same input should always produce the same output.

---

## 4.4 External Data Layer

This layer communicates with external services.

Initial example:

```text
MarginX
   │
   ▼
Exchange Rate API
   │
   ▼
Current Exchange Rate
```

The external API should not be called directly from UI components when a server-side API route can safely handle the request.

---

## 4.5 AI Layer

The AI layer will be added after the financial engine is stable.

The AI receives structured financial results.

Example:

```text
Financial Engine
       │
       ▼
Structured Analysis
       │
       ▼
      AI
       │
       ▼
Explanation
```

The AI should explain the calculations rather than independently inventing financial numbers.

---

# 5. Recommended Project Structure

The application will eventually follow a structure similar to:

```text
MarginX/
│
├── app/
│   ├── page.tsx
│   ├── analyze/
│   │   └── page.tsx
│   ├── results/
│   │   └── page.tsx
│   └── api/
│       ├── exchange-rate/
│       │   └── route.ts
│       └── ai/
│           └── route.ts
│
├── components/
│   ├── analysis-form/
│   ├── results/
│   ├── scenarios/
│   ├── charts/
│   └── ai-assistant/
│
├── lib/
│   ├── finance/
│   │   ├── currency.ts
│   │   ├── costs.ts
│   │   ├── profit.ts
│   │   ├── margin.ts
│   │   ├── breakeven.ts
│   │   └── scenarios.ts
│   │
│   ├── exchange-rate/
│   │   └── client.ts
│   │
│   └── ai/
│       └── client.ts
│
├── types/
│   ├── analysis.ts
│   ├── currency.ts
│   └── scenario.ts
│
├── tests/
│   └── finance/
│
├── docs/
│   ├── 01-PROJECT-SPECIFICATION.md
│   ├── 02-REQUIREMENTS.md
│   ├── 03-ARCHITECTURE.md
│   └── 04-FINANCIAL-ENGINE.md
│
├── .env.local
├── package.json
├── tsconfig.json
└── README.md
```

This is the **target architecture**.

We do not need to create every folder immediately.

---

# 6. Data Flow

The main analysis flow will be:

```text
User enters data
       ↓
Input validation
       ↓
Exchange rate obtained
       ↓
Currency conversion
       ↓
Financial engine
       ↓
Cost calculation
       ↓
Profit calculation
       ↓
Margin calculation
       ↓
Break-even calculation
       ↓
Scenario calculations
       ↓
Results
       ↓
UI visualization
```

---

# 7. AI Data Flow

When the AI assistant is introduced:

```text
User question
      ↓
AI API
      ↓
Structured MarginX Analysis
      ↓
AI Model
      ↓
Explanation / Analysis
      ↓
User
```

Example:

User:

> "Why is my profit margin so low?"

MarginX provides the AI with structured information such as:

```text
Revenue: $20
Total Cost: $18
Profit: $2
Margin: 10%

Shipping: $5
Platform Fee: $2
Payment Fee: $0.60
Other Costs: $1
```

The AI can then explain which costs are having the largest impact.

---

# 8. Database Architecture — Future

The database will be introduced after the core MVP.

Potential entities:

```text
User
 │
 └── Analyses
       │
       ├── Input Data
       ├── Financial Results
       ├── Scenarios
       └── Timestamps
```

Possible future tables:

```text
users
analyses
analysis_scenarios
```

The exact database schema will be defined when authentication and persistence are implemented.

---

# 9. Blockchain Architecture — Future

Blockchain verification is optional and will not be part of the MVP.

If implemented:

```text
Financial Analysis
       ↓
Canonical Data
       ↓
Cryptographic Hash
       ↓
Blockchain
       ↓
Verification Record
```

The actual financial information should remain off-chain.

Only the verification hash and required metadata should be recorded on-chain.

This allows users to verify that a finalized analysis has not been modified without exposing private financial information.

---

# 10. Security Architecture

MarginX should follow these principles:

### API Keys

External API keys must never be exposed to the browser.

They should be stored in environment variables.

```text
.env.local
```

### Server-Side Requests

Sensitive external API requests should be handled server-side where appropriate.

### Input Validation

All user-controlled inputs must be validated before calculations or external requests.

### Authentication

When accounts are introduced, users must only be able to access their own saved analyses.

---

# 11. Separation of Responsibilities

Each major component should have one primary responsibility.

```text
UI
↓
Collects and displays information

Application Layer
↓
Coordinates operations

Financial Engine
↓
Performs financial calculations

Exchange Service
↓
Provides exchange rates

Database
↓
Stores persistent data

AI Layer
↓
Explains and analyzes

Blockchain Layer
↓
Provides optional verification
```

This separation will allow MarginX to grow without rewriting the entire application.

---

# 12. Architectural Principles

MarginX will follow these principles:

1. **Financial calculations must be deterministic.**
2. **AI must not be the source of numerical truth.**
3. **UI components should not contain financial formulas.**
4. **External APIs should be isolated behind service modules.**
5. **Sensitive credentials must remain server-side.**
6. **Features should be added incrementally.**
7. **The MVP should remain small enough to complete quickly.**
8. **Future functionality should not unnecessarily complicate the MVP.**
9. **Core business logic should be independently testable.**
10. **The architecture should support future AI and blockchain integrations without requiring a complete rewrite.**
