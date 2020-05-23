# stdlib imports
import logging
import pprint
import typing
import datetime
import pathlib

# Beancount imports
from beancount.core import data
from coolbeans.utils import safe_plugin, get_setting
from coolbeans.tools.sheets import google_connect, safe_open_sheet

import gspread


logger = logging.getLogger(__name__)
__plugins__ = ['apply_coolbean_settings', 'remote_accounts_plugin']


def apply_coolbean_settings(entries, options_map):
    if 'coolbeans' in options_map:
        return entries, []

    settings = dict()
    for entry in entries:
        if isinstance(entry, data.Custom):
            if entry.type == "coolbeans":
                param, value = entry.values
                settings.setdefault(param.value, []).append(value.value)

    options_map['coolbeans'] = settings

    return entries, []


def remote_accounts(entries, options_map):
    """* Remote Accounts

    Fetch a list of accounts and possible meta-data from a google sheet.

    Merge these with the current file's 'open' directive.

    Any "new" entries are dynamically injected and optionally burned to a local
    file.

    Accepts the following Bean based configuration:

2018-06-14 custom "coolbeans" "accounts-workbook-url"  "URL to Google Sheet"
2018-06-14 custom "coolbeans" "accounts-sheet-name"  "NameOfTab"
2018-06-14 custom "coolbeans" "new-accounts-bean"  "reports/new-accounts.bean"
2018-06-14 custom "coolbeans" "google-apis"  "~/.google-apis.json"

    secrets_filename = os.environ.get('GOOGLE_APIS',
                                      path.expanduser('~/.google-apis.json'))
    """

    settings = options_map['coolbeans']
    secrets_file = get_setting('google-apis', settings)
    connection = google_connect(secrets_file)

    new_accounts_path = None
    new_accounts_file = get_setting('new-accounts-bean', settings)
    if new_accounts_file:
        new_accounts_path = pathlib.Path(new_accounts_file)

    workbook_url = get_setting('accounts-workbook-url', settings)
    sheet_name = get_setting('accounts-sheet-name', settings)

    if not workbook_url or not sheet_name:
        logger.error("Unable to configure Accounts Sync")
        return entries, []

    workbook = None

    if workbook_url:
        try:
            workbook = connection.open(workbook_url)
        except gspread.exceptions.SpreadsheetNotFound:
            logger.error(f"Unable to find Google Sheets '{workbook}'")
            available: typing.List[gspread.Worksheet] = connection.openall()
            logger.error(f"Possible {(a.title for a in available)}")
            raise ValueError(f"Invalid Google Sheets URL {workbook}")

    #  else:
    #      # Use the first available sheet for these credentials:
    #      all_sheets = connection.openall()
    #      if all_sheets:
    #          sheet = all_sheets[0]
    #          logger.info(f"Connecting to google sheet '{sheet.title}'.")
    #      else:
    #          print("Credentials unable to find any authorized sheets.")
    #          sys.exit(3)

    sheet = safe_open_sheet(workbook, sheet_name)

    possible_accounts = load_accounts_from_sheet(sheet)
    sheet_by_name = dict((a['account'], a) for a in possible_accounts)
    last_row = len(possible_accounts) + 1

    append_to_sheet = []
    open_by_account = {}

    # Some Account Trees Should be Hidden, use a 'hidden': 1 Meta
    hidden_prefixes = set()
    for entry in entries:
        if not isinstance(entry, data.Open):
            continue
        hidden = entry.meta.get('hidden', 0)
        if bool(int(hidden)):
            hidden_prefixes.add(entry.account)

    # Make a List of Local Entries, not on the Sheet
    for entry in entries:
        if not isinstance(entry, data.Open):
            continue
        match = False
        for hidden_name in hidden_prefixes:
            if entry.account.startswith(hidden_name):
                match = True
                break
        open_by_account[entry.account] = entry
        if match:
            continue

        if entry.account not in sheet_by_name:
            # Skip these things
            if entry.account.endswith("Unrealized"):
                continue
            new_account = {
                'account': entry.account,
                'currencies': ','.join(entry.currencies or []),
                'slug': entry.meta.get('slug', ''),
                'account_number': str(entry.meta.get('account_number', '')),
                'institution': entry.meta.get('institution', ''),
                'date': entry.date.strftime("%Y-%m-%d")
            }
            append_to_sheet.append(new_account)

    # Make a List of Entries on the Sheet but Not in our Books
    new_entries = []
    for account, record in sheet_by_name.items():
        if account in open_by_account:
            # This _might_ be a modified entry, in which case we should use
            # Meta Attributes set in the Sheet!
            open_entry: data.Open = open_by_account[account]
            sheet_entry: dict = record
            compare_fields = ('slug', 'account_number', 'institution')
            for field in compare_fields:
                sheet_val = str(sheet_entry[field])
                if sheet_val and sheet_val != open_entry.meta.get(field, None):
                    open_entry.meta[field] = sheet_val
                    if open_entry not in new_entries:
                        new_entries.append(open_entry)
            continue

        # logging.info(f"New Account {account} from sheet: {record}.")
        # noinspection PyBroadException
        try:
            record = dict(record)
            record.pop('account')
            currencies = record.pop('currencies', None)
            if currencies:
                currencies = currencies.split(',')
            datestr = record.pop('date', "2000-01-01") or "2000-01-01"
            y, m, d = datestr.split('-')
            open_date = datetime.date(year=int(y), month=int(m), day=int(d))
            meta = dict((k, str(v)) for (k, v) in record.items() if v)
            meta['lineno'] = 0
            meta['filename'] = ''
            entry = data.Open(
                account=account,
                currencies=currencies,
                date=open_date,
                meta=meta,
                booking=None
            )
            # We add this to the "live" system as well
            entries.append(entry)
            new_entries.append(entry)
        except Exception:
            logger.exception(f"Unable to create new entry for {account}")

    if new_entries:
        from beancount.parser import printer
        with new_accounts_path.open("w") as stream:
            printer.print_entries(new_entries, file=stream)
            logger.info(f"Wrote {len(new_entries)} new account(s) to {new_accounts_path}.")


    # Write all the entries back to the sheet
    append_to_sheet.sort(key=lambda x: x['account'])
    header = sheet.row_values(1)
    rows = []
    for item in append_to_sheet:
        row = [str(item.get(f, '')) for f in header]
        rows.append(row)
    sheet.update([header]+rows)

    return entries, []

remote_accounts_plugin = safe_plugin(remote_accounts)

def load_accounts_from_sheet(sheet: gspread.Worksheet):
    return sheet.get_all_records()
