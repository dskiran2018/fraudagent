"""
Fraud Investigation Agent — EU/BaFin Compliant POC
Uses Claude claude-opus-4-7 with adaptive thinking, tool use, and prompt caching.
Screens transactions against a global criminal watchlist and alerts top management.
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone

import anthropic
from rapidfuzz import fuzz, process

from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    HIGH_RISK_COUNTRIES,
    EU_MEMBER_STATES,
    BAFIN_LARGE_TRANSACTION_THRESHOLD,
    BAFIN_SUSPICIOUS_THRESHOLD,
    EU_WIRE_TRANSFER_REGULATION_THRESHOLD,
    NAME_MATCH_THRESHOLD,
    EXACT_MATCH_THRESHOLD,
    TOP_MANAGEMENT_EMAILS,
)
from alert_service import send_management_alert

# ── Client ─────────────────────────────────────────────────────────────────
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Load watchlist once at startup ─────────────────────────────────────────
_WATCHLIST_PATH = Path(__file__).parent / "criminal_watchlist.json"
with open(_WATCHLIST_PATH) as f:
    _WATCHLIST_DATA = json.load(f)

_WATCHLIST_INDIVIDUALS: list[dict] = _WATCHLIST_DATA["watchlist"]
_WATCHLIST_ENTITIES: list[dict] = _WATCHLIST_DATA["high_risk_entities"]

# Build flat name index: {canonical_name: entry}
_NAME_INDEX: dict[str, dict] = {}
for entry in _WATCHLIST_INDIVIDUALS:
    _NAME_INDEX[entry["name"].lower()] = entry
    for alias in entry.get("aliases", []):
        if alias:
            _NAME_INDEX[alias.lower()] = entry

for entity in _WATCHLIST_ENTITIES:
    _NAME_INDEX[entity["name"].lower()] = entity


# ── Tool implementations ────────────────────────────────────────────────────

def _screen_criminal_watchlist(customer_name: str, beneficiary_name: str) -> dict:
    """Fuzzy name screening against global criminal watchlist."""
    matches = []
    all_names = list(_NAME_INDEX.keys())

    for query_name in [customer_name, beneficiary_name]:
        if not query_name or query_name.strip() == "":
            continue

        # rapidfuzz top matches
        results = process.extract(
            query_name.lower(),
            all_names,
            scorer=fuzz.token_sort_ratio,
            limit=5,
        )

        for matched_name, score, _ in results:
            if score >= NAME_MATCH_THRESHOLD:
                entry = _NAME_INDEX[matched_name]
                matches.append({
                    "query_name": query_name,
                    "matched_name": entry.get("name", matched_name),
                    "match_score": score,
                    "match_type": "EXACT" if score >= EXACT_MATCH_THRESHOLD else "FUZZY",
                    "risk_level": entry.get("risk_level", "UNKNOWN"),
                    "category": entry.get("category", "UNKNOWN"),
                    "sanctions": entry.get("sanctions", []),
                    "known_for": entry.get("known_for", ""),
                    "associated_entities": entry.get("associated_entities", []),
                    "nationality": entry.get("nationality", "Unknown"),
                    "watchlist_id": entry.get("id", "UNKNOWN"),
                })

    # deduplicate by watchlist_id
    seen_ids = set()
    unique_matches = []
    for m in matches:
        if m["watchlist_id"] not in seen_ids:
            seen_ids.add(m["watchlist_id"])
            unique_matches.append(m)

    return {
        "screening_timestamp": datetime.now(timezone.utc).isoformat(),
        "customer_name_screened": customer_name,
        "beneficiary_name_screened": beneficiary_name,
        "watchlist_hits": unique_matches,
        "total_hits": len(unique_matches),
        "highest_risk": max((m["risk_level"] for m in unique_matches), default="NONE"),
        "screening_status": "HIT" if unique_matches else "CLEAR",
    }


def _check_regulatory_compliance(transaction: dict) -> dict:
    """BaFin / EU AML regulatory compliance check."""
    issues = []
    amount = transaction.get("amount", 0)
    currency = transaction.get("currency", "EUR")
    sender_country = transaction.get("sender", {}).get("country", "")
    beneficiary_country = transaction.get("beneficiary", {}).get("country", "")

    # Convert to EUR roughly
    eur_amount = amount if currency == "EUR" else (
        amount * 0.92 if currency == "USD" else
        amount * 1.17 if currency == "GBP" else amount
    )

    # BaFin §11 GwG — Large transaction
    if eur_amount >= BAFIN_LARGE_TRANSACTION_THRESHOLD:
        issues.append({
            "rule": "BaFin §11 GwG",
            "description": f"Transaction ≥€{BAFIN_LARGE_TRANSACTION_THRESHOLD:,} — mandatory CTR filing required",
            "severity": "HIGH",
        })

    # EU Wire Transfer Regulation 2015/847
    if eur_amount >= EU_WIRE_TRANSFER_REGULATION_THRESHOLD:
        issues.append({
            "rule": "EU Regulation 2015/847",
            "description": "Complete originator/beneficiary information required for wire transfers ≥€1,000",
            "severity": "MEDIUM",
        })

    # High-risk country involvement
    for country_code, direction in [(sender_country, "sender"), (beneficiary_country, "beneficiary")]:
        if country_code in HIGH_RISK_COUNTRIES:
            issues.append({
                "rule": "EU 5AMLD Art. 18 / BaFin AML",
                "description": f"High-risk third country involved ({direction}: {country_code}) — Enhanced Due Diligence required",
                "severity": "HIGH",
            })

    # Structuring indicator (just below reporting threshold)
    structuring_window = BAFIN_LARGE_TRANSACTION_THRESHOLD * 0.98
    if structuring_window <= eur_amount < BAFIN_LARGE_TRANSACTION_THRESHOLD:
        issues.append({
            "rule": "BaFin §261 StGB / FinCEN Structuring",
            "description": f"Amount (€{eur_amount:,.0f}) suspiciously close to €{BAFIN_LARGE_TRANSACTION_THRESHOLD:,} reporting threshold — possible structuring",
            "severity": "CRITICAL",
        })

    # Velocity check
    velocity_flag = transaction.get("velocity_flag", False)
    prior_amount = transaction.get("prior_amount_24h", 0)
    prior_count = transaction.get("prior_transactions_24h", 0)
    if velocity_flag or (prior_count >= 3 and prior_amount >= 50_000):
        issues.append({
            "rule": "BaFin AT 6.3 MaRisk / EU 4AMLD Art. 8",
            "description": f"Velocity anomaly: {prior_count} transactions, €{prior_amount:,.0f} in past 24h",
            "severity": "HIGH",
        })

    return {
        "compliance_timestamp": datetime.now(timezone.utc).isoformat(),
        "eur_equivalent": round(eur_amount, 2),
        "sender_country": sender_country,
        "beneficiary_country": beneficiary_country,
        "sender_in_eu": sender_country in EU_MEMBER_STATES,
        "beneficiary_in_eu": beneficiary_country in EU_MEMBER_STATES,
        "sender_high_risk": sender_country in HIGH_RISK_COUNTRIES,
        "beneficiary_high_risk": beneficiary_country in HIGH_RISK_COUNTRIES,
        "compliance_issues": issues,
        "total_issues": len(issues),
        "highest_severity": (
            "CRITICAL" if any(i["severity"] == "CRITICAL" for i in issues) else
            "HIGH" if any(i["severity"] == "HIGH" for i in issues) else
            "MEDIUM" if any(i["severity"] == "MEDIUM" for i in issues) else
            "NONE"
        ),
        "mandatory_sar_required": any(
            i["severity"] in ("CRITICAL", "HIGH") for i in issues
        ) or len(issues) >= 2,
    }


def _analyze_transaction_risk(transaction: dict, watchlist_result: dict, compliance_result: dict) -> dict:
    """Compute composite risk score (0–100)."""
    score = 0
    factors = []

    amount = transaction.get("amount", 0)
    currency = transaction.get("currency", "EUR")
    eur_amount = compliance_result.get("eur_equivalent", amount)

    # Watchlist hits (up to 60 points)
    if watchlist_result["total_hits"] > 0:
        highest_risk = watchlist_result["highest_risk"]
        if highest_risk == "CRITICAL":
            score += 60
            factors.append(f"CRITICAL watchlist match — {watchlist_result['watchlist_hits'][0]['matched_name']}")
        elif highest_risk == "HIGH":
            score += 45
            factors.append(f"HIGH watchlist match — {watchlist_result['watchlist_hits'][0]['matched_name']}")
        elif highest_risk == "MEDIUM":
            score += 25
            factors.append(f"MEDIUM watchlist match — {watchlist_result['watchlist_hits'][0]['matched_name']}")

    # Amount risk (up to 20 points)
    if eur_amount >= 1_000_000:
        score += 20
        factors.append(f"Very large transaction: €{eur_amount:,.0f}")
    elif eur_amount >= 100_000:
        score += 15
        factors.append(f"Large transaction: €{eur_amount:,.0f}")
    elif eur_amount >= BAFIN_LARGE_TRANSACTION_THRESHOLD:
        score += 8
        factors.append(f"Reportable transaction: €{eur_amount:,.0f}")

    # High-risk country (up to 15 points)
    if compliance_result["sender_high_risk"] and compliance_result["beneficiary_high_risk"]:
        score += 15
        factors.append(f"Both sender and beneficiary in high-risk countries")
    elif compliance_result["sender_high_risk"] or compliance_result["beneficiary_high_risk"]:
        score += 10
        factors.append(f"High-risk country involved: {compliance_result['sender_country']} → {compliance_result['beneficiary_country']}")

    # Structuring / velocity (up to 15 points)
    severity = compliance_result.get("highest_severity", "NONE")
    if severity == "CRITICAL":
        score += 15
        factors.append("Possible structuring — amount just below reporting threshold")
    elif compliance_result.get("mandatory_sar_required"):
        score += 10
        factors.append("Multiple compliance violations detected")

    # Velocity flag
    if transaction.get("velocity_flag"):
        score += 8
        factors.append(f"Transaction velocity: {transaction.get('prior_transactions_24h', 0)} txns / €{transaction.get('prior_amount_24h', 0):,.0f} in 24h")

    score = min(score, 100)

    # Determine risk level
    if score >= 85:
        risk_level = "CRITICAL"
    elif score >= 70:
        risk_level = "HIGH"
    elif score >= 50:
        risk_level = "MEDIUM"
    elif score >= 30:
        risk_level = "LOW"
    else:
        risk_level = "MINIMAL"

    return {
        "risk_score": score,
        "risk_level": risk_level,
        "risk_factors": factors,
        "alert_recommended": score >= 70 or watchlist_result["total_hits"] > 0,
        "sar_required": compliance_result.get("mandatory_sar_required", False) or score >= 80,
    }


def _dispatch_management_alert(
    transaction: dict,
    risk_result: dict,
    watchlist_result: dict,
    investigation_summary: str,
    fraud_pattern: str,
) -> dict:
    """Dispatch immediate alert to top management."""
    score = risk_result["risk_score"]

    if score >= 90 or (watchlist_result["total_hits"] > 0 and watchlist_result["highest_risk"] == "CRITICAL"):
        priority = "CRITICAL"
    elif score >= 80 or watchlist_result["total_hits"] > 0:
        priority = "HIGH"
    elif score >= 60:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    sender_name = transaction.get("sender", {}).get("name", "UNKNOWN")
    amount = transaction.get("amount", 0)
    currency = transaction.get("currency", "EUR")

    subject_emoji = "🚨" if priority in ("CRITICAL", "HIGH") else "⚠️"
    subject = f"{subject_emoji} [{priority}] Fraud Alert — {fraud_pattern} | {sender_name} | {amount:,.0f} {currency}"

    watchlist_matches = watchlist_result.get("watchlist_hits", [])

    recommended_action = (
        "IMMEDIATE: Freeze transaction, file SAR with BaFin FIU, notify compliance team"
        if priority == "CRITICAL" else
        "URGENT: Hold transaction, initiate enhanced due diligence, prepare SAR"
        if priority == "HIGH" else
        "Review transaction, enhanced monitoring, document findings"
    )

    return send_management_alert(
        priority=priority,
        subject=subject,
        transaction_id=transaction.get("transaction_id", "UNKNOWN"),
        customer_name=sender_name,
        amount=amount,
        currency=currency,
        fraud_pattern=fraud_pattern,
        risk_score=score,
        top_risk_factors=risk_result.get("risk_factors", [])[:3],
        alert_reason=investigation_summary[:500],
        recipients=TOP_MANAGEMENT_EMAILS,
        watchlist_matches=watchlist_matches,
        recommended_action=recommended_action,
    )


# ── Tool definitions for Claude ─────────────────────────────────────────────

TOOLS = [
    {
        "name": "screen_criminal_watchlist",
        "description": (
            "Screen customer and beneficiary names against the global criminal watchlist "
            "using fuzzy matching. Returns watchlist hits with risk levels and sanction details. "
            "ALWAYS call this first for any transaction."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_name": {
                    "type": "string",
                    "description": "Full name of the transaction sender / customer",
                },
                "beneficiary_name": {
                    "type": "string",
                    "description": "Full name of the transaction beneficiary",
                },
            },
            "required": ["customer_name", "beneficiary_name"],
        },
    },
    {
        "name": "check_regulatory_compliance",
        "description": (
            "Check transaction against BaFin and EU AML regulatory requirements "
            "(GwG, 5AMLD, 6AMLD, MaRisk, Wire Transfer Regulation 2015/847). "
            "Identifies reporting obligations, high-risk country exposure, and structuring patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "transaction": {
                    "type": "object",
                    "description": "Full transaction object as received",
                },
            },
            "required": ["transaction"],
        },
    },
    {
        "name": "analyze_transaction_risk",
        "description": (
            "Compute a composite risk score (0–100) and risk level based on watchlist results, "
            "compliance findings, amount, country risk, and velocity signals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "transaction": {
                    "type": "object",
                    "description": "Full transaction object",
                },
                "watchlist_result": {
                    "type": "object",
                    "description": "Output from screen_criminal_watchlist tool",
                },
                "compliance_result": {
                    "type": "object",
                    "description": "Output from check_regulatory_compliance tool",
                },
            },
            "required": ["transaction", "watchlist_result", "compliance_result"],
        },
    },
    {
        "name": "dispatch_management_alert",
        "description": (
            "Dispatch an IMMEDIATE alert to top management when a high-risk or criminal-linked "
            "transaction is detected. Use this when risk_score >= 70 or when watchlist hits are found. "
            "This triggers email/SMS/Slack notifications to CEO, CFO, CCO, CRO, and the SOC team."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "transaction": {
                    "type": "object",
                    "description": "Full transaction object",
                },
                "risk_result": {
                    "type": "object",
                    "description": "Output from analyze_transaction_risk tool",
                },
                "watchlist_result": {
                    "type": "object",
                    "description": "Output from screen_criminal_watchlist tool",
                },
                "investigation_summary": {
                    "type": "string",
                    "description": "Brief investigator summary for the alert email body",
                },
                "fraud_pattern": {
                    "type": "string",
                    "description": "Detected fraud pattern (e.g. MULE_AGGREGATION, LAUNDERING_CHAIN, SANCTIONED_ENTITY_TRANSFER, STRUCTURING)",
                },
            },
            "required": ["transaction", "risk_result", "watchlist_result", "investigation_summary", "fraud_pattern"],
        },
    },
]

# ── System prompt (cached) ──────────────────────────────────────────────────

def _build_system_prompt() -> str:
    watchlist_summary = json.dumps(
        {
            "total_individuals": len(_WATCHLIST_INDIVIDUALS),
            "total_entities": len(_WATCHLIST_ENTITIES),
            "categories": list({e["category"] for e in _WATCHLIST_INDIVIDUALS}),
            "sanctions_sources": list(_WATCHLIST_DATA["metadata"]["sources"]),
        },
        indent=2,
    )

    return f"""You are a Senior Fraud Investigator AI operating within a real-time EU/BaFin-regulated banking fraud detection system.

## YOUR MANDATE
You investigate international transactions for financial crime indicators, applying EU and German BaFin regulatory standards. When you detect a criminal name match or high-risk transaction, you IMMEDIATELY alert top management — this is non-negotiable.

## REGULATORY FRAMEWORK
- **BaFin (Bundesanstalt für Finanzdienstleistungsaufsicht)**: Germany's primary financial regulator
  - GwG (Geldwäschegesetz) — German AML Act, mandatory SAR filing
  - KWG (Kreditwesengesetz) — Banking supervision law
  - MaRisk — Minimum requirements for risk management
  - §261 StGB — Money laundering criminal statute

- **EU Directives**:
  - 4AMLD/5AMLD/6AMLD — Anti-Money Laundering Directives
  - EU Regulation 2015/847 — Wire Transfer Regulation (full originator/beneficiary info)
  - EU Sanctions Regulation — Asset freeze obligations
  - GDPR Art. 6(1)(c) — Legal basis for processing (legal obligation)

- **International Standards**:
  - FATF 40 Recommendations
  - Wolfsberg Anti-Money Laundering Principles
  - Egmont Group FIU standards

## CRIMINAL WATCHLIST DATABASE
{watchlist_summary}

The watchlist contains OFAC SDN, EU Sanctions, FBI Most Wanted, Interpol Red Notice, BaFin Watch, and UN Security Council designations. You have access to screen any name using the `screen_criminal_watchlist` tool.

## YOUR INVESTIGATION PROCESS
For EVERY transaction:
1. **ALWAYS start** by calling `screen_criminal_watchlist` — criminal name screening is mandatory
2. Call `check_regulatory_compliance` — regulatory obligation assessment
3. Call `analyze_transaction_risk` — composite risk scoring
4. If risk_score ≥ 70 OR watchlist hit found → **IMMEDIATELY** call `dispatch_management_alert`
5. Produce a structured JSON investigation report

## FRAUD PATTERNS TO DETECT
- `SANCTIONED_ENTITY_TRANSFER` — transaction involving a sanctioned person/entity
- `MULE_AGGREGATION` — multiple incoming transfers consolidated before forwarding
- `FRAUD_DISTRIBUTION` — funds dispersed to multiple accounts after aggregation
- `LAUNDERING_CHAIN` — multi-hop transfers obscuring origin
- `STRUCTURING` — amounts deliberately kept below reporting thresholds
- `HIGH_RISK_JURISDICTION` — transfers involving FATF-listed high-risk countries
- `CRYPTO_FRAUD_PROCEEDS` — funds linked to crypto fraud/scams
- `TERRORISM_FINANCING` — transactions linked to terrorist organizations
- `NORMAL_BEHAVIOR` — no significant red flags detected

## IMPORTANT CONSTRAINTS
- You are an INVESTIGATION and EXPLANATION system — NOT a final decision authority
- Always provide evidence-backed reasoning
- Never hallucinate watchlist entries — use the tools
- Always output a final structured JSON report
- EU/BaFin compliance obligations must be stated explicitly
"""


# ── Demo mode (no API key required) ────────────────────────────────────────

def _infer_fraud_pattern(watchlist_result: dict, compliance_result: dict, transaction: dict) -> str:
    if watchlist_result["total_hits"] > 0:
        return "SANCTIONED_ENTITY_TRANSFER"
    issues = compliance_result.get("compliance_issues", [])
    rules = {i["rule"] for i in issues}
    if any("Structuring" in r or "§261" in r for r in rules):
        return "STRUCTURING"
    if compliance_result.get("sender_high_risk") or compliance_result.get("beneficiary_high_risk"):
        return "HIGH_RISK_JURISDICTION"
    if transaction.get("velocity_flag") and transaction.get("prior_transactions_24h", 0) >= 3:
        return "MULE_AGGREGATION"
    return "NORMAL_BEHAVIOR"


def _build_investigator_summary(
    transaction: dict,
    watchlist_result: dict,
    compliance_result: dict,
    risk_result: dict,
    fraud_pattern: str,
) -> str:
    sender = transaction["sender"]["name"]
    amount = transaction["amount"]
    currency = transaction["currency"]
    src = transaction["sender"]["country"]
    dst = transaction["beneficiary"]["country"]
    score = risk_result["risk_score"]
    level = risk_result["risk_level"]

    parts = [
        f"Transaction of {amount:,.2f} {currency} from {sender} ({src} → {dst}) "
        f"assessed as {level} risk (score {score}/100). Pattern: {fraud_pattern}."
    ]

    if watchlist_result["total_hits"] > 0:
        hit = watchlist_result["watchlist_hits"][0]
        parts.append(
            f"WATCHLIST HIT: {hit['matched_name']} matched as {hit['category']} "
            f"({hit['match_score']}% confidence). Sanctions: {', '.join(hit.get('sanctions', ['N/A']))}."
        )

    if compliance_result["total_issues"] > 0:
        parts.append(
            f"{compliance_result['total_issues']} compliance issue(s) detected "
            f"(highest: {compliance_result['highest_severity']}): "
            + "; ".join(i["description"] for i in compliance_result["compliance_issues"][:2]) + "."
        )

    if risk_result.get("sar_required"):
        parts.append("BaFin SAR filing mandatory within 24h.")

    return " ".join(parts)


def investigate_transaction_demo_stream(transaction: dict):
    """
    Generator form of the rule-based investigation pipeline.
    Yields one event per pipeline stage: {"step", "status", "data"}.
    Used by both the CLI (investigate_transaction_demo) and the web demo frontend.
    """
    yield {
        "step": "intake",
        "status": "done",
        "data": {
            "transaction_id": transaction["transaction_id"],
            "sender": transaction["sender"]["name"],
            "sender_country": transaction["sender"]["country"],
            "beneficiary": transaction["beneficiary"]["name"],
            "beneficiary_country": transaction["beneficiary"]["country"],
            "amount": transaction["amount"],
            "currency": transaction["currency"],
            "type": transaction.get("type", "WIRE"),
        },
    }

    watchlist = _screen_criminal_watchlist(
        customer_name=transaction["sender"]["name"],
        beneficiary_name=transaction["beneficiary"]["name"],
    )
    yield {"step": "watchlist", "status": "done", "data": watchlist}

    compliance = _check_regulatory_compliance(transaction)
    yield {"step": "compliance", "status": "done", "data": compliance}

    risk = _analyze_transaction_risk(transaction, watchlist, compliance)
    yield {"step": "risk", "status": "done", "data": risk}

    fraud_pattern = _infer_fraud_pattern(watchlist, compliance, transaction)
    summary = _build_investigator_summary(transaction, watchlist, compliance, risk, fraud_pattern)

    alert_result = None
    alert_recommendation = "NO_ALERT"
    if risk["alert_recommended"]:
        alert_recommendation = "TRIGGER_ALERT"
        alert_result = _dispatch_management_alert(
            transaction=transaction,
            risk_result=risk,
            watchlist_result=watchlist,
            investigation_summary=summary,
            fraud_pattern=fraud_pattern,
        )
        yield {"step": "alert", "status": "done", "data": alert_result}
    else:
        yield {"step": "alert", "status": "skipped", "data": None}

    obligations = []
    if watchlist["total_hits"] > 0:
        obligations.append("BaFin §261 StGB — File SAR with FIU within 24h")
        obligations.append("EU 5AMLD Art. 33 — Mandatory STR to Financial Intelligence Unit")
    if compliance.get("mandatory_sar_required"):
        obligations.append("BaFin §11 GwG — Large Transaction Report required")

    report = {
        "transaction_id": transaction["transaction_id"],
        "investigation_timestamp": datetime.now(timezone.utc).isoformat(),
        "fraud_pattern": fraud_pattern,
        "fraud_narrative": summary,
        "graph_analysis": f"Single-hop transfer {transaction['sender']['country']} → {transaction['beneficiary']['country']}",
        "behavior_analysis": (
            f"Velocity flag: {transaction.get('velocity_flag', False)}, "
            f"prior 24h txns: {transaction.get('prior_transactions_24h', 0)}, "
            f"prior 24h amount: {transaction.get('prior_amount_24h', 0):,.0f} {transaction['currency']}"
        ),
        "compliance_analysis": "; ".join(
            i["description"] for i in compliance["compliance_issues"]
        ) or "No compliance issues detected.",
        "observability_insight": f"IP: {transaction.get('ip_address', 'N/A')}, device: {transaction.get('device_fingerprint', 'N/A')}",
        "top_risk_factors": risk["risk_factors"][:3],
        "investigator_summary": summary,
        "alert_recommendation": alert_recommendation,
        "email_notification": alert_result,
        "evidence_mapping": [
            {"type": "watchlist", "hits": watchlist["total_hits"]},
            {"type": "compliance", "issues": compliance["total_issues"]},
        ],
        "confidence": min(risk["risk_score"] + 10, 100),
        "regulatory_obligations": obligations,
        "bafin_sar_required": risk.get("sar_required", False),
        "_tool_results": {
            "watchlist_screening": watchlist,
            "compliance_check": compliance,
            "risk_analysis": risk,
            "alert_dispatched": alert_result is not None,
            "alert_details": alert_result,
        },
    }
    yield {"step": "report", "status": "done", "data": report}


def investigate_transaction_demo(transaction: dict) -> dict:
    """Run full investigation pipeline without Claude API — rule-based demo mode."""
    print(f"\n{'─' * 60}")
    print(f"🔍 [DEMO] INVESTIGATING: {transaction['transaction_id']}")
    print(f"   {transaction['sender']['name']} → {transaction['beneficiary']['name']}")
    print(f"   {transaction['amount']:,.2f} {transaction['currency']} | "
          f"{transaction['sender']['country']} → {transaction['beneficiary']['country']}")
    print(f"{'─' * 60}\n")

    report = {}
    for event in investigate_transaction_demo_stream(transaction):
        step, data = event["step"], event["data"]
        if step == "watchlist":
            print("  🔧 Tool call: screen_criminal_watchlist")
            status = "🔴 HIT" if data["screening_status"] == "HIT" else "🟢 CLEAR"
            print(f"     Watchlist screening: {status} ({data['total_hits']} matches)")
        elif step == "compliance":
            print("  🔧 Tool call: check_regulatory_compliance")
            print(f"     Compliance: {data['total_issues']} issues, severity={data['highest_severity']}")
        elif step == "risk":
            print("  🔧 Tool call: analyze_transaction_risk")
            print(f"     Risk score: {data['risk_score']}/100 [{data['risk_level']}]")
        elif step == "alert" and event["status"] == "done":
            print("  🔧 Tool call: dispatch_management_alert")
        elif step == "report":
            report = data

    return report


# ── Main investigation function ─────────────────────────────────────────────

def investigate_transaction(transaction: dict) -> dict:
    """
    Run the full fraud investigation pipeline for a single transaction.
    Returns the complete investigation report.
    """
    print(f"\n{'─' * 60}")
    print(f"🔍 INVESTIGATING: {transaction['transaction_id']}")
    print(f"   {transaction['sender']['name']} → {transaction['beneficiary']['name']}")
    print(f"   {transaction['amount']:,.2f} {transaction['currency']} | {transaction['sender']['country']} → {transaction['beneficiary']['country']}")
    print(f"{'─' * 60}\n")

    system_prompt = _build_system_prompt()
    transaction_prompt = f"""Investigate this international transaction for financial crime indicators.
Apply EU/BaFin regulatory standards. If criminal names are detected or risk is high, alert top management immediately.

## TRANSACTION DATA
```json
{json.dumps(transaction, indent=2)}
```

Execute the full investigation workflow:
1. Screen criminal watchlist (MANDATORY first step)
2. Check regulatory compliance
3. Analyze composite risk score
4. Alert management if warranted (risk ≥ 70 or watchlist hit)
5. Produce the final structured JSON investigation report

The final output MUST be valid JSON with these fields:
{{
  "transaction_id": "...",
  "investigation_timestamp": "...",
  "fraud_pattern": "...",
  "fraud_narrative": "...",
  "graph_analysis": "...",
  "behavior_analysis": "...",
  "compliance_analysis": "...",
  "observability_insight": "...",
  "top_risk_factors": ["...", "...", "..."],
  "investigator_summary": "...",
  "alert_recommendation": "NO_ALERT | MONITOR | TRIGGER_ALERT",
  "email_notification": null | {{...}},
  "evidence_mapping": [{{...}}],
  "confidence": 0-100,
  "regulatory_obligations": ["..."],
  "bafin_sar_required": true/false
}}"""

    messages = [{"role": "user", "content": transaction_prompt}]

    # Agentic tool-use loop
    tool_results_store = {}

    while True:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},  # cache stable system prompt
                }
            ],
            tools=TOOLS,
            messages=messages,
        )

        # Append assistant response
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason != "tool_use":
            break

        # Process all tool calls in this response
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input
            print(f"  🔧 Tool call: {tool_name}")

            # Dispatch tool
            if tool_name == "screen_criminal_watchlist":
                result = _screen_criminal_watchlist(
                    customer_name=tool_input.get("customer_name", ""),
                    beneficiary_name=tool_input.get("beneficiary_name", ""),
                )
                tool_results_store["watchlist"] = result
                status = "🔴 HIT" if result["screening_status"] == "HIT" else "🟢 CLEAR"
                print(f"     Watchlist screening: {status} ({result['total_hits']} matches)")

            elif tool_name == "check_regulatory_compliance":
                result = _check_regulatory_compliance(tool_input.get("transaction", transaction))
                tool_results_store["compliance"] = result
                print(f"     Compliance: {result['total_issues']} issues, severity={result['highest_severity']}")

            elif tool_name == "analyze_transaction_risk":
                result = _analyze_transaction_risk(
                    transaction=tool_input.get("transaction", transaction),
                    watchlist_result=tool_input.get("watchlist_result", tool_results_store.get("watchlist", {})),
                    compliance_result=tool_input.get("compliance_result", tool_results_store.get("compliance", {})),
                )
                tool_results_store["risk"] = result
                print(f"     Risk score: {result['risk_score']}/100 [{result['risk_level']}]")

            elif tool_name == "dispatch_management_alert":
                result = _dispatch_management_alert(
                    transaction=tool_input.get("transaction", transaction),
                    risk_result=tool_input.get("risk_result", tool_results_store.get("risk", {})),
                    watchlist_result=tool_input.get("watchlist_result", tool_results_store.get("watchlist", {})),
                    investigation_summary=tool_input.get("investigation_summary", ""),
                    fraud_pattern=tool_input.get("fraud_pattern", "UNKNOWN"),
                )
                tool_results_store["alert"] = result
                print(f"     Alert dispatched: {result.get('alert_id', 'N/A')} [{result.get('dispatch_status')}]")

            else:
                result = {"error": f"Unknown tool: {tool_name}"}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })

        messages.append({"role": "user", "content": tool_results})

    # Extract final JSON report from the last text block
    final_report = {}
    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            # Try to parse JSON from the response
            if "{" in text:
                # Extract JSON block
                start = text.find("{")
                # Find the matching closing brace
                depth = 0
                end = start
                for i, ch in enumerate(text[start:], start):
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                try:
                    final_report = json.loads(text[start:end])
                except json.JSONDecodeError:
                    final_report = {"raw_output": text, "parse_error": True}
            break

    # Merge tool results into report
    final_report["_tool_results"] = {
        "watchlist_screening": tool_results_store.get("watchlist"),
        "compliance_check": tool_results_store.get("compliance"),
        "risk_analysis": tool_results_store.get("risk"),
        "alert_dispatched": tool_results_store.get("alert") is not None,
        "alert_details": tool_results_store.get("alert"),
    }

    return final_report
