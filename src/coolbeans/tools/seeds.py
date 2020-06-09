"""
Seeds help beans grow
"""

#  import typing
import datetime
import enum
from dataclasses import field, make_dataclass
from decimal import Decimal


class EventType(enum.Enum):
    """The Highest level event.  We use this to determine the type of journal entry that will be created"""
    TRANSFER = "Transfer"
    TRADE = "Trades"
    EXPENSE = "Expense"
    INCOME = "Income"


class EventDetail(enum.Enum):
    # Neutral
    TRANSFER_WITHDRAWAL = "Withdrawal"
    TRANSFER_DEPOSIT = "Deposit"

    TRADE_UNKNOWN = "Trade"
    TRADE_OPEN = "Open Position Trade"
    TRADE_CLOSE = "Close Position Trade"

    # Expenses Sub-types
    EXPENSE_OTHER = "Other Expense"
    EXPENSE_INTEREST = "Interest Expense"
    EXPENSE_TAX = "Tax Expense"
    EXPENSE_FEES = "Fees"

    # Income Sub-types
    INCOME_OTHER = "Other Income"
    INCOME_INTEREST = "Interest or Dividend Income"


BASE_FIELDS = [
    ('id', str),
    ('date', datetime.date),
]

# All have Defaults
TRANSACTION_FIELDS: list = [
    ('narration', str, field(default="")),

    ('payee', str, field(default="")),
    ('subaccount', str, field(default="")),

    ('meta', dict, field(default_factory=dict)),

    # Things we'd like to remember, but not import into beanfile
    ('context', dict, field(default_factory=dict))
]

TRADE_FIELDS = [
    ('commodity', str),  # The commodity/symbol.  Should be Account-Name Safe
    ('quantity', Decimal),  # How many we bought/sold
    ('currency', str),  # This is the traded price currency, eg. USD
    ('price', Decimal),  # This is the traded price, eg 100.00
    ('fees', Decimal),
    ('fees_currency', str),

    # This is the "type" and should be defaulted
    ('event_type', str, field(default=EventType.TRADE.name)),
    ('event_detail', str, field(default=EventDetail.TRADE_UNKNOWN.name)),
]

TRANSFER_FIELDS = [
    ('amount', str),
    ('currency', str),
    ('transfer_account', str, field(default='')),
    ('event_type', str, field(default=EventType.TRANSFER.name)),
    ('event_detail', str, field(default="")),
]

EXPENSE_FIELDS = [
    ('amount', str),
    ('currency', str),
    ('event_type', str, field(default=EventType.EXPENSE.name)),
    ('event_detail', str, field(default=EventDetail.EXPENSE_OTHER.name)),
]

INCOME_FIELDS = [
    ('amount', str),
    ('currency', str),
    ('event_type', str, field(default=EventType.INCOME.name)),
    ('event_detail', str, field(default=EventDetail.INCOME_OTHER.name)),
]

Transaction = make_dataclass("Transaction", BASE_FIELDS + TRANSACTION_FIELDS)
Transfer = make_dataclass("Transfer", BASE_FIELDS + TRANSFER_FIELDS + TRANSACTION_FIELDS)
Expense = make_dataclass("Expense", BASE_FIELDS + EXPENSE_FIELDS + TRANSACTION_FIELDS)
Income = make_dataclass("Income", BASE_FIELDS + INCOME_FIELDS + TRANSACTION_FIELDS)


def add_trade(self: "Trade", quantity: Decimal, price: Decimal, fees: Decimal) -> None:
    """Modifies an instance in place, adding a trade in such a way that price*quantity = stays correct
    even for executions at different prices.  IE, the weighted average price of the execution.
    """
    self.fees += fees

    current_quant = self.quantity
    current_price = self.price

    if current_quant < 0:
        assert quantity < 0, "Can only add trades in same direction"
    if current_quant >= 0:
        assert quantity >= 0, "Can only add trades in same direction"

    self.quantity += quantity

    # Use Quantity weighted average Price
    self.price = ((current_quant * current_price) + (quantity * price)) / self.quantity


Trade = make_dataclass(
    "Trade",
    BASE_FIELDS + TRADE_FIELDS + TRANSACTION_FIELDS,
    namespace=dict(add_trade=add_trade)
)
