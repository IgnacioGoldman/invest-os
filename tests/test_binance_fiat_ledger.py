from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.sources.binance import _fetch_fiat_orders  # noqa: E402


class FakeBinanceClient:
    def __init__(self, responses: dict[int, list[list[dict[str, Any]]]]):
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def _signed_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert path == "/sapi/v1/fiat/orders"
        assert params is not None
        self.calls.append(params)
        transaction_type = int(params["transactionType"])
        page = int(params["page"])
        pages = self.responses.get(transaction_type, [])
        rows = pages[page - 1] if page <= len(pages) else []
        return {"data": rows}


class BinanceFiatLedgerTest(unittest.TestCase):
    def test_imports_all_paginated_fiat_deposits_with_original_and_credited_amounts(self) -> None:
        failed_rows = [
            {
                "orderNo": f"failed-{index}",
                "fiatCurrency": "EUR",
                "indicatedAmount": "1.00",
                "amount": "1.00",
                "status": "Failed",
                "createTime": 1761640919000 + index,
            }
            for index in range(498)
        ]
        client = FakeBinanceClient(
            {
                0: [
                    [
                        {
                            "orderNo": "card-20251028",
                            "fiatCurrency": "EUR",
                            "indicatedAmount": "5000.00",
                            "amount": "4900.00",
                            "totalFee": "100.00",
                            "method": "Card (VISA/Mastercard)",
                            "status": "Successful",
                            "createTime": 1761640919000,
                            "updateTime": 1761640919000,
                        },
                        {
                            "orderNo": "sepa-20251104",
                            "fiatCurrency": "EUR",
                            "indicatedAmount": "5000.00",
                            "amount": "5000.00",
                            "totalFee": "0",
                            "method": "Bank transfer (SEPA Instant)",
                            "status": "Successful",
                            "createTime": 1762239522000,
                            "updateTime": 1762239522000,
                        },
                        *failed_rows,
                    ],
                    [
                        {
                            "orderNo": "sepa-20251124",
                            "fiatCurrency": "EUR",
                            "indicatedAmount": "10000.00",
                            "amount": "10000.00",
                            "totalFee": "0",
                            "method": "Bank transfer (SEPA Instant)",
                            "status": "Successful",
                            "createTime": 1763985555000,
                            "updateTime": 1763985555000,
                        }
                    ],
                ],
                1: [[]],
            }
        )
        start = datetime(2025, 10, 1, tzinfo=timezone.utc)
        end = datetime(2025, 11, 30, 23, 59, 59, tzinfo=timezone.utc)

        deposits = _fetch_fiat_orders(client, start, end, transaction_type=0, label="deposits")
        withdrawals = _fetch_fiat_orders(client, start, end, transaction_type=1, label="withdrawals")

        self.assertEqual(withdrawals, [])
        self.assertEqual(len(deposits), 3)
        self.assertEqual([event.event_type for event in deposits], ["fiat_deposit", "fiat_deposit", "fiat_deposit"])
        self.assertEqual([event.raw["method"] for event in deposits], [
            "Card (VISA/Mastercard)",
            "Bank transfer (SEPA Instant)",
            "Bank transfer (SEPA Instant)",
        ])
        self.assertEqual([(event.original_amount, event.credited_amount, event.amount) for event in deposits], [
            (5000.0, 4900.0, 4900.0),
            (5000.0, 5000.0, 5000.0),
            (10000.0, 10000.0, 10000.0),
        ])
        self.assertEqual([event.created_at.isoformat() for event in deposits], [
            "2025-10-28T08:41:59+00:00",
            "2025-11-04T06:58:42+00:00",
            "2025-11-24T11:59:15+00:00",
        ])
        self.assertEqual([event.balance_changes for event in deposits], [
            {"EUR": 4900.0},
            {"EUR": 5000.0},
            {"EUR": 10000.0},
        ])
        self.assertEqual([call["transactionType"] for call in client.calls], [0, 0, 1])
        self.assertTrue(all(call["beginTime"] <= 1759276800000 for call in client.calls))
        self.assertTrue(all(call["endTime"] >= 1764547199000 for call in client.calls))


if __name__ == "__main__":
    unittest.main()
