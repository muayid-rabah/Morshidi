# Institutional Capacity Pressure Policy

Policy version: **1.0**  
Phase: **P7.1 — Policy and Contracts Only**  
Predecessor phases: Phase P6.1 (Demand Policy), P6.2 (Demand Engine), P6.4 (Persistence), P6.5 (Institutional API).

---

## 1. Purpose

This document defines the exact mathematical, logical, and privacy contracts for **Capacity Pressure Analysis** within Morshidi's Institutional Intelligence layer.

Capacity Pressure Analysis compares student registration intent declarations against supplied course section capacity. It surfaces operational alignment and potential seat shortages while strictly prohibiting autonomous section creation, enrollment forecasting, or staffing mandates.

---

## 2. Core Definitions

1. **Declared Demand ($D$):** The count of distinct, valid, active intent owners who have declared an intention to register for a specific course in a specific planning period. Sourced strictly from the P6.2 Institutional Demand engine (`COURSE_INTENT_OWNER_COUNT`).
2. **Supplied Capacity ($C$):** The total verified scheduled seat capacity for a course in that planning period, supplied via external institutional facts (`CapacityFact`).
3. **Declared Capacity Deficit ($\Delta_{\text{cap}}$):** The factual arithmetic difference between declared demand and supplied capacity:
   $$\Delta_{\text{cap}} = D - C$$

---

## 3. Exact Arithmetic and Gap Semantics

### 3.1 Positive Deficit ($\Delta_{\text{cap}} > 0$)
- **Meaning:** Declared student intent exceeds supplied capacity.
- **Interpretation:** Indicates potential capacity pressure if all declaring students attempt official registration.
- **Factual Signal:** `DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY`.
- **Prohibited Claim:** Does NOT guarantee that sections will fill or that waitlists will materialize.

### 3.2 Balanced or Negative Deficit ($\Delta_{\text{cap}} \le 0$)
- **Meaning:** Supplied capacity meets or exceeds declared student intent.
- **Interpretation:** Sufficient capacity exists to accommodate all observed declared intents.
- **Factual Signal:** `WITHIN_SUPPLIED_CAPACITY`.
- **Prohibited Claim:** A negative deficit ($\Delta_{\text{cap}} < 0$) must **NEVER** be labeled as "overstaffed", "wasted resources", or "excessive capacity". It simply indicates available capacity headroom relative to observed intent.

---

## 4. Edge Cases: Missing, Zero, and Not-Offered Capacity

### 4.1 Missing Capacity Facts (Offered or Offering Unknown)
- **Condition:** No `CapacityFact` record is supplied for the target course and period, AND the course offering state is either verified `OFFERED` or `UNAVAILABLE` (unknown).
- **System Behavior:**
  - $\Delta_{\text{cap}}$ status is `INSUFFICIENT_DATA`.
  - Value is `None` (absent).
  - Emits data quality flag `MISSING_CAPACITY_DATA`.
  - State is `NO_CAPACITY_DATA`.
  - Triggers data-hygiene alert `INST_ALERT_CAPACITY_DATA_MISSING`.
- **Strict Rule:** Missing capacity is **NEVER** treated as $C = 0$.

### 4.2 Verified Zero Capacity ($C = 0$)
- **Condition:** An explicit `CapacityFact` exists with `capacity = 0` (e.g., department decided not to offer sections despite course being listed).
- **System Behavior:**
  - If $D > 0$: $\Delta_{\text{cap}} = D - 0 = D$.
  - State is `DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY`.
  - Ratio $\frac{D}{C}$ is `NOT_APPLICABLE` (division by zero is undefined).
  - Triggers deterministic alert `INST_ALERT_ZERO_CAPACITY_WITH_DEMAND`.

### 4.3 Verified Not-Offered Course (`OfferingFact.status == NOT_OFFERED`)
- **Condition:** An authoritative `VERIFIED_INSTITUTIONAL_FACT` explicitly establishes that the course is **NOT OFFERED** in the target planning period.
- **System Behavior:**
  - If no capacity fact is supplied: Capacity status is **`NOT_APPLICABLE`** (not a missing-data defect).
  - Deficit $\Delta_{\text{cap}}$ is `NOT_APPLICABLE`.
  - Ratio $\frac{D}{C}$ is `NOT_APPLICABLE`.
  - State is `NOT_APPLICABLE`.
  - Alert `INST_ALERT_CAPACITY_DATA_MISSING` is **NOT EMITTED** (demanding capacity for a verified non-offered course is semantically invalid).

### 4.4 Missing Offering Data is NEVER Inferred as Not-Offered
- **Strict Prohibition:** If offering data is absent (`OfferingFact is None`), the offering state is strictly `UNAVAILABLE` / `UNKNOWN`.
- The system must **NEVER** assume an unrecorded course is `NOT_OFFERED`.
- In this case, `INST_ALERT_OFFERING_DATA_MISSING` is emitted, and missing capacity remains treated under Section 4.1 (`INSUFFICIENT_DATA`), emitting `INST_ALERT_CAPACITY_DATA_MISSING`.

---

## 5. Privacy Suppression and Propagation

Capacity Pressure Analysis is strictly subordinate to student privacy:

1. **Suppression Invariant:** If the underlying demand count $D$ is suppressed for privacy ($0 < D < k$), then:
   - Deficit $\Delta_{\text{cap}}$ is `SUPPRESSED`.
   - Ratio $\frac{D}{C}$ is `SUPPRESSED`.
   - Capacity pressure state is `SUPPRESSED`.
2. **Reverse-Engineering Prevention:** Exposing $\Delta_{\text{cap}}$ alongside known capacity $C$ would reveal $D = \Delta_{\text{cap}} + C$. Therefore, whole-result suppression must propagate to all capacity arithmetic.

---

## 6. Demand-to-Capacity Ratio Semantics

When both $D$ and $C$ are available, unsuppressed, and $C > 0$, the system computes:
$$\text{Ratio} = \frac{D}{C}$$

- **Labeling Requirement:** Must be displayed as `"Declared Intent to Supplied Capacity Ratio"`.
- **Prohibition:** Must **NEVER** be called "Section Utilization", "Class Fill Rate", or "Enrollment Efficiency".
- **Precision:** Rounded to four decimal places.

---

## 7. Operational Boundaries & Non-Goals

1. **No Section Recommendations:** The system must never recommend: *"Open 2 more sections of Course X"*. It may only state: *"Declared demand exceeds supplied capacity by 45 seats"*.
2. **No Staffing or Faculty Inferences:** The system must never infer instructor workload, teaching assignments, or departmental hiring needs.
3. **No Enrollment Guarantees:** Student intent declarations are non-binding; they do not guarantee actual registration.
4. **Partial Adoption Acknowledgment:** All outputs must reflect the caveat `OBSERVED_INTENTS_ONLY` unless verified institutional census data is supplied.

---

## 8. Deterministic Capacity Pressure State Machine

```text
Inputs: Demand D (Status, Value), Capacity C (Fact Present, Value), Offering O (OFFERED, NOT_OFFERED, UNAVAILABLE)

+-----------------------+-----------------------+-----------------------+---------------------------------------------+
| Demand Status         | Offering Status       | Capacity Condition    | Capacity Pressure State                     |
+-----------------------+-----------------------+-----------------------+---------------------------------------------+
| Any                   | NOT_OFFERED           | Missing               | NOT_APPLICABLE                              |
| SUPPRESSED            | Any != NOT_OFFERED    | Any                   | SUPPRESSED                                  |
| INSUFFICIENT_DATA     | Any != NOT_OFFERED    | Any                   | INSUFFICIENT_DATA                           |
| AVAILABLE (D = 0)     | OFFERED / UNAVAILABLE | Missing               | NO_CAPACITY_DATA                            |
| AVAILABLE (D = 0)     | Any                   | C >= 0                | WITHIN_SUPPLIED_CAPACITY                    |
| AVAILABLE (D > 0)     | OFFERED / UNAVAILABLE | Missing               | NO_CAPACITY_DATA                            |
| AVAILABLE (D > 0)     | Any                   | C >= D                | WITHIN_SUPPLIED_CAPACITY                    |
| AVAILABLE (D > 0)     | Any                   | C < D                 | DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY   |
+-----------------------+-----------------------+-----------------------+---------------------------------------------+
```

---

## 9. P7.2 Implementation Contract

In Phase P7.2, Capacity Pressure Analysis will be implemented as a pure domain function:
```python
def evaluate_capacity_pressure(
    demand: DemandMetric,
    capacity: CapacityFact | None,
    privacy_config: PrivacyConfiguration,
) -> CapacityPressureResult:
    ...
```
- Pure, deterministic calculation.
- Guaranteed zero side-effects.
- Complete unit test coverage for zero capacity, missing capacity, suppressed demand, and negative gaps.

