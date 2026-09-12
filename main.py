"""
Fraud Investigation Agent — POC Demo Runner
EU/BaFin Compliant | Criminal Watchlist Screening | Top Management Alerts
"""
import json
import sys
import os
from colorama import Fore, Style, init

init(autoreset=True)


def check_api_key() -> bool:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key or not key.startswith("sk-ant-"):
        print(f"{Fore.YELLOW}⚠  ANTHROPIC_API_KEY not set — running in DEMO mode (rule-based, no LLM).{Style.RESET_ALL}")
        return False
    return True


def print_banner() -> None:
    print(f"""
{Fore.CYAN + Style.BRIGHT}╔══════════════════════════════════════════════════════════════════╗
║   🏦  FRAUD INVESTIGATION AGENT — EU/BaFin POC SANDBOX          ║
║   Criminal Watchlist Screening + Management Alert System         ║
║                ║
╚══════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
""")


def print_transaction_menu(transactions: list) -> None:
    print(f"\n{Fore.WHITE + Style.BRIGHT}Available Transactions:{Style.RESET_ALL}")
    for i, txn in enumerate(transactions):
        sender = txn["sender"]["name"]
        amount = txn["amount"]
        currency = txn["currency"]
        src = txn["sender"]["country"]
        dst = txn["beneficiary"]["country"]
        txn_type = txn.get("type", "WIRE")
        print(f"  [{i+1}] {sender:<40} {amount:>12,.2f} {currency}  {src}→{dst}  [{txn_type}]")
    print(f"  [A] Investigate ALL transactions")
    print(f"  [Q] Quit")


def print_report_summary(report: dict) -> None:
    """Print a clean summary of the investigation report."""
    tool_results = report.get("_tool_results", {})
    risk = tool_results.get("risk_analysis", {})
    watchlist = tool_results.get("watchlist_screening", {})

    score = risk.get("risk_score", report.get("confidence", 0))
    risk_level = risk.get("risk_level", "UNKNOWN")
    pattern = report.get("fraud_pattern", "UNKNOWN")
    alert_rec = report.get("alert_recommendation", "UNKNOWN")
    alert_sent = tool_results.get("alert_dispatched", False)

    color = (
        Fore.RED + Style.BRIGHT if risk_level in ("CRITICAL",) else
        Fore.YELLOW + Style.BRIGHT if risk_level == "HIGH" else
        Fore.YELLOW if risk_level == "MEDIUM" else
        Fore.GREEN
    )

    print(f"\n{Fore.CYAN + Style.BRIGHT}{'─' * 60}")
    print(f"  INVESTIGATION REPORT SUMMARY")
    print(f"{'─' * 60}{Style.RESET_ALL}")
    print(f"  Fraud Pattern    : {color}{pattern}{Style.RESET_ALL}")
    print(f"  Risk Score       : {color}{score}/100 [{risk_level}]{Style.RESET_ALL}")
    print(f"  Alert Rec.       : {color}{alert_rec}{Style.RESET_ALL}")
    print(f"  Management Alert : {'🔴 SENT' if alert_sent else '🟢 NOT REQUIRED'}")

    if watchlist and watchlist.get("total_hits", 0) > 0:
        print(f"\n  {Fore.RED + Style.BRIGHT}WATCHLIST HITS: {watchlist['total_hits']}{Style.RESET_ALL}")
        for hit in watchlist.get("watchlist_hits", []):
            print(f"  ⚠  {hit['matched_name']} [{hit['risk_level']}] — {hit['category']} (score: {hit['match_score']}%)")

    if report.get("investigator_summary"):
        print(f"\n  {Fore.WHITE + Style.BRIGHT}Investigator Summary:{Style.RESET_ALL}")
        summary = report["investigator_summary"]
        # Word-wrap at 60 chars
        words = summary.split()
        line = "  "
        for word in words:
            if len(line) + len(word) + 1 > 62:
                print(line)
                line = "  " + word + " "
            else:
                line += word + " "
        if line.strip():
            print(line)

    sar = report.get("bafin_sar_required", False)
    obligations = report.get("regulatory_obligations", [])
    if sar or obligations:
        print(f"\n  {Fore.YELLOW + Style.BRIGHT}Regulatory Obligations:{Style.RESET_ALL}")
        if sar:
            print(f"  📋 BaFin SAR REQUIRED — file with FIU within 24h")
        for ob in (obligations or [])[:3]:
            print(f"  📋 {ob}")

    print(f"\n  Confidence       : {report.get('confidence', 'N/A')}/100")
    print(f"{Fore.CYAN}{'─' * 60}{Style.RESET_ALL}")


def save_report(report: dict, transaction_id: str) -> str:
    """Save full investigation report to JSON file."""
    filename = f"report_{transaction_id.replace('TXN-', '')}.json"
    filepath = os.path.join(os.path.dirname(__file__), "reports", filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(report, f, indent=2, default=str)
    return filepath


def main() -> None:
    print_banner()

    demo_mode = "--demo" in sys.argv or not check_api_key()

    from transaction_generator import get_demo_transactions
    if demo_mode:
        from fraud_agent import investigate_transaction_demo as investigate_transaction
    else:
        from fraud_agent import investigate_transaction

    transactions = get_demo_transactions()
    print_transaction_menu(transactions)

    while True:
        choice = input(f"\n{Fore.WHITE}Select transaction to investigate (1-{len(transactions)}/A/Q): {Style.RESET_ALL}").strip().upper()

        if choice == "Q":
            print(f"{Fore.GREEN}Exiting Fraud Investigation Agent. Stay vigilant.{Style.RESET_ALL}")
            break

        if choice == "A":
            print(f"\n{Fore.YELLOW + Style.BRIGHT}Running full batch investigation on all {len(transactions)} transactions...{Style.RESET_ALL}")
            all_reports = []
            for txn in transactions:
                try:
                    report = investigate_transaction(txn)
                    print_report_summary(report)
                    filepath = save_report(report, txn["transaction_id"])
                    print(f"  💾 Report saved: {filepath}")
                    all_reports.append(report)
                except Exception as e:
                    print(f"{Fore.RED}  Error investigating {txn['transaction_id']}: {e}{Style.RESET_ALL}")

            print(f"\n{Fore.GREEN + Style.BRIGHT}Batch complete. {len(all_reports)}/{len(transactions)} transactions investigated.{Style.RESET_ALL}")
            print_transaction_menu(transactions)
            continue

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(transactions):
                print(f"{Fore.RED}Invalid selection. Choose 1–{len(transactions)}, A, or Q.{Style.RESET_ALL}")
                continue
        except ValueError:
            print(f"{Fore.RED}Invalid input. Enter a number, A, or Q.{Style.RESET_ALL}")
            continue

        txn = transactions[idx]
        try:
            report = investigate_transaction(txn)
            print_report_summary(report)
            filepath = save_report(report, txn["transaction_id"])
            print(f"\n  💾 Full report saved: {filepath}")
        except Exception as e:
            print(f"{Fore.RED}Investigation error: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()

        print_transaction_menu(transactions)


if __name__ == "__main__":
    main()
