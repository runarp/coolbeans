"""
Simple Bitfinex Importer of trades

BTC/USD	2020-05-24	45511322859	USD	44000	5 -176
"""
# stdlib imports
import dataclasses
import typing
import datetime
from decimal import Decimal
from collections import defaultdict

# beancount imports
from beancount.core import data, account
from beancount.core.position import CostSpec
from beancount.core.number import MISSING
from beancount.core.amount import Amount
from beancount.loader import printer


csvdata = """
BTC/USD	2020-05-24	45511322859	USD	44000	5	-176
"""

Q = Decimal("0.00000001")

@dataclasses.dataclass
class TradeRecord:
    def __post_init__(self):
        if isinstance(self.date, str):
            self.date = datetime.date(*(int(i) for i in self.date.split('-')))
        self.amount = Decimal(self.amount).quantize(Q)
        self.quantity = Decimal(self.quantity).quantize(Q)
        self.fee = Decimal(self.fee).quantize(Q)
        self.price = (self.amount / self.quantity).quantize(Q)
        self.commodity, _ = self.pair.split('/')

    #BTC/USD	2020-05-10	44874541663	USD	472500	50	-283.5
    pair: str
    date: datetime.date
    order_id: str
    currency: str
    amount: Decimal
    quantity: Decimal
    fee: Decimal

    price: Decimal = dataclasses.field(default_factory=Decimal)
    commodity: str = dataclasses.field(default="")

    def __str__(self):
        return f"{self.quantity} {self.pair} at {self.price} and fee {self.fee}"

def records_from_string(csvstring):
    for row in csvstring.split_type('\n'):
        row = row.strip()
        if row:
            records = row.split_type('\t')
            print(';', records)
            yield TradeRecord(*records)

# price = Amount(6950, "USD")
# cost = CostSpec(MISSING, None, MISSING, None, None, False)
# units = 200
# currency = "BTC

# cost_spec = CostSpec(
#     number_per=MISSING,
#     number_total=None,
#     currency=MISSING,
#     date=None,
#     label=None,
#     merge=False)

empty_cost_spec = CostSpec(
    number_per=MISSING,
    number_total=None,
    currency=MISSING,
    date=None,
    label=None,
    merge=False
)


def main():
    position_account = "Liabilities:Crypto:Bitfinex:Positions"
    margin_account   = "Liabilities:Crypto:Bitfinex:Positions"
    income_account = "Income:Crypto:Bitfinex:Realized"

    fee_account = "Expenses:Trading:Bitfinex:Fees:Trading"

    positions:typing.Dict[str, Decimal] = defaultdict(Decimal)
    balances:typing.Dict[str, datetime.date] = defaultdict(lambda: datetime.date(2000, 1, 1))

    records = list(records_from_string(csvdata))
    records.sort(key=lambda r:(r.date, r.commodity, -r.quantity))

    entries = []
    for record in records:

        # Now, we need to Handle the Incoming Account, Only if our Absolute
        # Position is decreasing:
        current_position = positions[record.commodity]
        new_position = current_position + record.quantity
        positions[record.commodity] = new_position

        # This is the account who's position we need to track for our lots
        commodity_account = account.join(position_account, record.commodity)

        if balances[commodity_account] != record.date:
            entries.append(data.Balance(
                date=record.date,
                account=commodity_account,
                amount=Amount(current_position, record.commodity),
                tolerance=Q,
                diff_amount=None,
                meta=data.new_metadata("", 0)
            ))
            balances[commodity_account] = record.date

        entry = data.Transaction(
            date=record.date,
            narration=str(record),
            payee="",
            tags={"margin"},
            links=set(),
            flag='*',
            meta=data.new_metadata("",0, kvlist=dict(
                position=str(new_position),
                order_id=record.order_id
            )),
            postings=[]
        )
        # The Commodity Adjustment

        # Assets:Crypto:Bitfinex:Positions:BTC 200 BTC {} @ 6950 USD
        posting = data.Posting(
            account=commodity_account,
            units=data.Amount(record.quantity, record.commodity),
            cost=empty_cost_spec,
            price=Amount(record.price, record.currency),
            flag=None,
            meta=data.new_metadata("", 0)
        )
        entry.postings.append(posting)

        # The Currency Account Adjustment (based on Cost?)
        # ; Liabilities:Crypto:Bitfinex:Borrowed:USD     -1,390,102.19 USD
        data.create_simple_posting(
            entry=entry,
            account=account.join(margin_account, record.currency),
            number=-record.amount,
            currency=record.currency
        )
        if record.fee:
            # We add Two fee Records
            # ; Liabilities:Crypto:Bitfinex:Borrowed:USD               -839.747894 USD
            data.create_simple_posting(
                entry=entry,
                account=account.join(margin_account, record.currency),
                number=record.fee,
                currency=record.currency
            )
            data.create_simple_posting(
                entry=entry,
                account=fee_account,
                number=-record.fee,
                currency=record.currency
            )

        if abs(new_position) < abs(current_position):
            # Add an Income Account Entry
            data.create_simple_posting(
                entry=entry,
                account=income_account,
                number=None,
                currency=None
            )
        entries.append(entry)

    printer.print_entries(entries)

if __name__ == "__main__":
    main()
