"""
# Sheets Account

Read a Google Sheet as if it were are realtime source of transactions
for a GL account.  Columns are mapped to attributes.  The
assumption is that the sheet maps to a single account, and the
rows are the credit/debits to that account.

Can be used as a plugin, which will write new entries (for reference)
to a file, but also maintain a "live" view of the transactions.

"""


# stdlib imports
import logging
import decimal
import pprint
import typing
import datetime
import dateparser
import pathlib
import slugify

# Beancount imports
from beancount.core import data
from coolbeans.utils import safe_plugin, get_setting
from coolbeans.tools.sheets import google_connect, safe_open_sheet
from coolbeans.plugins.accountsync import apply_coolbean_settings

import gspread

DEFAULT_CURRENCY = "USD"
logger = logging.getLogger(__name__)
__plugins__ = ['apply_coolbean_settings', 'remote_entries_plugin']


def remote_entries(entries, options_map):
    """

    @param entries:
    @param options_map:
    @return:
    """
    errors = []
    settings = options_map['coolbeans']
    secrets_file = get_setting('google-apis', settings)
    connection = google_connect(secrets_file)

    new_entries_path = None
    new_entries_file = get_setting('new-entries-bean', settings)
    if new_entries_file:
        new_entries_path = pathlib.Path(new_entries_file)

    # Capture the configuration off the Open
    remote_accounts = {}
    for entry in entries:
        if not isinstance(entry, data.Open):
            continue
        document_name = entry.meta.get('document_name', None)
        default_currency = entry.currencies[0] if entry.currencies else DEFAULT_CURRENCY

        if document_name:
            options = dict(
                document_name=document_name,
                document_tab=entry.meta.get('document_tab', None),
                reverse_amount=entry.meta.get('reverse', False),
                default_currency=default_currency,
                entry=entry
            )
            remote_accounts[entry.account] = options

    new_entries = []
    for account, options in remote_accounts.items():
        try:
            new_entries += load_remote_account(
                connection=connection,
                errors=errors,
                account=account,
                options=options
            )
        except Exception as exc:
            logger.error(f"while processing {account}", exc_info=exc)

    if new_entries and new_entries_path:
        from beancount.parser import printer
        with new_entries_path.open("w") as stream:
            printer.print_entries(new_entries, file=stream)
            logger.info(f"Wrote {len(new_entries)} new account(s) to {new_entries_path}.")

    return entries+new_entries, errors

remote_entries_plugin = safe_plugin(remote_entries)

ALIASES = {
    'narration': ['description', 'notes', 'details', 'memo'],
    'account': ['category']
}

def clean_record(record: typing.Dict[str, str]):
    new_record = {}
    for k, v in record.items():
        k = slugify.slugify(k.lower().strip())
        v = str(v)

        for field, names in ALIASES.items():
            if k in names:
                k = field
                break

        if k == 'amount':
            v = v.replace(',', '')
            if v and not v[0].isdecimal() and not v[0]=='-':
                v = v[1:]
                # Pull currency?

            try:
                v = decimal.Decimal(v)
            except decimal.InvalidOperation:
                logger.error(f"Unable to convert {v} to Decimal in record {record}")
                v = 0

        if k:
            new_record[k] = v

    return new_record

def load_remote_account(
        connection: gspread.Client,
        errors: list,
        account: str,
        options: typing.Dict[str, str]
    ):
    """Try to Load Entries from URL into Account.

    options include:
        - document_name -- the Actual Google Doc name
        - document_tab -- the Tab name on the Doc
        - default_currency - the entry currency if None is provided
        - reverse_amount - if true, assume positive entries are credits

    TODO: Multi-currency
    TODO: Lot support

    """
    entries = []

    document_name = options['document_name']
    document_tab = options.get('document_tab', 0) or 0
    default_currency = options['default_currency']
    reverse_amount = options.get('reverse_amount', False)

    if not document_name:
        return

    m = -1 if reverse_amount else 1
    logger.info(f"Attempting to download entries for {account} from {document_name}.{document_tab}")
    workbook = connection.open(document_name)
    try:
        # Try the index case
        sheet = workbook.get_worksheet(int(document_tab))
    except:
        sheet = workbook.worksheet(document_tab)

    records = sheet.get_all_records()
    import re
    for record in records:

        # logger.info(f"Looking at {record}")
        if 'date' not in record or not record['date']:
            continue
        if 'amount' not in record or not record['amount']:
            continue
        record = clean_record(record)

        narration = record.pop('narration', None)

        payee = record.pop('payee', None)

        tagstr = record.pop('tags', '')
        tags = set(re.split(r'\W+', tagstr)) if tagstr else set()

        date = dateparser.parse(record.pop('date'))
        if date:
            date = datetime.date(year=date.year, month=date.month, day=date.day)

        linkstr = record.pop('links', '')
        links = set(re.split(r'\W+', linkstr)) if linkstr else set()

        meta = {
            'filename': '',
            'lineno': 0
        }
        amount = decimal.Decimal(record.pop('amount')) * m
        currency = record.pop('currency', default_currency)
        entry_account = record.pop('account')
        for k, v in record.items():
            if v:
                meta[k] = v

        try:
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
