"""
# Google Sheets Tools

It seems everyone needs their own Google Sheets Tools.  These are mine.

We use the gspread library and not the direct google API's.

"""
# stdlib imports
import os
import pathlib

# for Google
from oauth2client.service_account import ServiceAccountCredentials
import gspread


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

