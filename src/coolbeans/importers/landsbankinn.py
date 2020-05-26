"""
An importer for the Personal Format Excel Files downloaded
from Landsbankin in Iceland.

Sample Row/Headers are:
Dagsetning	Vaxtadagur	Tilvísun	Skýring	Texti	Upphæð	Staða	Númer útibús	Stutt tilvísun
5/15/20 0:00	5/15/20 0:00	GV165636	Fj.skatt gengishagnað	Guðmundur Rúnar Pétursson	-199.2	7,258.2	0152

Current version of these rhese files are in Excel, but usually pretty clean.
"""
import pathlib
import datetime
import decimal
import typing
import dataclasses
import logging
import pprint

import openpyxl

from beancount.ingest import importer, cache
from coolbeans.tools.loader import load_file, Meta
from beancount.core import data, amount, account



logger = logging.getLogger(__name__)


HEADER_MAP = dict(
    date='Dagsetning',
#   posting_date='Vaxtadagur',
    refference='Tilvísun',
    tx_id='Stutt tilvísun',
    payee='Texti',
    narration='Skýring',
    amount='Upphæð',
    balance='Staða',
#   bank_number='Númer útibús',
)
MAP_BY_VALUE = dict((v.lower(), k) for (k, v) in HEADER_MAP.items())

INFO_MAP = dict(
    account_number="B2",
    balance="B3",
    currency="B4",
    owner="B5",
    social="B6",
    account_name="B7"
)


@dataclasses.dataclass
class PossibleRow:
    date: datetime.date
    payee: str
    narration: str
    amount: decimal.Decimal
    meta: dict = dataclasses.field(default_factory=dict)
    currency: str = "ISK"

    @classmethod
    def from_row(cls, row: list, map: dict) -> 'PossibleRow':
        parameters = dict(meta=Meta())
        for field, index in map.items():
            cell = row[index]
            value = cell.value
            if field == 'date':
                value = datetime.date(
                    year=value.year,
                    month=value.month,
                    day=value.day
                )

            if field == 'amount':
                value = decimal.Decimal(value).quantize(decimal.Decimal("0.01"))

            if field in cls.__dataclass_fields__:
                parameters[field] = value
            elif value:
                parameters['meta'][field] = str(value)
        return cls(**parameters)


def map_header(row:list, value_map: dict):
    # Reverse the Map to be by Foreign Character
    # print(f"{row} | {value_map}")
    row = [cell.value.lower().strip() for cell in row]
    return dict(
        (v, row.index(k)) for (k, v) in value_map.items()
    )


class Importer(importer.ImporterProtocol):

    accounts = None
    possible_accounts:dict = None
    header:dict = None
    bean_file:str = ""

    def __init__(
            self,
            accounts: typing.Dict[str, str],
            bean_file: str=None,
    ):
        """We need the account.
        next is to match on the meta tag and check the second TAB of the Excel sheet for Account number

        """
        self.accounts = accounts
        self.bean_file = bean_file
        self.possible_accounts = {}
        self.header = {}

        if bean_file:
            self._auto_configure(bean_file)

    def _auto_configure(self, bean_file):
        self.possible_accounts = {}
        entries, errors, context = load_file(bean_file)
        for entry in entries:
            if not isinstance(entry, data.Open):
                continue
            acct = entry.meta.get('account_number', '').replace('-', '')
            self.possible_accounts[acct] = entry.account

    def get_root(self):
        root = self.accounts.get('root', None)
        if root:
            return root

        if self.possible_accounts and self.header:
            assert 'account_number' in self.header, f"XXX {self.header}"
            statement_account = str(self.header.get('account_number'))
            acct = self.possible_accounts.get(
                statement_account, None)
            if acct:
                logger.info(f"Auto-Resolved account {statement_account}  to {acct}")
                return acct
            else:
                logger.info(f"{pprint.pformat(self.possible_accounts)}")
                logger.info(f"statement_account = {statement_account}")


    def name(self):
        return "landsbankinn.Importer"

    def identify(self, file: cache._FileMemo):
        try:
            name = file.name
            self._read_file(name)
        except Exception as exc:
#           logger.info("", exc_info=exc)
            return False
        return True

    def file_account(self, file):
        name = file.name
        return f"{self.get_root()}"

    def file_date(self, file: cache._FileMemo):
        name = file.name
        entries, context = self._read_file(name)
        if entries:
            return entries[0].date

    def file_name(self, file):
        name = file.name
        entries, context = self._read_file(name)

        if entries:
            first_entry = entries[-1].date

        return f"s{first_entry.strftime('%Y-%m-%d')}.{context['account_number']}.statement.xlsx"

    def extract(self, file: cache._FileMemo, existing_entries=None) -> data.Entries:
        """Given a File, let's extract the records"""

        name = file.name
        possible, context = self._read_file(name)
        root_account = self.get_root()
        if not root_account:
            logger.error(f"Unable to find an account {context}")
            return []

        new_entries = []

        for entry in possible:
            target_account = self.accounts['default-transfer']

            new_entries.append(data.Transaction(
                date=entry.date,
                narration=entry.narration,
                payee=entry.payee,
                meta=entry.meta,
                tags=set(),
                links=set(),
                flag="!",
                postings=[
                    data.Posting(
                        account=root_account,
                        units=data.Amount(entry.amount, entry.currency),
                        flag="*",
                        cost=None,
                        price=None,
                        meta=None
                    ),
                    data.Posting(
                        account=target_account,
                        units=data.Amount(-entry.amount, entry.currency),
                        flag="!",
                        cost=None,
                        price=None,
                        meta=None
                    )
                ]
            ))
        return new_entries


    def pull_info(self, wb) -> dict:
        sheet = wb['Reikningur']
        result = {}
        for field, loc in INFO_MAP.items():
            result[field] = sheet[loc].value
        return result

    def _read_file(self, file: str):
        """
        Create an Excel file reader

        @param file:
        @return:
        """
        wb = openpyxl.open(
            file,
            read_only=True,
        )
        sheet = wb.active

        header = None
        col_map = {}
        data_rows = []
        for row in sheet.rows:
            if not col_map:
                col_map = map_header(row, MAP_BY_VALUE)
            else:
                record = PossibleRow.from_row(row, col_map)
                if record.amount:
                    data_rows.append(record)

        context = self.pull_info(wb)
        context['header'] = col_map
        self.header = context
        return data_rows, context

if __name__ == "__main__":
    import sys
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    document = pathlib.Path("statements/landsbankinn.xlsx")
    assert document.exists()
    importer = Importer(
        accounts={
            'root': "Assets:Banks:Landsbankinn",
            'default-transfer': "Assets:Transfer:FIXME",
            'default-expense': "Expenses:FIXME"
        }
    )

    from beancount.loader import printer
    for entry in importer.extract(document):
        printer.print_entry(entry)
