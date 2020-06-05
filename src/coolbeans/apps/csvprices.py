"""cool-csv-prices is a simple util that reads a CSV in the format
SYMBOL,YYYY-MM-DD,PRICE,.*

It ignores any further columns.  These are compared against an existing bean file so duplicates are removed.
"""

from coolbeans.utils import logging_config
from collections import defaultdict
import argparse
import logging
import sys
import os
from pathlib import Path
import pdb
import csv
import datetime
import typing
import dateparser
import decimal


from beancount.core import data
from beancount import loader
from beancount.utils import misc_utils

from coolbeans.apps import BEAN_FILE_ENV


logger = logging.getLogger(__name__)


def read_price_stream(stream: typing.Iterable, price_db: typing.Dict[str, dict], quote_currency: str) -> data.Entries:
    """Reads an iterable of tuples and compares against existing price_db

    Returns:
        list of beancount Entries
    """

    entries = []
    for row in stream:
        currency, _date, _amount = row[0:3]
        if currency not in price_db:
            continue
        dp: datetime.datetime = dateparser.parse(_date)
        assert dp, f"Unable to parse date {_date}"
        date = datetime.date(dp.year, dp.month, dp.day)
        amount = data.Amount(decimal.Decimal(_amount), quote_currency)

        history = price_db[currency]
        if date in history:
            continue

        entry = data.Price(
            date=date,
            currency=currency,
            amount=amount,
            meta=data.new_metadata('', 0)
        )

        entries.append(entry)

    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    default_file = os.environ.get(BEAN_FILE_ENV, None)
    default_home = os.environ.get('BEAN_HOME', None)

    parser.add_argument(
        "source",
        type=argparse.FileType("r"),
        default="-"
    )
    parser.add_argument(
        "-o", "--output", "--target",
        type=str,
        dest="target",
        default="-",
    )
    parser.add_argument(
        "--quote-currency",
        type=str,
        dest="currency",
        default=None,
        help="The currency in which this commodity is priced.  Defaults to USD."
    )
    parser.add_argument(
        '-e', '--bean',
        metavar=BEAN_FILE_ENV,
        default=default_file,
        required=False,
        type=str,
        dest='bean_file',
        help=f"Beancount file to read and verify. {'Default is '+ default_file if default_file else ''}"
    )
    parser.add_argument(
        '--pdb',
        action='store_true',
        help='Drop into a debugger on error'
    )
    parser.add_argument(
        '--logging-conf',
        type=str,
        default=default_home + '/logging.yaml',
        help='logging.yaml file to use.  Default is ./logging.yaml'
    )
    args = parser.parse_args()

    logging_conf: Path = Path(args.logging_conf)
    if logging_conf.exists():
        logging_config(
            config_file=logging_conf,
            level=logging.DEBUG
        )

    # Output File Handling
    out_file = args.target
    if out_file == "-":
        stream = sys.stdout
    else:
        out_path = Path(out_file)
        if out_path.exists():
            stream = out_path.open("a")
        else:
            stream = out_path.open("w")

    with misc_utils.log_time('beancount.loader (total)', logging.info):
        # Load up the file, print errors, checking and validation are invoked
        # automatically.
        try:
            entries, errors, context = loader.load_file(
                args.bean_file,
                log_timings=logging.info,
                log_errors=sys.stderr
            )
        except Exception as exc:
            if args.pdb:
                pdb.post_mortem(exc.__traceback__)
            else:
                raise

    quote_currency: str = args.currency
    if not quote_currency:
        oc = context.get('operating_currency', ['USD'])
        if oc:
            quote_currency = oc[0]
    logger.info(f"Using quote currency: {quote_currency}")

    # Build the Price Database:
    price_db: typing.Dict[str, dict] = defaultdict(dict)

    for entry in entries:
        if not isinstance(entry, data.Price):
            continue
        price_db[entry.currency][entry.date] = entry.amount

    # We could handle different source formats (JSON, YAML)
    reader = csv.reader(args.source)

    price_entries = read_price_stream(reader, price_db, quote_currency)

    loader.printer.print_entries(
        price_entries,
        file=stream
    )

if __name__ == "__main__":
    main()
