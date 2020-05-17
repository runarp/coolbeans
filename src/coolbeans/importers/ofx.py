import datetime
from datetime import timedelta
import logging

DEBUG = False

# logging.basicConfig(level="DEBUG")
from beancount.ingest import importer, cache
from beancount.ingest.cache import _FileMemo as FileMemo
from beancount.core import data, amount

# This guy does all the work
from ofxtools.Parser import OFXTree
from ofxtools.models.bank.stmt import CCSTMTRS, STMTTRN

from coolbeans import matcher


class Importer(importer.ImporterProtocol):

    def __init__(
            self,
            accounts:dict,
            account_number,
            base_name="ofx"
    ):
        self.accounts = accounts
        self.account_number = account_number
        self.base_name = base_name

    def name(self):
        return f"coolbeans.ofx"

    def auto_cofigure(self):
        """Pull the base configuration out of the Meta for the account:
            Searching for:
                'default-expense'
                'payment'
                'ofx-account-id'
        """

    def _parse_statement(self, file: FileMemo) -> CCSTMTRS:
        """
        for tx in doc.statements[0].transactions:
     ...:     print(f"{tx.dtposted}: {tx.trnamt} {tx.fitid} {tx.name}")

        We return a "CCSTMTRS" instance.  This has a few interesting properites:

        * curdef - the Currency of the statement
        * transactions - the List of Entries for each tx it has:
                tx.dtposted - datetime
                tx.trnamt - Decimal
                tx.fitid - String/unique
                tx.name - Name/Description

        * balance - balance.balamt -- balance
                    balance.dtasof -- datetime as of

        * account.acctid -- the Full account number (might be a CC number!)
        """
        try:
            parser = OFXTree()
            parser.parse(file.name)

            # Use the Convert to make this thing readable:
            ofx_doc = parser.convert()

            return ofx_doc.statements[0]
        except:
            if DEBUG:
                logging.exception(f"While Parsing {file}")

    def identify(self, file:cache._FileMemo) -> bool:
        try:
            statement = self._parse_statement(file)
            # Probably make this ends-with or re
            return statement.account.acctid == self.account_number
        except:
            return False

    def file_account(self, file):
        # statement = self._parse_statement(file)
        return self.accounts['root']

    def file_date(self, file) -> datetime.datetime:
        statement = self._parse_statement(file)
        return statement.dtend

    def file_name(self, file):
        return f"{self.base_name}.ofx"

    def find_existing(self, existing_entries:list, key, _type=None):
        matches = {}
        if not existing_entries:
            return matches
        for entry in existing_entries:
            if key in entry.meta:
                if not _type or type(entry) == _type:
                    matches[entry.meta[key]] = entry
        return matches

    def resolve_account(self, tx:STMTTRN, by_id:dict, existing_entries:list):
        # We might have a Payment:
        # TODO Make this an re parameter and use tx.trntype == "CREDIT"
        is_payment = tx.name.upper().find("PAYMENT") != -1

        if is_payment and tx.trnamt > 0:
            return self.accounts['payment']
        else:
            return self.accounts['default-expense']

        # TODO Need to do some matching based on entries.
        # TODO Also need to check for Payee

    def extract_balance(self, statement:CCSTMTRS, existing_entries=None):
        amount = statement.balance.balamt

        # Seems Chase doesn't provide a proper date for this:
        if statement.transactions:
            last_tx = statement.transactions[-1]
            bal_datetime = last_tx.dtposted
        else:
            return []

        currency = statement.curdef
        bal_date = datetime.date(
            bal_datetime.year,
            bal_datetime.month,
            bal_datetime.day
        )

        unique_key = str(bal_date)
        match_key = 'source-report-date'
        existing_by_id = self.find_existing(existing_entries, match_key, _type=data.Balance)

        if unique_key in existing_by_id:
            # We don't do duplicate balance assertions
            return []

        return [data.Note(
            account=self.accounts['root'],
            # amount=data.Amount(amount, currency),
            comment=f"balance {amount} {currency}",
            date=bal_date,
            meta={'lineno': 0, 'filename': '', match_key: unique_key},
            # tolerance=0.5,  # Need to verify these
            # diff_amount=None, # Set by system
        )]

    def extract(self, file, existing_entries=None):
        """
        here we do the work of:
        1) Find existing transactions based on our meta-tag
        2) Generate a tx for all missing transactions

        :param file:
        :param existing_entries:
        :return:


        tx.dtposted - datetime
        tx.trnamt - Decimal
        tx.fitid - String/unique
        tx.name - Name/Description


        flag: A single-character string or None. This user-specified string
          represents some custom/user-defined state of the transaction. You can use
          this for various purposes. Otherwise common, pre-defined flags are defined
          under beancount.core.flags, to flags transactions that are automatically
          generated.
        payee: A free-form string that identifies the payee, or None, if absent.
        narration: A free-form string that provides a description for the transaction.
          All transactions have at least a narration string, this is never None.
        tags: A set of tag strings (without the '#'), or EMPTY_SET.
        links: A set of link strings (without the '^'), or EMPTY_SET.
        postings: A list of Posting instances, the legs of this transaction. See the
          doc under Posting above.


        """

        statement = self._parse_statement(file)
        card_account = self.accounts['root']

        match_key = 'match-key'

        # Exiting Entries
        entries_by_id = self.find_existing(existing_entries, match_key)

        result = []
        for tx in statement.transactions:
            assert isinstance(tx, STMTTRN)
            if tx.fitid in entries_by_id:
                continue

            meta = {
                'lineno': 0,
                'filename': '',
                match_key: tx.fitid,
                'ofx-type': tx.trntype
            }

            target_account = self.resolve_account(tx, entries_by_id, existing_entries)

            result.append(
                data.Transaction(
                    meta,
                    datetime.date(tx.dtposted.year, tx.dtposted.month, tx.dtposted.day),
                    '!',
                    None, # payee--might need help
                    tx.name, # narration
                    data.EMPTY_SET, # tags
                    data.EMPTY_SET, # {link}
                    [
                        data.Posting(
                            account=card_account,
                            units=amount.Amount(tx.trnamt, statement.curdef),
                            cost=None,
                            price=None,
                            flag='*',
                            meta={}
                        ),
                        data.Posting(
                            account=target_account,
                            units=amount.Amount(-tx.trnamt, statement.curdef),
                            cost=None,
                            price=None,
                            flag='!',
                            meta={}
                        )
                    ]
                )
            )

        balances = self.extract_balance(statement, existing_entries)

        return result + balances
