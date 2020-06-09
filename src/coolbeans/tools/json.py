from typing import Any
import json
import enum
import decimal
import datetime


class CoolJsonEncoder(json.JSONEncoder):
    ensure_ascii = False
    allow_nan = False

    def default(self, o: Any) -> Any:
        """Given an object o, check for conversion functions for it."""
        if isinstance(o, (datetime.datetime, datetime.date)):
            return o.strftime("%Y-%m-%d")
        elif isinstance(o, enum.Enum):
            return o.name
        elif isinstance(o, decimal.Decimal):
            return float(o)
        return o
