"""
The YAML importer will:

* Look for A YAML file in the Documents tree
* Generate Transaction Entries

This is part of my Sheets->Bean workflow such that I update
they YAML files asynchronously and let this importer manage
the actual file.  This reduces some of the uncertainenty (and
lag) with using Google as a source of information.

"""
# stdlib imports
import logging
import decimal
import re
import pprint
import typing
import datetime
import dateparser
import pathlib
from beancount.ingest import importer, cache

# 3rdparty imports
import slugify
import yaml

# Beancount imports
from beancount.core import data
from coolbeans.utils import safe_plugin, get_setting
from coolbeans.tools.sheets import google_connect, safe_open_sheet
from coolbeans.plugins.accountsync import apply_coolbean_settings


STRIP_SYMOLS = '₱$'
DEFAULT_CURRENCY = "USD"


logger = logging.getLogger(__name__)


ALIASES = {
    'narration': ['description', 'notes', 'details', 'memo']
}


class Importer(importer.ImporterProtocol):
    """This is the importer.  We operate on a single file"""
    def name(self):
        return "yaml.Importer"

    def identify(self, file: cache._FileMemo):
        # TODO use FileMemo correctly
        try:
            name = file.name
            self._read_file(name)
        except Exception as exc:
            return False
        return True

    def file_account(self, file: cache._FileMemo):
        content = self._read_file(file.name)
        return content['account']

    def file_date(self, file: cache._FileMemo):
        content = self._read_file(file.name)
        return content['until_date']

    def file_name(self, file):
        name = file.name
        content = self._read_file(name)
        from_date = content['from_date']
        until_date = content['until_date']
        return f"s{until_date.strftime('%Y-%m-%d')}.{content['slug']}.sheets.yaml"

    def _read_file(self, name) -> dict:
        with pathlib.Path(name).open("r") as stream:
            content = yaml.full_load(stream)
            assert 'until_date' in content
        return content

    def extract(self, file: cache._FileMemo, existing_entries=None) -> data.Entries:
        """
        """

        entries = []
        errors = []
        content = self._read_file(file.name)
        records = content.pop('records')
        currencies = content['currencies']
        account = content['account']

        if currencies:
            default_currency = currencies[0]
        else:
            default_currency = DEFAULT_CURRENCY

        row = 0
        for record in records:
            row += 1
            record = clean_record(record)
            if 'date' not in record or not record['date']:
                continue
            if 'amount' not in record or not record['amount']:
                continue

            narration = record.pop('narration', None)

            payee = record.pop('payee', None)

            tagstr = record.pop('tags', '')
            tags = set(re.split(r'\W+', tagstr)) if tagstr else set()

            # Date handling through dateparser
            date = dateparser.parse(record.pop('date'))
            if date:
                date = datetime.date(year=date.year, month=date.month, day=date.day)

            # Links
            linkstr = record.pop('links', '')
            links = set(re.split(r'\W+', linkstr)) if linkstr else set()

            meta = {
                'filename': '',
                'lineno': 0,
                'document-sheet-row': f"{content['document']}/{content['tab']}/{row+1}"
            }

            # Need more protections
            amount = decimal.Decimal(record.pop('amount'))
            currency = record.pop('currency', default_currency)
            entry_account = record.pop('account')

            for k, v in record.items():
                if v:
                    meta[k] = v

            try:
                if not entry_account:
                    errors.append(f"Skipping Record with Blank Account: {meta['document-sheet-row']}")
                    logger.warning(f"Skipping Record with Blank Account: {meta['document-sheet-row']}")
                    continue

                entry = data.Transaction(
                    date=date,
                    narration=narration,
                    payee=payee,
                    tags=tags,
                    meta=meta,
                    links=links,
                    flag='*',
                    postings=[
                        data.Posting(
                            account=account,
                            units=data.Amount(amount, currency),
                            cost=None,
                            price=None,
                            flag='*',
                            meta={}
                        ),
                        data.Posting(
                            account=entry_account,
                            units=data.Amount(-amount, currency),
                            cost=None,
                            price=None,
                            flag='*',
                            meta={}
                        )
                    ]
                )
                entries.append(entry)
            except Exception as exc:
                logger.error(f"Error while parsing {record}", exc_info=exc)
                errors.append(str(exc))

        return entries


def clean_record(record: typing.Dict[str, str]):
    """This is a bit of a hack.  But using get_all_records doesn't leave many
    options"""

    new_record = {}
    for k, v in record.items():
        k = slugify.slugify(k.lower().strip())
        v = str(v)

        # Combine multiple narration columns if needed:
        for field, names in ALIASES.items():
            new_record.setdefault(field, '')
            if k in names:
                # Add the value to Narration:
                new_record[field] += ('. ' if new_record[field] else '') + v
                k = None  # Clear this Key
                break

        # Really Ugly hack around embeded currency symbols.  Needs Cleanup
        if k == 'amount':
            v = v.replace(',', '')
            for s in STRIP_SYMOLS:
                v = v.replace(s, '')
            if v and not v[0].isdecimal() and not v[0]=='-':
                v = v[1:]
                # Pull currency?

            # Decimal is fussy
            try:
                v = decimal.Decimal(v)
            except decimal.InvalidOperation:
                v = 0

        if k:
            new_record[k] = v

    return new_record


# Allows this importer to be used without a config file
CONFIG = [Importer()]
