"""DK Export/Import File.

This is the importer for a Excel output from https://dk.is/

"""
__author__ = "Runar Petursson <runar@runar.net>"

# stdlib imports
import datetime
import logging
import typing
import csv
import decimal
import collections

# 3rdparty imports
from beancount.ingest import importer
from beancount.ingest.cache import _FileMemo as FileMemo
from beancount.core import data
from slugify import slugify

# Log all of the things
logger = logging.getLogger(__name__)


CURRENCY = "ISK"  # The data seems to not have Other currencies


DK_COLUMNS = {
    "Bókhaldslykill": 'account_number',
    "Heiti lykils": 'account_name',
    "Dagsetning": 'date',  # date
    "Undirlykill": 'sub_key',
    "Tilvísun": 'tag',  # done
    "Fylgiskjal": 'glid',  # done
    "Reikningur": 'invoice',  # done
    "Lýsing": 'narration',  # done
    "Upphæð": 'amount',  # done
    "Staða": 'balance',
    "Tegund færslu": 'tx_type',
    "Erl.jöfnuður": 'foreign_balance'
}

class Format:
    def __init__(self, name_map):
        self.by_col = {}
        index = 0
        values = []
        for value, name in name_map.items():
            self.__dict__[name] = value
            self.by_col[index] = value
            values.append(name)

        self.NamedTuple = collections.namedtuple(
            "row",
            values
        )

    def __getitem__(self, item):
        if item in self.by_col:
            return self.by_col[item]
        return getattr(self, item)

    def named_tuple_from_row(self, row: typing.Iterable) -> collections.namedtuple:
        # logging.warning(f"{len(row)}: {row}")
        return self.NamedTuple(*row)



class Entry:
    """Some Helpers to Parse/Format the entries coming from d2.

    Example Row:

3200,Tryggingargjald,30/6/2016,,,L0019,,Tryggingagjald,"4,927 ","21,548,413-",,"21,548,413.00-"

    """
    def __init__(self, format: Format, row, accounts: dict, currency=CURRENCY):
        self.format = format
        self.row = row
        self.accounts = accounts

        self.currency = currency

    @property
    def account(self):
        row = self.row
        try_list = [row.account_number, row.account_name, 'default']
        for lookup in try_list:
            if lookup in self.accounts:
                return self.accounts[lookup]

        number = row.account_number[0]
        name = slugify(row.account_name)
        # name = self.clean_name(row.account_name)

        reverse = {
            "Assets": "7",
            "Expenses": "23456",
            "Equity": "",
            "Liabilities": "89",
            "Income": "1"
        }
        for account, numbers in reverse.items():
            if number in numbers:
                return f"{account}:K{row.account_number}:{name.title()}"

        return "Expenses:FIXME"

    def clean_name(self, name: str):
        name = name.strip()
        name = name.replace(' ', '-')
        name = name.replace('.', '')
        name = name.replace(',', '')
        name = name.replace('/', '-')
        name = name.replace('%', '')
        while name.startswith('-'):
            name = name[-1:]
        while name.endswith('-'):
            name = name[:-1]
        return name.title()

    @property
    def date(self):
        # print(f"{type(self.row)} - {self.row}")
        # print(f"{self.row.date.split('/')}")
        d, m, y = map(int, self.row.date.split('/'))
        return datetime.date(year=y, month=m, day=d)

    @property
    def gl_id(self):
        return f"{self.date.year}:{self.row.glid}"

    def convert_number(self, number):
        """We get numbers as strings with , and . all reversed"""
        number = number.replace(',', '')
        sign = 1
        if number.endswith("-"):
            sign = -1
            number = number[:-1]
        try:
            return decimal.Decimal(number) * sign
        except:
            logger.exception(f"Unable to convert {number} to a Decimal!")
            raise

    @property
    def amount(self):
        return self.convert_number(self.row.amount)

    @property
    def tags(self):
        tag = slugify(self.row.tag).strip()
        if tag:
            return {tag}
        else:
            return set()

    @property
    def links(self):
        if self.row.invoice:
            return {f"INV-{slugify(self.row.invoice)}"}
        else:
            return set()

    @property
    def narration(self):
        return self.row.narration

    @property
    def entry_type(self):
        if self.row.tx_type.strip().lower() == 'opnun':
            return "Balance"
        else:
            return "Transaction"

    @property
    def meta(self):
        meta = {
            'tx-type': self.row.tx_type,
            'narration': self.row.narration,
            'lineno': 0,
            'filename': ""
        }
        if self.row.tx_type:
            meta['tx-type'] = self.row.tx_type.lower()
        if self.row.account_name:
            meta['description'] = self.row.account_name
        return meta

    @property
    def payee(self):
        """Perhaps provide a list of common Payye and parse?"""
        return ""


class Importer(importer.ImporterProtocol):
    """

    From the File we have:
    Bókhaldslykill, Heiti lykils, Dagsetning, Undirlykill, Tilvísun, Fylgiskjal, Reikningur, Lýsing, Upphæð, Staða, Tegund færslu, Erl.jöfnuður
    """

    gl_records: typing.Dict[str, typing.List[Entry]] = {}
    entries: typing.List[data.Directive] = []
    new_accounts:typing.Set[str] = set()

    def __init__(self, accounts: typing.Dict[str, str]):
        """Accepts a dict of account number in DK to our Account Name"""
        self.accounts  = accounts

        self.gl_records = {}
        self.entries = []
        self.new_accounts = set(["Equity:OpeningBalances"])

    def extract(self, file: FileMemo, existing_entries=None):
        self.read_file(file.name)
        return self.entries


    def identify(self, file: FileMemo) -> bool:
        try:
            self.read_file(file.name)
        except Exception:
            logger.exception(f"Reading {file}")
            return False
        return True

    def file_account(self, file):
        # This is all records, so doesn't Quite Make Sense
        statement = self.read_file(file.name)
        return f"Assets"

    def file_date(self, file):
        statement = self.read_file(file.name)
        last_entry = None
        for entry in self.entries:
            if entry.date > last_entry:
                last_entry = entry.date
        return last_entry

    def file_name(self, file):
        return "d2.full.csv"

    def read_file(self, file_name: str):
        if self.gl_records:
            # File has already been read
            return None

        format = Format(DK_COLUMNS)

        with open(file_name, "r") as stream:
            reader = csv.reader(stream, dialect='excel')
            skip = 1
            for row in reader:
                if skip:
                    skip -= 1
                    continue
                if not row[0].strip():
                    continue
                try:
                    row = format.named_tuple_from_row(row)
                except Exception:
                    logger.exception(f"{row}")
                    raise

                self.add_record(
                    Entry(format, row, accounts=self.accounts)
                )
        # Now Generate the self.entries
        self.generate_transactions()

    def add_record(self, record: Entry):
        """Add a single Record.  """
        self.gl_records.setdefault(
            record.gl_id, []).append(record)

    def generate_transactions(self):
        """Iterate through the GL Records, generate entries"""
        for entries in self.gl_records.values():
            self.entries.extend(
                self.entry_from_gl(entries)
            )

        for account in sorted(self.new_accounts):
            self.entries.append(
                data.Open(
                    date=datetime.date(2010, 1, 1),
                    account=account,
                    meta={
                        'filename': '',
                        'lineno': 0
                    },
                    currencies=None,
                    booking=None
                )
            )


    def entry_from_gl(self, entries: typing.List[Entry]) -> typing.Iterable:
        """Given a single GL_ID and as a list of Entrys
        """
        first = entries[0]

        postings = []
        all_tags = set()
        all_meta = {
            'lineno': 0,
            'filename': "",
            'gl-id': first.gl_id
        }
        all_links = set()

        for entry in entries:
            self.new_accounts.add(entry.account)

            if first.entry_type == "Balance":
                if entry.amount and entry.date.year == 2016:
                    yield data.Pad(
                        date=entry.date-datetime.timedelta(days=1),
                        account=entry.account,
                        source_account="Equity:OpeningBalances",
                        meta={
                            'lineno': 0,
                            'filename': '',
                            'note': entry.narration,
                            'gl-id': entry.gl_id
                        }
                    )
                yield data.Balance(
                    date=entry.date,
                    amount=data.Amount(entry.amount, entry.currency),
                    account=entry.account,
                    tolerance=None,
                    diff_amount=None,
                    meta={
                        'lineno': 0,
                        'filename': '',
                        'note': entry.narration,
                        'gl-id': entry.gl_id
                    }
                )
            else:
                posting = data.Posting(
                    entry.account,
                    data.Amount(entry.amount, entry.currency),
                    None,
                    None,
                    flag='*',
                    meta=entry.meta
                )
                all_tags.update(entry.tags)
                all_links.update(entry.links)

                postings.append(posting)
                all_meta.update(posting.meta or {})

        if postings:
            yield data.Transaction(
                meta=all_meta,
                date=entry.date,
                flag='*',
                payee=entry.payee,
                narration=entry.narration,
                tags=all_tags,
                links=all_links,
                postings=postings
            )
