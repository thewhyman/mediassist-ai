"""Deterministic Medicaid eligibility engine.

Pure Python — no LLM calls. This module is the single source of truth for
eligibility math. It is used by:
  - The agent (as an internal tool to verify its own reasoning)
  - The Layer 4 guardrail (to catch LLM hallucinated determinations)
  - The eval suite (to compute expected results)

Keeping eligibility logic in code (not in a prompt) eliminates model drift
for the most critical part of the application.
"""

from prompts import FPL, FPL_ALASKA, FPL_HAWAII, STATE_THRESHOLDS


def get_fpl(state: str, household_size: int) -> int:
    """Get the Federal Poverty Level for a state and household size."""
    size = min(household_size, 8)
    if state == "AK":
        return FPL_ALASKA.get(size, FPL_ALASKA[8])
    elif state == "HI":
        return FPL_HAWAII.get(size, FPL_HAWAII[8])
    return FPL.get(size, FPL[8])


def determine_category(patient: dict) -> str:
    """Determine which Medicaid eligibility category applies.

    Categories (in priority order):
      - child: age < 19 (higher income thresholds)
      - pregnant: regardless of age (enhanced thresholds)
      - disabled: SSI-related pathway
      - elderly: age >= 65 (aged/blind/disabled category)
      - adult: default
    """
    if patient.get("age", 0) < 19:
        return "child"
    if patient.get("is_pregnant", False):
        return "pregnant"
    if patient.get("has_disability", False):
        return "disabled"
    if patient.get("age", 0) >= 65:
        return "elderly"
    return "adult"


def compute_eligibility(patient: dict) -> dict:
    """Compute Medicaid eligibility deterministically.

    Args:
        patient: dict with keys: state, household_size, annual_income,
                 age, is_pregnant, has_disability, is_us_citizen

    Returns:
        dict with: eligible (bool), category, fpl, income_pct,
                   threshold_pct, threshold_amount, expansion, ambiguous, reason
    """
    state = patient.get("state", "")
    hh_size = patient.get("household_size", 1)
    income = patient.get("annual_income", 0)
    category = determine_category(patient)

    # Citizenship check — non-citizens are ineligible
    # (simplified; real rules have qualified immigrant exceptions)
    if not patient.get("is_us_citizen", True):
        fpl = get_fpl(state, hh_size)
        return {
            "eligible": False,
            "ambiguous": False,
            "category": category,
            "fpl": fpl,
            "income_pct": round((income / fpl) * 100, 1) if fpl else 0,
            "threshold_pct": 0,
            "threshold_amount": 0,
            "expansion": STATE_THRESHOLDS.get(state, {}).get("expansion", False),
            "reason": "Not a US citizen",
        }

    fpl = get_fpl(state, hh_size)
    thresholds = STATE_THRESHOLDS.get(state)
    if not thresholds:
        return {
            "eligible": None,
            "ambiguous": True,
            "category": category,
            "fpl": fpl,
            "income_pct": round((income / fpl) * 100, 1) if fpl else 0,
            "threshold_pct": 0,
            "threshold_amount": 0,
            "expansion": None,
            "reason": f"State '{state}' not found in threshold data",
        }

    income_pct = (income / fpl) * 100

    # Select the applicable threshold percentage
    if category == "child":
        threshold_pct = thresholds["child_pct"]
    elif category == "pregnant":
        threshold_pct = thresholds["pregnant_pct"]
    elif category in ("disabled", "elderly"):
        # Use adult threshold as baseline; these categories may qualify
        # through SSI or aged/blind/disabled pathways beyond income
        threshold_pct = thresholds["adult_pct"]
    else:
        threshold_pct = thresholds["adult_pct"]

    threshold_amount = fpl * threshold_pct / 100
    eligible = income <= threshold_amount

    # Disabled/elderly in non-expansion states have SSI pathways we can't
    # fully model — flag as ambiguous
    ambiguous = category in ("disabled", "elderly") and not thresholds["expansion"]

    reason_parts = []
    if eligible:
        reason_parts.append(
            f"Income ${income:,.0f} ({income_pct:.1f}% FPL) is at or below "
            f"{threshold_pct}% FPL threshold (${threshold_amount:,.0f}) for "
            f"{category} category in {state}"
        )
    else:
        reason_parts.append(
            f"Income ${income:,.0f} ({income_pct:.1f}% FPL) exceeds "
            f"{threshold_pct}% FPL threshold (${threshold_amount:,.0f}) for "
            f"{category} category in {state}"
        )
    if ambiguous:
        reason_parts.append(
            f"Note: {category} individuals may qualify through SSI/aged-blind-disabled "
            f"pathways not fully modeled here"
        )

    return {
        "eligible": eligible,
        "ambiguous": ambiguous,
        "category": category,
        "fpl": fpl,
        "income_pct": round(income_pct, 1),
        "threshold_pct": threshold_pct,
        "threshold_amount": round(threshold_amount, 2),
        "expansion": thresholds["expansion"],
        "reason": ". ".join(reason_parts),
    }


def parse_determination(response: str) -> bool | None:
    """Extract ELIGIBLE or NOT ELIGIBLE from agent response text."""
    import re
    text = response.upper()
    if re.search(r'\bNOT\s+ELIGIBLE\b', text):
        return False
    if re.search(r'\bINELIGIBLE\b', text):
        return False
    if re.search(r'\bELIGIBLE\b', text):
        return True
    return None


def format_determination_summary(patient: dict, result: dict) -> str:
    """Format a human-readable summary of the eligibility determination.

    Used by the guardrail to inject into the agent's context when the LLM
    disagrees with the deterministic result.
    """
    name = f"{patient.get('first_name', '?')} {patient.get('last_name', '?')}"
    status = "ELIGIBLE" if result["eligible"] else "NOT ELIGIBLE"
    lines = [
        f"Deterministic Eligibility Result for {name}:",
        f"  Status: {status}",
        f"  Category: {result['category']}",
        f"  State: {patient.get('state', '?')} ({'expansion' if result['expansion'] else 'non-expansion'})",
        f"  FPL (household size {patient.get('household_size', '?')}): ${result['fpl']:,}",
        f"  Income: ${patient.get('annual_income', 0):,.0f} ({result['income_pct']}% of FPL)",
        f"  Threshold: {result['threshold_pct']}% FPL = ${result['threshold_amount']:,.0f}",
        f"  Reason: {result['reason']}",
    ]
    if result["ambiguous"]:
        lines.append("  Note: This case is ambiguous — SSI/ABD pathways may apply")
    return "\n".join(lines)
