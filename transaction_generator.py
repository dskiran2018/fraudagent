"""
Sandbox transaction generator — creates realistic international payment scenarios
including seeded criminal name matches for POC demonstration.
"""
import random
import uuid
from datetime import datetime, timezone


def _txn_id() -> str:
    return f"TXN-{uuid.uuid4().hex[:12].upper()}"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


NORMAL_TRANSACTIONS = [
    {
        "transaction_id": _txn_id(),
        "timestamp": _ts(),
        "type": "WIRE_TRANSFER",
        "amount": 2500.00,
        "currency": "EUR",
        "sender": {
            "name": "Hans Mueller",
            "account": "DE89370400440532013000",
            "bank": "Deutsche Bank AG",
            "country": "DE",
        },
        "beneficiary": {
            "name": "Sophie Leclerc",
            "account": "FR7630006000011234567890189",
            "bank": "BNP Paribas",
            "country": "FR",
        },
        "purpose": "Invoice payment INV-2024-1187",
        "ip_address": "93.184.216.34",
        "device_fingerprint": "fp_abc12345",
    },
    {
        "transaction_id": _txn_id(),
        "timestamp": _ts(),
        "type": "SEPA_TRANSFER",
        "amount": 850.00,
        "currency": "EUR",
        "sender": {
            "name": "Maria Garcia",
            "account": "ES9121000418450200051332",
            "bank": "Banco Santander",
            "country": "ES",
        },
        "beneficiary": {
            "name": "Jan De Vries",
            "account": "NL91ABNA0417164300",
            "bank": "ABN AMRO",
            "country": "NL",
        },
        "purpose": "Rent payment",
        "ip_address": "80.58.192.1",
        "device_fingerprint": "fp_def67890",
    },
]

SUSPICIOUS_TRANSACTIONS = [
    # Criminal name match — Ruja Ignatova (OneCoin Cryptoqueen)
    {
        "transaction_id": _txn_id(),
        "timestamp": _ts(),
        "type": "INTERNATIONAL_WIRE",
        "amount": 487_500.00,
        "currency": "EUR",
        "sender": {
            "name": "Ruja Ignatova",
            "account": "BG80BNBG96611020345678",
            "bank": "Fibank Bulgaria",
            "country": "BG",
        },
        "beneficiary": {
            "name": "OneLife Network Ltd",
            "account": "AE070331234567890123456",
            "bank": "Mashreq Bank UAE",
            "country": "AE",
        },
        "purpose": "Business investment",
        "ip_address": "77.99.109.10",
        "device_fingerprint": "fp_xyz99999",
        "velocity_flag": True,
        "prior_transactions_24h": 3,
        "prior_amount_24h": 1_200_000.00,
    },
    # Criminal name match — Maxim Yakubets (Evil Corp)
    {
        "transaction_id": _txn_id(),
        "timestamp": _ts(),
        "type": "INTERNATIONAL_WIRE",
        "amount": 95_000.00,
        "currency": "USD",
        "sender": {
            "name": "Maxim Yakubets",
            "account": "RU123456789012345678901",
            "bank": "Sberbank Russia",
            "country": "RU",
        },
        "beneficiary": {
            "name": "Apex Digital Solutions LLC",
            "account": "CY17002001280000001200527600",
            "bank": "Bank of Cyprus",
            "country": "CY",
        },
        "purpose": "IT consulting services",
        "ip_address": "95.213.204.21",
        "device_fingerprint": "fp_rus12345",
        "velocity_flag": False,
        "prior_transactions_24h": 1,
        "prior_amount_24h": 95_000.00,
    },
    # Criminal name match — Daniel Kinahan (Kinahan Cartel)
    {
        "transaction_id": _txn_id(),
        "timestamp": _ts(),
        "type": "INTERNATIONAL_WIRE",
        "amount": 250_000.00,
        "currency": "EUR",
        "sender": {
            "name": "Daniel Kinahan",
            "account": "AE390330000010191001345",
            "bank": "Emirates NBD",
            "country": "AE",
        },
        "beneficiary": {
            "name": "Elite Sports Management FZE",
            "account": "MT84MALT011000012345MTLCAST001S",
            "bank": "APS Bank Malta",
            "country": "MT",
        },
        "purpose": "Sports management fee",
        "ip_address": "212.117.65.23",
        "device_fingerprint": "fp_uae88888",
        "velocity_flag": True,
        "prior_transactions_24h": 5,
        "prior_amount_24h": 750_000.00,
    },
    # Alias match — "El Chapo" account transfer
    {
        "transaction_id": _txn_id(),
        "timestamp": _ts(),
        "type": "INTERNATIONAL_WIRE",
        "amount": 1_200_000.00,
        "currency": "USD",
        "sender": {
            "name": "Joaquin Guzman Loera",
            "account": "MX53BAOR180000000000000000",
            "bank": "Banco Azteca",
            "country": "MX",
        },
        "beneficiary": {
            "name": "Pacific Rim Investments SA",
            "account": "PA73480000000010501212341",
            "bank": "Balboa Bank Panama",
            "country": "PA",
        },
        "purpose": "Investment transfer",
        "ip_address": "189.203.68.94",
        "device_fingerprint": "fp_mex44444",
        "velocity_flag": True,
        "prior_transactions_24h": 8,
        "prior_amount_24h": 4_500_000.00,
    },
    # Sanctioned oligarch — Roman Abramovich
    {
        "transaction_id": _txn_id(),
        "timestamp": _ts(),
        "type": "INTERNATIONAL_WIRE",
        "amount": 3_500_000.00,
        "currency": "EUR",
        "sender": {
            "name": "Roman Abramovich",
            "account": "IL620108000000099999999",
            "bank": "Bank Leumi Israel",
            "country": "IL",
        },
        "beneficiary": {
            "name": "Millhouse Capital Management",
            "account": "CH5604835012345678009",
            "bank": "UBS Switzerland",
            "country": "CH",
        },
        "purpose": "Asset management transfer",
        "ip_address": "91.200.14.12",
        "device_fingerprint": "fp_isr55555",
        "velocity_flag": False,
        "prior_transactions_24h": 2,
        "prior_amount_24h": 3_500_000.00,
    },
    # High-risk country + structuring pattern (just below threshold)
    {
        "transaction_id": _txn_id(),
        "timestamp": _ts(),
        "type": "INTERNATIONAL_WIRE",
        "amount": 9_800.00,  # just below €10k BaFin threshold — structuring indicator
        "currency": "EUR",
        "sender": {
            "name": "Ahmed Al-Rashid",
            "account": "IQ12345678901234567890",
            "bank": "Trade Bank of Iraq",
            "country": "IQ",
        },
        "beneficiary": {
            "name": "Global Trade Solutions GmbH",
            "account": "DE29700100100987654321",
            "bank": "Commerzbank",
            "country": "DE",
        },
        "purpose": "Goods payment",
        "ip_address": "31.40.183.200",
        "device_fingerprint": "fp_iqq33333",
        "velocity_flag": True,
        "prior_transactions_24h": 4,
        "prior_amount_24h": 38_400.00,  # 4 × ~€9,800 = structuring
    },
]


def get_demo_transactions() -> list[dict]:
    """Return the full demo transaction set for POC demonstration."""
    return NORMAL_TRANSACTIONS + SUSPICIOUS_TRANSACTIONS


def get_random_transaction(include_suspicious: bool = True) -> dict:
    pool = SUSPICIOUS_TRANSACTIONS if include_suspicious else NORMAL_TRANSACTIONS
    return random.choice(pool)


def get_transaction_by_criminal(criminal_name: str) -> dict | None:
    """Return a transaction seeded with a specific criminal's name."""
    name_lower = criminal_name.lower()
    for txn in SUSPICIOUS_TRANSACTIONS:
        if name_lower in txn["sender"]["name"].lower():
            return txn
    return None
