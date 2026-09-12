import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-opus-4-7"

# BaFin / EU Regulatory Thresholds
BAFIN_LARGE_TRANSACTION_THRESHOLD = 10_000      # EUR — mandatory reporting
BAFIN_SUSPICIOUS_THRESHOLD = 1_000              # EUR — enhanced scrutiny
EU_WIRE_TRANSFER_REGULATION_THRESHOLD = 1_000   # EU 2015/847 Wire Transfer Regulation
FATF_HIGH_RISK_THRESHOLD = 15_000               # FATF high-value threshold

# High-risk jurisdictions (FATF grey/black list, EU high-risk third countries)
HIGH_RISK_COUNTRIES = {
    "AF", "KP", "IR", "MM", "RU", "BY", "SY", "YE", "VE",
    "CU", "SD", "SS", "ZW", "LY", "IQ", "SO", "CF", "CD",
    "BI", "HT", "ML", "NI", "PK", "PH", "TN", "VU", "BB",
    "JM", "TT", "PA", "GH", "SN", "MR", "UG"
}

# EU Member State codes (SEPA zone — lower risk baseline)
EU_MEMBER_STATES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES",
    "FI", "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU",
    "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"
}

# Management notification recipients
TOP_MANAGEMENT_EMAILS = [
   "kirankumar.dangetį@cgi.com",
   "werner.ziegler@cgi.com"  # Cheif Compliance Officer   
]

# Fuzzy matching threshold for name screening (0-100)
NAME_MATCH_THRESHOLD = 75   # ≥75% similarity triggers watchlist hit
EXACT_MATCH_THRESHOLD = 95  # ≥95% triggers CRITICAL alert

# BaFin reporting contacts
BAFIN_FIU_ENDPOINT = "https://goaml.bafin.de/report"   # sandbox simulation
