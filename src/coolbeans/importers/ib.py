from os import path
import datetime
from datetime import timedelta, date
import logging

from ibflex import client, parser, Types, FlexQueryResponse, FlexStatement
from ibflex.enums import CashAction

from beancount.query import query
from beancount.parser import options
from beancount.ingest import importer, cache
from beancount.core import data, amount
from beancount.core.number import D


# create a logger
logger = logging.getLogger(__name__)


def parse_file(file_name):
    """Wrapper callback for file cache"""
    return parser.parse(file_name)


class Importer(importer.ImporterProtocol):
    """An importer for Interactive Broker using the flex query service.

    ib.Importer(account="Assets:Investment:IB")

     Todo Items:

     * use 'account-type' instead of symbol for the sub-accounts
       that would be values like: option, future, stock, cash
     * allow for passing a mapping of 'account-number' -> 'short-name'

    """

    REQUIRED_ACCOUNTS = ('root', 'fees')
    accounts:dict = None

    def __init__(
            self,
            accounts:dict,
            prefix_account_id=True,
            add_balance=True,
            commodity_accounts=True,
            ib_account_id=None,
    ):
        """

        :param accounts:
        :param prefix_account_id: set to true such that We insert the Account_ID after the root account:
            Assets:Investment:IB:[Account-id]:[Commodity]
        :param add_balance: When True we try to include 'balance' statements from positions
        :param ib_account_id: Optional the ib_account_id to use incase there are multiple accounts in the
            statement.  By default we parse only the first statement.

        Possible TODO to parse all accounts.
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

    def identify(self, file:cache._FileMemo) -> bool:
        try:
            self._parse_statement(file)
        except:
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
        # return f"ibflex_{statement.accountId}_{statement.fromDate.strftime('%Y-%m-%d')}_{statement.toDate.strftime('%Y-%m-%d')}.xml"
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
        symbol = ib_symbol.replace(' ', '').replace('_', '').replace('.', '')
        if symbol[0].isdigit():
            return "X" + symbol
        else:
            return symbol

    def account_for_symbol(self, statement, ib_symbol):
        symbol = self.clean_symbol(ib_symbol)
        root_account = self.accounts['root']
        if self.prefix_account_id:
            root_account = root_account + ":" + statement.accountId

        return root_account + ":" + symbol

    def extract(self, file:cache._FileMemo, existing_entries=None):
        """
        ibflex allows for several "sections", each one has some good tidbits. We support reports with some or all
        of he sections.  These are mostly handled in "extract_[name]" methods.  Here we call each, and it returns
        an empty list if there's no data for that section in the file.

        """
        statement = self._parse_statement(file)

        commodities = self.extract_commodities(statement, existing_entries)
        prices = self.extract_prices(statement, existing_entries)
        trades = self.extract_trades(statement, existing_entries)

        return commodities + prices + trades

    def extract_cash_transaction(self, statement: FlexStatement, existing_entries:list=None):
        """
        for item in statement.CashTransactions: print(f"{item.dateTime} {item.type.name}: {item.currency} {item.amount}: {item.description}");

        https://www.interactivebrokers.com/en/software/reportguide/reportguide/cash_transactionsfq.htm

        Some fun things to import:
        2020-04-03 00:00:00 DEPOSITWITHDRAW: USD 1500000: CASH RECEIPTS / ELECTRONIC FUND TRANSFERS
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

        match_key = 'execution-id'

        existing_by_key = self.find_existing(existing_entries, match_key)

        result = []
        for trade in statement.Trades:

            if trade.extExecID in existing_by_key:
                continue

            meta = {
                'lineno': 0,
                'filename': '',
                match_key: trade.extExecID,
                'order-id': trade.ibOrderID,
                'exchange': trade.exchange,
                'multiplier': trade.multiplier,
                'commission': trade.ibCommission,
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

            narration = f"{trade.buySell.name} {trade.quantity} {safe_symbol} @ {trade.tradePrice} {trade.currency} on {trade.exchange}"
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
                        cost=None, #cost_amount, # cost=(Cost, CostSpec, None),
                        price=post_price,
                        flag=None,
                        meta={}
                    ),
                    # How does this affect our Cash?
                    data.Posting(
                        account=cost_account,
                        units=cash_amount,
                        cost=None,  # cost=(Cost, CostSpec, None),
                        price=None,
                        flag=None,
                        meta={}
                    ),

                    # Total Fees
                    data.Posting(
                        account=fees_cost_account,
                        units=amount.Amount(trade.ibCommission, trade.ibCommissionCurrency),
                        cost=None,
                        price=None,
                        flag=None,
                        meta={}
                    ),
                   data.Posting(
                       account=fees_account,
                       units=amount.Amount(-trade.ibCommission, trade.ibCommissionCurrency),
                       cost=None,
                       price=None,
                       flag=None,
                       meta={}
                   )
                ]
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
