"""
CLI to Fetch Specific Google Sheets that have been updated

Accepts a Bean-File and writes a Yaml file of the records.
"""
import argparse
import pathlib
import logging
import datetime
import os
import typing
import json
import yaml
import dateparser

from coolbeans.tools.sheets import fetch_sheet, google_connect
from coolbeans.apps import BEAN_FILE_ENV
from coolbeans.plugins.sheetsaccount import coolbean_sheets
from coolbeans.utils import logging_config


logger = logging.getLogger(__name__)


def configure_parser(parser):

    parser.add_argument(
        '-d', '--document',
        type=str,
        help=f"Document name to fetch"
    )
    parser.add_argument(
        '-t', '--tab',
        type=str,
        help=f"tab name to fetch"
    )
    parser.add_argument(
        '--slug',
        type=str,
        help=f"Destination Account Slug",
    )
    parser.add_argument(
        '--account',
        type=str,
        help=f"Account filter rex",
        default=""
    )
    parser.add_argument(
        '-f', '--format',
        type=str,
        choices=('json', 'yaml'),
        help=f"Output format. Default is json.",
        default="json"
    )
    out_default = os.environ.get("BEAN_INCOMING", None) or pathlib.Path('.').absolute()
    parser.add_argument(
        '-o', '--output',
        type=pathlib.Path,
        help=f"Destination Folder ({out_default})",
        default=out_default
    )
    parser.add_argument(
        '-s', '--secrets',
        type=pathlib.Path,
        default="~/.google-apis.json",
        help=f"Google Secrets Path File"
    )
    parser.add_argument(
        '-v', '--debug',
        action='store_true',
        default=False
    )
    parser.add_argument(
        '-n', '--dry',
        action='store_true',
        help="Dry run",
        default=False,
    )

    default_file = os.environ.get(BEAN_FILE_ENV, None)
    parser.add_argument(
        '-e', '--existing',
        metavar=BEAN_FILE_ENV,
        default=default_file,
        type=pathlib.Path,
        dest='bean_file',
        help=f"Beancount file to read the Open slugs. {'Default is '+ default_file if default_file else ''}"
    )


def save_sheet(records: list, file_name: str, **header):
    # Now add the records
    header['records'] = records

    with pathlib.Path(file_name).open("w") as stream:
        yaml.dump(header, stream=stream)


def main():
    parser = argparse.ArgumentParser()
    configure_parser(parser)
    args = parser.parse_args()

    logging_config(level=logging.DEBUG)

    from beancount.loader import load_file
    logger.info(f"Loading {args.bean_file}.")

    entries, errors, context = load_file(
        args.bean_file,
        log_errors=logger.error,
        log_timings=logger.info
    )

    # Update the context with the names/locations of the sheets we want.
    # This will add context['coolbean-accounts']
    coolbean_sheets(entries, context)
    import re, pprint

    connection = google_connect(args.secrets)

    matches = 0
    for slug, conf in context['coolbean-accounts'].items():
        if args.slug and args.slug != slug:
            continue

        if args.account:
            if not re.match(args.account, conf['account'], re.I):
                continue

        logger.info(f"Fetching {conf['account']} at {conf['document']}/{conf['tab']}")
        if args.dry:
            print(f"would fetch {conf['account']} at {conf['document']}/{conf['tab']}")
            continue

        records = fetch_sheet(connection, conf['document'], conf['tab'])

        # Find the 'first' record:
        first_date, last_date = record_range(records)
        last_date = last_date or datetime.date.today()

        first_str = ""
        if first_date:
            first_str = f".s{first_date.strftime('%Y-%m-%d')}"

        # Default file_name
        file_name = '.'.join([
            #  last_date.strftime('%Y-%m-%d') + first_str,
            #  slug,
            conf['account'].replace(':', '.'),
            'sheet',
            args.format
        ])

        output: pathlib.Path = args.output
        assert output.is_dir(), f"--output {output} must be a valid directory."

        out_file = output.joinpath(file_name)

        document = dict(
            records=records,
            document=conf['document'],
            tab=conf['tab'],
            slug=slug,
            account=conf['account'],
            saved=datetime.datetime.today(),
            from_date=first_date,
            until_date=last_date,
            version="1.0",
            currencies=conf['currencies']
        )

        with out_file.open("w") as stream:
            if args.format == "yaml":
                yaml.dump(document, stream=stream)
            elif args.format == "json":
                json.dump(document, fp=stream, default=str, indent=2)
        logging.info(f"Wrote {out_file}")
        matches += 1

    print(f"Matched {matches} accounts.")
    if not matches:
        print("Valid Accounts are:")
        print(pprint.pformat(context['coolbean-accounts'].keys()))


def record_range(records:typing.List[dict]):
    first = None
    last = None
    for record in records:
        date = record.get('date', None)
        if not date:
            continue
        # We might need to parse this:
        best_date = dateparser.parse(date)
        if first is None or best_date < first:
            first = best_date
        if last is None or last < best_date:
            last = best_date

    return first, last


if __name__ == "__main__":
    main()
