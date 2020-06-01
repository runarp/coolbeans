"""
# Google Sheets Tools

It seems everyone needs their own Google Sheets Tools.  These are mine.

We use the gspread library and not the direct google API's.

"""
# stdlib imports
import os
import pathlib
import typing
import logging
import yaml
import datetime

# for Google
from oauth2client.service_account import ServiceAccountCredentials
import gspread

logger = logging.getLogger(__name__)


GOOGLE_SECRETS_ENV = 'GOOGLE_APIS'
GOOGLE_SECRETS_FILE = '~/.google-apis.json'
API_SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]


def google_connect(secrets_file=None) -> gspread.Client:
    """Attempt to make a connection with Google

    This doesn't have a fallback interactive mode.

    """
    if secrets_file is None:
        secrets_file = os.environ.get(
            GOOGLE_SECRETS_ENV,
            pathlib.Path(GOOGLE_SECRETS_FILE).expanduser()
        )
    else:
        secrets_file = pathlib.Path(secrets_file).expanduser()

    assert secrets_file.exists(), f"Unable to find {secrets_file}."

    creds = ServiceAccountCredentials.from_json_keyfile_name(secrets_file, API_SCOPE)

    return gspread.authorize(creds)


def safe_open_sheet(book: gspread.Spreadsheet, sheet_name: str, rows=1000):
    """Open a Worksheet, if it doesn't exist, just create it."""
    try:
        return book.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        return book.add_worksheet(sheet_name, rows=rows, cols=20)

def _scrub(record:dict):
    return dict([
        (k.lower().strip(), v) for (k, v) in record.items()
    ])

def fetch_sheet(
        connection: gspread.Client,
        document: str,
        tab: str
) -> list:
    """Try to Load Entries from URL into Account.

    options include:
        - document_name -- the Actual Google Doc name
        - document_tab -- the Tab name on the Doc
        - default_currency - the entry currency if None is provided
        - reverse_amount - if true, assume positive entries are credits
    """

    document_name = document
    document_tab = tab
    reverse_amount = False

    if not document_name:
        False

    workbook = connection.open(document_name)

    sheet = None
    try:
        document_tab = int(document_tab)
        sheet = workbook.get_worksheet(document_tab)
    except ValueError:
        pass

    if sheet is None:
        sheet = workbook.worksheet(document_tab)

    records = sheet.get_all_records()
    clean_records = []
    for record in records:
        clean = _scrub(record)
        if ('account' not in clean or not clean['account']):
            continue
        if ('amount' not in clean or not clean['amount']):
            continue
        clean_records.append(clean)
    return clean_records

def save_sheet(
        connection: gspread.Client,
        document: str,
        tab: str,
        file_name=None
):
    records = fetch_sheet(connection, document, tab)
    data = {
        'saved': datetime.datetime.today(),
        'document': document,
        'tab': tab,
#       'currencies': entry.currencies
    }
    # Now add the records
    data['records'] = records
    with pathlib.Path(file_name).open("w") as stream:
        logging.info(f"Writing {len(records)} to {file_name} from {document}/{tab}")
        yaml.dump(data, stream=stream)
