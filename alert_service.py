"""
Alert service — simulates real-time notifications to top management.
In production, integrate with SMTP/SendGrid/SMS/Slack/PagerDuty.
"""
import json
from datetime import datetime, timezone
from colorama import Fore, Style, init

init(autoreset=True)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def send_management_alert(
    priority: str,
    subject: str,
    transaction_id: str,
    customer_name: str,
    amount: float,
    currency: str,
    fraud_pattern: str,
    risk_score: int,
    top_risk_factors: list[str],
    alert_reason: str,
    recipients: list[str],
    watchlist_matches: list[dict] | None = None,
    recommended_action: str = "IMMEDIATE INVESTIGATION REQUIRED",
) -> dict:
    """
    Simulate sending an immediate alert to top management.
    Returns structured alert payload that would be dispatched.
    """
    alert_id = f"ALERT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{transaction_id[:8].upper()}"

    alert_payload = {
        "alert_id": alert_id,
        "timestamp": _timestamp(),
        "priority": priority,
        "subject": subject,
        "transaction_id": transaction_id,
        "customer_name": customer_name,
        "amount": amount,
        "currency": currency,
        "fraud_pattern": fraud_pattern,
        "risk_score": risk_score,
        "top_risk_factors": top_risk_factors,
        "alert_reason": alert_reason,
        "watchlist_matches": watchlist_matches or [],
        "recommended_action": recommended_action,
        "recipients": recipients,
        "regulatory_obligations": _get_regulatory_obligations(
            risk_score, watchlist_matches, amount, currency
        ),
        "dispatch_status": "SENT",
    }

    _print_alert_console(alert_payload)
    return alert_payload


def _get_regulatory_obligations(
    risk_score: int,
    watchlist_matches: list[dict] | None,
    amount: float,
    currency: str,
) -> list[str]:
    obligations = []
    eur_amount = amount if currency == "EUR" else amount * 0.92  # rough FX

    if watchlist_matches:
        obligations.append("BaFin §261 StGB — File Suspicious Activity Report (SAR) within 24h")
        obligations.append("EU 5AMLD Art. 33 — Mandatory STR to Financial Intelligence Unit")
        obligations.append("EU Sanctions Regulation — Freeze assets, report to competent authority")
        obligations.append("GDPR Art. 6(1)(c) — Processing lawful under legal obligation")

    if eur_amount >= 10_000:
        obligations.append("BaFin §11 GwG — Large Cash Transaction Report (≥€10,000)")
        obligations.append("EU Wire Transfer Regulation 2015/847 — Full originator/beneficiary info required")

    if risk_score >= 80:
        obligations.append("BaFin AT 8.2 MaRisk — Escalate to Risk Management Committee")
        obligations.append("EU 6AMLD — Enhanced Due Diligence, document investigation")

    if risk_score >= 90:
        obligations.append("CRITICAL: Consider immediate account freeze pending investigation")
        obligations.append("Notify BaFin Supervisory Officer within 48h (§43 KWG)")

    return obligations if obligations else ["Standard monitoring — no immediate reporting obligation"]


def _print_alert_console(alert: dict) -> None:
    priority_colors = {
        "CRITICAL": Fore.RED + Style.BRIGHT,
        "HIGH": Fore.YELLOW + Style.BRIGHT,
        "MEDIUM": Fore.YELLOW,
        "LOW": Fore.CYAN,
    }
    color = priority_colors.get(alert["priority"], Fore.WHITE)

    border = "=" * 70
    print(f"\n{color}{border}")
    print(f"  🚨  FRAUD ALERT DISPATCHED — {alert['priority']}  🚨")
    print(f"{border}{Style.RESET_ALL}")

    print(f"{Fore.WHITE}{Style.BRIGHT}Alert ID   :{Style.RESET_ALL} {alert['alert_id']}")
    print(f"{Fore.WHITE}{Style.BRIGHT}Timestamp  :{Style.RESET_ALL} {alert['timestamp']}")
    print(f"{Fore.WHITE}{Style.BRIGHT}Subject    :{Style.RESET_ALL} {alert['subject']}")
    print(f"{Fore.WHITE}{Style.BRIGHT}Transaction:{Style.RESET_ALL} {alert['transaction_id']}")
    print(f"{Fore.WHITE}{Style.BRIGHT}Customer   :{Style.RESET_ALL} {color}{alert['customer_name']}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}{Style.BRIGHT}Amount     :{Style.RESET_ALL} {alert['amount']:,.2f} {alert['currency']}")
    print(f"{Fore.WHITE}{Style.BRIGHT}Risk Score :{Style.RESET_ALL} {color}{alert['risk_score']}/100{Style.RESET_ALL}")
    print(f"{Fore.WHITE}{Style.BRIGHT}Pattern    :{Style.RESET_ALL} {alert['fraud_pattern']}")

    if alert["watchlist_matches"]:
        print(f"\n{Fore.RED + Style.BRIGHT}⚠  WATCHLIST MATCHES DETECTED:{Style.RESET_ALL}")
        for match in alert["watchlist_matches"]:
            print(f"   • {match.get('name')} [{match.get('risk_level')}] — {match.get('category')}")
            print(f"     Sanctions: {', '.join(match.get('sanctions', []))}")

    print(f"\n{Fore.WHITE + Style.BRIGHT}Risk Factors:{Style.RESET_ALL}")
    for factor in alert["top_risk_factors"]:
        print(f"   ▶ {factor}")

    print(f"\n{Fore.YELLOW + Style.BRIGHT}Regulatory Obligations:{Style.RESET_ALL}")
    for obligation in alert["regulatory_obligations"]:
        print(f"   📋 {obligation}")

    print(f"\n{Fore.WHITE + Style.BRIGHT}Recommended Action:{Style.RESET_ALL} {color}{alert['recommended_action']}{Style.RESET_ALL}")

    print(f"\n{Fore.GREEN}📧 Alert dispatched to top management:{Style.RESET_ALL}")
    for recipient in alert["recipients"]:
        print(f"   ✓ {recipient}")

    print(f"{color}{border}{Style.RESET_ALL}\n")
