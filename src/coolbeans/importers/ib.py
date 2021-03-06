import datetime
from datetime import timedelta
import logging
import dataclasses
import decimal
import typing
import sys

import slugify

from ibflex import client, parser, Types, FlexQueryResponse, FlexStatement

from beancount.ingest import importer, cache
from beancount.core import data, amount, account
from beancount.core.number import MISSING
from beancount.core.amount import Amount


# create a logger
logger = logging.getLogger(__name__)


def parse_file(file_name):
    """Wrapper callback for file cache"""
    return parser.parse(file_name)


EMPTY_COST_SPEC = data.CostSpec(
    number_per=MISSING,
    number_total=None,
    currency=MISSING,
    date=None,
    label=None,
    merge=False
)


@dataclasses.dataclass
class CombinedTrades:
    tradeDate: datetime.datetime
    ibOrderID: str
    tradePrice: decimal.Decimal
    exchange: str
    multiplier: int
    ibCommission: decimal.Decimal
    symbol: str
    safe_symbol: str
    buySell: str
    currency: str
    quantity: decimal.Decimal
    ibCommissionCurrency: str
    securityID: str
    openCloseIndicator: str

    @staticmethod
    def trade_key(trade):
        return f"{trade.openCloseIndicator}:{trade.tradeDate.strftime('%Y-%m-%d')}:{trade.ibOrderID}"

    def add_trade(self, quantity, price, comission: decimal.Decimal):
        self.ibCommission += comission

        current_quant = self.quantity
        current_price = self.tradePrice

        self.quantity += quantity
        # Use Quantity weighted average Price
        self.tradePrice = ((current_quant*current_price) + (quantity*price)) / self.quantity


class Importer(importer.ImporterProtocol):
    """An importer for Interactive Broker using the flex query service.

    ib.Importer(account="Assets:Investment:IB")

     Todo Items:

     * use 'account-type' instead of symbol for the sub-accounts
       that would be values like: option, future, stock, cash
     * allow for passing a mapping of 'account-number' -> 'short-name'

    """

    REQUIRED_ACCOUNTS = ('root', 'fees')
    accounts: dict = None

    def __init__(
            self,
            accounts: dict,
            prefix_account_id=True,
            add_balance=True,
            commodity_accounts=True,
            ib_account_id=None,
    ):
        """

        :param accounts: Dict of accounts used by the importer, for example:
            {
                'root': "Assets:Investment:IB",
                'fees': "Expenses:IB:Fees"
            }
        :param prefix_account_id: set to True such that We insert the
            Account_ID after the root account:

            Assets:Investment:IB:[Account-id]:[Commodity]

        :param add_balance: When True we try to include 'balance' statements from positions
            NOT IMPLEMETED YET--always True

        :param ib_account_id: Optional the ib_account_id to use incase there are multiple accounts in the
            statement.  By default we parse only the first statement.

        Possible TODO to parse all accounts?

        """

        self.accounts = accounts
        self.prefix_account_id = prefix_account_id
        self.add_balance = add_balance
        self.commodity_accounts = commodity_accounts
        self.ib_account_id = ib_account_id
        for key in self.REQUIRED_ACCOUNTS:
            assert key in accounts

    def name(self):
        return "ib.Importer"

    def identify(self, file: cache._FileMemo) -> bool:
        try:
            self._parse_statement(file)
        except Exception:
            return False
        return True

    def file_account(self, file):
        statement = self._parse_statement(file)
        return f"{self.accounts['root']}:{statement.accountId}"

    def file_date(self, file):
        statement = self._parse_statement(file)
        return statement.toDate

    def file_name(self, file):
        statement = self._parse_statement(file)

        if statement.Trades:
            return "ibflex-trades.xml"
        elif statement.OpenPositions:
            return "ibflex-positions.xml"

    def _parse_statement(self, file: cache._FileMemo) -> FlexStatement:
        """Try to parse this file"""
        query_obj:FlexQueryResponse = file.convert(parse_file)
        assert isinstance(query_obj, Types.FlexQueryResponse)

        statements = query_obj.FlexStatements
        if len(statements) > 1 and self.ib_account_id:
            # We have multiple statements in this object.  We only support One, but can optionally
            # Allow the user to specify the specific Account to use:
            for stmt in statements:
                logger.debug(f"looking at: {stmt.accountId}")
                if stmt.accountId == self.ib_account_id:
                    return stmt
            raise ValueError(f"Unable to find {self.ib_account_id} in query response.")

        statement = statements[0]
        if self.ib_account_id:
            # Just a reality check if we did pass in the accountId
            assert self.ib_account_id == statement.accountId
        else:
            self.ib_account_id = statement.accountId
        return statement

    def clean_symbol(self, ib_symbol):
        symbol = slugify.slugify(ib_symbol)
        #  symbol = ib_symbol.replace(' ', '').replace('_', '').replace('.', '')
        if symbol[0].isdigit():
            symbol = "X" + symbol
        symbol = symbol.upper()
        symbol = symbol.replace('-', '')
        return symbol

    def account_for_symbol(self, statement, ib_symbol):
        symbol = self.clean_symbol(ib_symbol)
        root_account = self.accounts['root']

        if self.prefix_account_id:
            root_account = account.join(root_account, statement.accountId)

        return account.join(root_account, symbol)

    def extract(self, file: cache._FileMemo, existing_entries=None):
        """
        ibflex allows for several "sections", each one has some good tidbits. We support reports with some or all
        of he sections.  These are mostly handled in "extract_[name]" methods.  Here we call each, and it returns
        an empty list if there's no data for that section in the file.

        """
        statement = self._parse_statement(file)

        commodities = self.extract_commodities(statement, existing_entries)
        prices = self.extract_prices(statement, existing_entries)
        trades = self.extract_trades(statement, existing_entries)
        opens = self.extract_new_accounts(statement, existing_entries)

        return trades

        # return commodities + prices + trades + opens

    def extract_cash_transaction(self, statement: FlexStatement, existing_entries:list=None):
        """
        for item in statement.CashTransactions: print(f"{item.dateTime} {item.type.name}: {item.currency} {item.amount}:
        {item.description}");

        https://www.interactivebrokers.com/en/software/reportguide/reportguide/cash_transactionsfq.htm

        Some fun things to import:
        2020-04-03 00:00:00 DEPOSITWITHDRAW: USD 15000: CASH RECEIPTS / ELECTRONIC FUND TRANSFERS
        2020-01-06 00:00:00 BROKERINTPAID: JPY -295: JPY DEBIT INT FOR DEC-2019
        2020-05-05 17:40:38 FEES: USD 10: P*****07:SNAPSHOTVALUENONPRO FOR APR 2020
        2020-04-01 20:20:00 WHTAX: USD -142.2: SDS(US74347B3832) PAYMENT IN LIEU OF DIVIDEND - US TAX
        2020-02-13 20:20:00 DIVIDEND: USD 385: AAPL(US0378331005) CASH DIVIDEND USD 0.77 PER SHARE (Ordinary Dividend)
        2020-03-31 20:20:00 PAYMENTINLIEU: USD -320: WH(US98311A1051) PAYMENT IN LIEU OF DIVIDEND (Ordinary Dividend)


        :param statement: The Parsed IBFlex Statement
        :param existing_entries: List of entries from BeanCount
        :return:
        """
        return []

    def find_existing(self, existing_entries:list, key):
        matches = {}
        if not existing_entries:
            return matches
        for entry in existing_entries:
            if key in entry.meta:
                matches[entry.meta[key]] = entry
        return matches

    def extract_trades(self, statement: FlexStatement, existing_entries:list=None):
        """
        Version one does not attempt to group by order ID.  This allows for perfect lot pricing and simpler
        implementation.  The downside is it's very verbose.

            txn = data.Transaction(meta, date, self.FLAG, payee, narration,
                                   tags, data.EMPTY_SET, [])

        * https://www.interactivebrokers.com/en/software/reportguide/reportguide/tradesfq.htm

        TODO: Handle Duplicates
        """
        fees_account = self.accounts['fees']

        match_key = 'id'

        existing_by_key = self.find_existing(existing_entries, match_key)

        by_order:typing.Dict[str, CombinedTrades] = {}

        for trade in statement.Trades:
            key = CombinedTrades.trade_key(trade)
            assert key.strip(), f"Invalid Key {len(key)}"
            if not trade.openCloseIndicator:
                continue
            if key in by_order:
                combined = by_order[key]
                combined.add_trade(trade.quantity, trade.tradePrice, trade.ibCommission)
            else:
                combined = CombinedTrades(
                    ibOrderID=trade.ibOrderID,
                    tradeDate=trade.tradeDate,
                    tradePrice=trade.tradePrice,
                    exchange=trade.exchange,
                    multiplier=trade.multiplier,
                    ibCommission=trade.ibCommission,
                    symbol=trade.symbol,
                    currency=trade.currency,
                    safe_symbol=self.clean_symbol(trade.symbol),
                    buySell=trade.buySell,
                    quantity=trade.quantity,
                    securityID=trade.securityID,
                    ibCommissionCurrency=trade.ibCommissionCurrency,
                    openCloseIndicator=trade.openCloseIndicator.name
                )
                by_order[key] = combined

        result = []
        for trade in by_order.values():

            key = CombinedTrades.trade_key(trade)
            if key in existing_by_key:
                continue

            meta = {
                'lineno': 0,
                'filename': '',
                match_key: key,
                'order_id': trade.ibOrderID,
                'exchange': trade.exchange,
#               'multiplier': str(trade.multiplier),
#               'commission': trade.ibCommission,
            }

            # TODO Make this a parameter
            payee = "IB"

            if trade.securityID is None and "." in trade.symbol:
                # FOREX Trade, not really a valid Symbol at all
                # TODO: Better check than blank securityID
                # Usually [currency].[commodity].  For example GBP.JPY
                # In that case trade.currency is JPY, so we just need to parse out the GBP part
                safe_symbol, _ = trade.symbol.split('.')
            else:
                safe_symbol = self.clean_symbol(trade.symbol)

            narration = (f"{trade.buySell.name} {trade.quantity} {safe_symbol} @ "
                         f"{trade.tradePrice} {trade.currency} on {trade.exchange}")

            tags = data.EMPTY_SET

            # cost = data.Amount(trade.cost, trade.currency)

            cost_account = self.account_for_symbol(statement, trade.currency)
            fees_cost_account = self.account_for_symbol(statement, trade.ibCommissionCurrency)
            comm_account = self.account_for_symbol(statement, safe_symbol)

            # This is how much USD it cost us
            # cost_amount = data.Cost(number=trade.netCash, currency=trade.currency, date=trade.tradeDate, label=f"xxx")
            cash_amount = amount.Amount(-trade.quantity * trade.multiplier * trade.tradePrice, trade.currency)
            unit_amount = amount.Amount( trade.quantity * trade.multiplier, safe_symbol)

            # post_price = data.Price(currency=trade.currency, amount=trade.tradePrice, meta={}, date=trade.tradeDate)
            post_price = data.Amount(trade.tradePrice, trade.currency)
            txn = data.Transaction(
                meta,
                trade.tradeDate,
                self.FLAG,
                "", # payee,
                narration,
                tags,
                data.EMPTY_SET, # {link} -- what is this?
                [
                    data.Posting(
                        account=comm_account,
                        units=unit_amount,
                        cost=EMPTY_COST_SPEC, #cost_amount, # cost=(Cost, CostSpec, None),
                        price=post_price,
                        flag=self.FLAG,
                        meta={}
                    ),
                    # How does this affect our Cash?
                    data.Posting(
                        account=cost_account,
                        units=cash_amount,
                        cost=None,  # cost=(Cost, CostSpec, None),
                        price=None,
                        flag=self.FLAG,
                        meta={}
                    ),
                    # Total Fees
                    data.Posting(
                        account=fees_cost_account,
                        units=amount.Amount(trade.ibCommission, trade.ibCommissionCurrency),
                        cost=None,
                        price=None,
                        flag=self.FLAG,
                        meta={}
                    ),
                   data.Posting(
                       account=fees_account,
                       units=amount.Amount(-trade.ibCommission, trade.ibCommissionCurrency),
                       cost=None,
                       price=None,
                       flag=self.FLAG,
                       meta={}
                   )
                ]
            )
            if trade.openCloseIndicator == "CLOSE":
                # This is a reduction in position, add the Income Account:
                data.create_simple_posting(
                    entry=txn,
                    account=self.accounts.get('income', 'Income:FIXME'),
                    number=None,
                    currency=None
                )
            result.append(txn)

        return result

    def extract_prices(self, statement: FlexStatement, existing_entries:list=None):
        """
        IBFlex XML Files can contain an object called 'OpenPositions',
        this is very useful because it lets us create

        - Balance assertions
        - Price entries from the Mark
        """
        result = []
        for position in statement.OpenPositions:
            price = position.markPrice
            safe_symbol = self.clean_symbol(position.symbol)
            # Dates are 12 Midnight, let's make it the next day
            date = statement.toDate + timedelta(days=1)
            result.append(
                # TODO De-Duplicate
                data.Price(
                    currency=safe_symbol,
                    amount=data.Amount(price, "USD"),
                    date=date,
                    meta={
                        'lineno': 0,
                        'filename': '',
                    }
                )
            )
            account = self.account_for_symbol(statement, position.symbol)
            result.append(
                data.Balance(
                    account=account,
                    amount=data.Amount(position.position * position.multiplier, safe_symbol),
                    date=statement.toDate + timedelta(days=1),
                    meta={'lineno': 0, 'filename': ''},
                    tolerance=0.5,
                    diff_amount=0,
                )
            )
        return result

    def extract_new_accounts(self, statement: FlexStatement, existing_entries:list=None):

        existing = {}
        root_account = self.accounts['root']

        existing_accounts = set()
        if existing_entries:
            for entry in existing_entries:
                if isinstance(entry, data.Open):
                    existing_accounts.add(entry.account)

        results = []
        for obj in statement.SecuritiesInfo:

            symbol = self.clean_symbol(obj.symbol)
            account_name = self.account_for_symbol(statement, symbol)

            if account_name in existing_accounts:
                continue

            meta = {
                'lineno': 0,
                'filename': '',
                'description': obj.description,
                'multiplier': obj.multiplier,
                'conid': obj.conid,
                'asset-type': obj.assetCategory.name.lower(),
            }
            if obj.cusip:
                meta['cusip'] = obj.cusip
            if obj.securityID:
                meta['security-id'] = obj.securityID

            entry = data.Open(
                date=datetime.date(2010, 1, 1),
                account=account_name,
                currencies=[symbol],
                meta=meta,
                booking=None,
            )
            results.append(entry)
        return results

    def extract_commodities(self, statement: FlexStatement, existing_entries:list=None):
        """
        TODO: Better Matching (on conid)
        """

        # Make a dict of all existing commodities
        existing_commodities = {}
        if existing_entries:
            for entry in existing_entries:
                if isinstance(entry, data.Commodity):
                    existing_commodities[entry.currency] = entry

        results = []
        for obj in statement.SecuritiesInfo:
            assert obj.conid, obj
            symbol = self.clean_symbol(obj.symbol)

            if symbol in existing_commodities:
                continue

            meta = {
                'lineno': 0,
                'filename': '',
                'description': obj.description,
                'multiplier': obj.multiplier,
                'conid': obj.conid,
                'asset-type': obj.assetCategory.name.lower(),
            }
            if obj.cusip:
                meta['cusip'] = obj.cusip
            if obj.securityID:
                meta['security-id'] = obj.securityID

            commodity = data.Commodity(
                currency=symbol,
                meta=meta,
                date=datetime.date(2010, 1, 1)
            )
            results.append(commodity)

        return results


if __name__ == "__main__":
    CONFIG = []
