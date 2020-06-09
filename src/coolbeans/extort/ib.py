"""Example Extorter, useful as a starting point"""

import typing
import logging
import dataclasses
import datetime

# 3rdparty
import slugify

# We use ibflex
from ibflex import parser, FlexStatement, CashAction


from coolbeans.extort.base import ExtortionProtocol

from coolbeans.tools.seeds import Trade, Transfer, Expense, Income, EventDetail


logger = logging.getLogger(__name__)


def trade_key(trade):
    if trade.openCloseIndicator:
        o = trade.openCloseIndicator.name + ':'
    else:
        o = ''
    return f"{o}{trade.tradeDate.strftime('%Y-%m-%d')}:{trade.ibOrderID}"


def clean_symbol(symbol: str) -> str:
    symbol = slugify.slugify(symbol, separator='_')

    if symbol[0].isdigit():
        symbol = "X" + symbol

    symbol = symbol.upper()

    return symbol


class Extorter(ExtortionProtocol):

    FILE_OPEN_MODE = None  # This requires a file-name, not a

    ib_account_id = ""

    def extort(self, stream: typing.Union[typing.IO[typing.AnyStr], str]):
        """Extract as much information as possible from the workbook"""
        for statement in parser.parse(stream).FlexStatements:
            for record in self.extract_cash(statement):
                yield dataclasses.asdict(record)
            for trade in self.extract_trades(statement):
                yield dataclasses.asdict(trade)

    @staticmethod
    def extract_cash(statement: FlexStatement):
        """
        Args:
            statement: The Statement to extract entries from

        Returns:
            iterator of DataClass instances for these records
        """

        for record in statement.CashTransactions:
            date = record.dateTime

            if record.type in (
                CashAction.DEPOSITWITHDRAW,
            ):
                yield Transfer(
                    id=record.transactionID,
                    date=date,
                    amount=record.amount,
                    currency=record.currency,
                    subaccount=record.accountId,
                    narration=record.description,
                    event_detail=EventDetail.TRANSFER_DEPOSIT.name if record.amount > 0 else EventDetail.TRANSFER_WITHDRAWAL.name,
                    meta={
                        'type': record.type.value,
                        'rate': record.fxRateToBase
                    }
                )
            elif record.amount < 0:
                event_detail = EventDetail.EXPENSE_FEES
                if record.type in (CashAction.BONDINTPAID, CashAction.BROKERINTPAID):
                    event_detail = EventDetail.EXPENSE_INTEREST
                if record.type == CashAction.WHTAX:
                    event_detail = EventDetail.EXPENSE_TAX

                yield Expense(
                    id=record.transactionID,
                    date=date,
                    amount=record.amount,
                    event_detail=event_detail,
                    currency=record.currency,
                    subaccount=record.accountId,
                    narration=record.description,
                    meta={
                        'type': record.type.value,
                        'rate': record.fxRateToBase
                    }
                )
            else:
                yield Income(
                    id=record.transactionID,
                    date=date,
                    amount=record.amount,
                    currency=record.currency,
                    subaccount=record.accountId,
                    narration=record.description,
                    meta={
                        'type': record.type.value,
                        'rate': record.fxRateToBase
                    }
                )

    @staticmethod
    def extract_trades(statement: FlexStatement):
        """Pull Trades from a FlexStatement
        """

        by_order: typing.Dict[str, Trade] = {}

        for trade in statement.Trades:
            key = trade_key(trade)

            assert key.strip(), f"Invalid Key {len(key)}"

            if not trade.openCloseIndicator:
                # This isn't a trade at all.
                continue

            if key in by_order:
                combined = by_order[key]
                combined.add_trade(
                    quantity=trade.quantity * trade.multiplier,
                    price=trade.tradePrice,
                    fees=trade.ibCommission
                )
            else:
                seed = Trade(
                    id=key,
                    date=trade.tradeDate,
                    price=trade.tradePrice,
                    currency=trade.currency,
                    quantity=trade.quantity * trade.multiplier,
                    commodity=clean_symbol(trade.symbol),

                    fees=trade.ibCommission,
                    fees_currency=trade.ibCommissionCurrency,
                    subaccount=trade.accountId,

                    event_detail=EventDetail.TRADE_OPEN if trade.openCloseIndicator.name == 'OPEN' else EventDetail.TRADE_CLOSE,

                    meta={
                        'exchange': trade.exchange,
                        'symbol': trade.symbol,
                    }
                )
                by_order[key] = seed

        for trade in by_order.values():
            yield trade

        #   if trade.securityID is None and "." in trade.symbol:
        #       # FOREX Trade, not really a valid Symbol at all
        #       # TODO: Better check than blank securityID
        #       # Usually [currency].[commodity].  For example GBP.JPY
        #       # In that case trade.currency is JPY, so we just need to parse out the GBP part
        #       safe_symbol, _ = trade.symbol.split('.')
        #   else:
        #       safe_symbol = self.clean_symbol(trade.symbol)
