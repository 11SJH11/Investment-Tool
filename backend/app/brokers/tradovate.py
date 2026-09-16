"""Read-only readiness scaffold. No transport and no invented API contract."""
class TradovateHistory:
    provider = "tradovate"

    @staticmethod
    def capability_report():
        return {"provider": "tradovate", "destination": "journal", "read_only": True,
                "supported": False, "closed_trades": False, "execution": False,
                "reason": "Unsupported: Tradovate history API contract and authentication are not implemented"}

    def accounts(self):
        return []

    def close(self):
        pass
