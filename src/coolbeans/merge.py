"""Utility to split/merge/sort an existing bean file

Takes an existing beancount file, or list of files and sort/filter it generally into new files

Example:
    input file (staged.bean) -> [year].bean

    within year.bean, we sort by::

        meta['global-sort'], DATE, meta['sort'], [Balance, Transaction, Note], Primary Account

This is still a work in progress as the workflow is evolving.
"""

# std library
import typing
import logging
import os
import pathlib
import datetime
import re
import dateparser
import argparse

# beancount imports
from beancount.core import data, account
from beancount.loader import load_file
from beancount.parser import printer
from beancount.core.display_context import DisplayContext

# local library
from coolbeans.utils import logging_config
from coolbeans.apps import BEAN_FILE_ENV

# Logger
logger = logging.getLogger(__name__)


class BeanOrganizer:

    entries: list = None
    duplicates: dict = None
    year: int = None
    sort_method: str
    split_type: str

    def __init__(
            self,
            bean_file: pathlib.Path,
            input_files: list,
            output: pathlib.Path,

            split_type: str,
            sort_method: str = 'date',

            do_filter: bool = True,
            between: typing.Tuple[datetime.date, datetime.date] = None,
            filter_account: str = None,

    ):
        """
        Args:
            between:
            output:
            bean_file:
            input_files:
            split_type:
            filter_account:
            sort_method:
            do_filter:
        """
        from_date, through_date = between
        self.duplicates = {}
        self.entries = []
        self.merge_file = output

        # These are the same thing?
        self.sort_method = sort_method
        self.split_type = split_type

        # First add the existing core file:
        self.bean_file = pathlib.Path(bean_file).absolute()
        self.add_file(bean_file)

        source_files = []

        # Now Merge the Input Files
        for file_name in input_files:
            file_path = str(pathlib.Path(file_name).absolute())
            source_files.append(file_path)
            self.add_file(file_path)

        if do_filter:
            # In place Filter
            self.entries = self.filter_entries(
                self.entries,
                source_files,
                from_date,
                through_date,
                filter_account=filter_account
            )

    def filter_entries(self, entries, valid_files, date_start, date_end, filter_account=None):
        logger.debug(f"Filter {len(entries)} on:\n{valid_files}\nbetween {date_start} and {date_end} in account {filter_account}")
        result = []
        for entry in entries:
            if valid_files:
                if entry.meta.get('filename', '') not in valid_files:
                    logger.debug(f"Skipping {entry} not in source file")
                    continue

            if entry.date < date_start or entry.date > date_end:
                continue

            if filter_account:
                if not re.fullmatch(filter_account, entry.meta['_account']):
                    continue

            result.append(entry)
        logging.info(f"Filtered from {len(entries)} to {len(result)}.")
        return result

    def load_beanfile(self, file_name, stop_on_error=False):
        entries, errors, context = load_file(file_name)

        if errors and False:
            printer.print_errors(errors, sys.stderr)
            if stop_on_error:
                raise ValueError()

        return entries

    def add_file(self, file_name):
        """Add a new file to the existing entries"""
        entries = self.load_beanfile(file_name)
        for entry in entries:
            self.safe_add_entry(entry)

    def safe_add_entry(self, entry):
        """Check for possible duplicate in the existing self.entries"""

        if self.year:
            if entry.date.year != self.year:
                return

        # Loaded Transactions could have a match-key, to help de-duplicate
        match_key = entry.meta.get('match-key', None)
        if not match_key:
            # Roll our own match-key for some things
            match_key = printer.format_entry(entry)

        if isinstance(entry, data.Transaction) and entry.postings:
            # Sort on the first account
            for posting in entry.postings:
                account_parts =  account.split(posting.account)
                if account_parts[0] in ("Assets", "Liabilities"):
                    entry.meta['_account'] = posting.account
                    break
            else:
                # Use last account?
                entry.meta['_account'] = entry.postings[0]
        elif hasattr(entry, 'account'):
            entry.meta['_account'] = entry.account
        else:
            entry.meta['_account'] = 'other'

        found_match = False
        existing_entry = None
        remove_list = []

        # TODO do a yaml.load(match_key) to support list
        count = 0
        while match_key and not found_match:
            existing_entry = None
            if match_key in self.duplicates:
                existing_entry = self.duplicates.get(match_key)
            if existing_entry:
                # Don't do anything since it's duplicate
                found_match = True
            else:
                # Make note of this match-key
                self.duplicates[match_key] = entry
            count += 1
            # We support multiple match keys in the format 'match-key-1' .. 'match-key-N'
            match_key = entry.meta.get(f'match-key-{count}', None)

        if found_match:
            # We only "preserve" * entries.  Others might be overwritten.
            if not hasattr(existing_entry, 'flag'):
                # No need to check flags
                return
            # Make sure the existing_entry isn't "booked" with a '*'
            if existing_entry.flag == entry.flag or existing_entry.flag == '*':
                return
            else:
                # We need to replace the existing entry!
                remove_list.append(existing_entry)

        for item in remove_list:
            if item in self.entries:
                self.entries.remove(item)

        self.entries.append(entry)

    def sort_key(self, entry):
        logger.debug(f"Sorting {entry} on {self.sort_method}")
        account_sort_key = ()
        amount_sort_key = 0
        text_sort_key = ""
        method = self.sort_method

        account_sort_key = tuple(account.split(entry.meta['_account']))
        # Not sure in what cases this is needed, but just incase
        if isinstance(entry, data.TxnPosting):
            entry = entry.txn

        if isinstance(entry, data.Transaction) and entry.postings:
            # Sort on the first account
            for posting in entry.postings:
                amount_sort_key = -abs(posting.price.number) if posting.price else 0
                break

            text_sort_key = entry.narration

        if isinstance(entry, data.Note):
            account_sort_key = tuple(account.split(entry.account))
            text_sort_key = entry.comment

        if entry.meta.get('filename') == self.merge_file:
            # If we're dealing with a transaction originating from our existing file, respect the position
            line_number = entry.meta.get('lineno', 0)
        else:
            # Let's put it at the end of the day?
            line_number = 99999

        if method == 'date':
            return (
                entry.meta.get('global-sort', 100),
                entry.date,
                entry.meta.get('sort', 100),
                #  entry.meta.get('lineno', 0) if , # Not sure how highly to prioritize existing position.
                data.SORT_ORDER.get(type(entry), 0),
                account_sort_key,
                amount_sort_key,
                text_sort_key,
            )
        elif method == 'account':
            sort_key = (
                entry.meta.get('global-sort', 100),
                account_sort_key,
                entry.date,
                entry.meta.get('sort', 100),
                #           entry.meta.get('lineno', 0) if , # Not sure how highly to prioritize existing position.
                data.SORT_ORDER.get(type(entry), 0),
                amount_sort_key,
                text_sort_key,
            )
            logger.debug(f"{sort_key}")
            return sort_key
        else:
            raise ValueError(f"Unknown sort method {method}. Try date or account")

    def sorted_entries(self, sort_key=None):
        if not sort_key:
            sort_key = self.sort_key

        self.entries.sort(key=sort_key)

        for entry in self.entries:
            yield entry

    def fold_injector(self, outstream):

        sort_method = self.sort_method
        class DateFoldStreamProxy:
            old_date = None
            date_re = re.compile(r"(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d).*")

            def __init__(self, stream):
                self.stream = stream

            def render_month(self, date:datetime.date):
                return f"* {date.strftime('%B %Y')}\n"

            def render_date(self, date:datetime.date):
                return f"** {date.strftime('%Y-%m-%d - %A')}\n"

            def write(self, content):
                match = self.date_re.match(content)
                if match:
                    g = dict((k, int(v)) for k, v in match.groupdict().items())
                    new_date = datetime.date(**g)
                    old_date = self.old_date
                    self.old_date = new_date

                    if not old_date or new_date.month != old_date.month:
                        self.stream.write(self.render_month(new_date))

                    if not old_date or new_date.day != old_date.day:
                        self.stream.write(self.render_date(new_date))

                # Now write the Original Content
                self.stream.write(content)

        return DateFoldStreamProxy(outstream)

    def save_entries(self):
        context = DisplayContext()
        context.set_commas(True)
        if self.split_type == 'account':
            # Append records on a per-account-file basis
            entries = []
            previous_account = None
            for entry in self.sorted_entries():
                filing_account = entry.meta.pop('_account')
                if filing_account != previous_account:
                    file_name = pathlib.Path(filing_account.replace(':', '') + '.bean')

                    if self.merge_file.is_dir():
                        file_name = self.merge_file.joinpath(file_name)

                    logger.info(f"Writing {len(entries)} to {file_name.name}.")
                    with file_name.open("a") as stream:  # Add overwrite?
                        printer.print_entries(
                            entries,
                            file=stream,
                            dcontext=context,
                        )
                    entries = []
                entries.append(entry)
        else:
            # We will want to roll our own
            with self.merge_file.open("w") as outstream:
                printer.print_entries(
                    list(self.sorted_entries()),
                    file=self.fold_injector(outstream),
                    dcontext=context,
                )

def main():
    parser = argparse.ArgumentParser("Organizer")

    default_file = os.environ.get(BEAN_FILE_ENV, None)
    parser.add_argument(
        '-e', '--existing',
        metavar=BEAN_FILE_ENV,
        default=default_file,
        type=pathlib.Path,
        dest='bean_file',
        help=f"Beancount file to read the Open slugs. {'Default is '+ default_file if default_file else ''}"
    )
    parser.add_argument(
        "-f", "--from-date",
        default="1996-01-01",
        type=str,
        help="date from which to inject"
    )
    parser.add_argument(
        "-t", "--through-date",
        default=datetime.datetime.today().strftime("%Y-%m-%d"),
        type=str,
        help="date until which to inject"
    )
    parser.add_argument(
        "--account",
        default="",
        type=str,
        help="Filter Account"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="The bean file to sort entries into, or a directory."
    )
    parser.add_argument(
        "--split_type",
        action="store",
        default="year",
        choices=('year', 'account'),
        help="Split outbound files on 'year' or 'account'",
    )
    parser.add_argument(
        "input_files",
        nargs='*',
        help="Source files to load entries from."
    )
    args = parser.parse_args()

    logging_config(level=logging.DEBUG)

    assert args.bean_file.exists()

    # We "merge" into this file.  Entries not originating from this file are ignored
    output_path = pathlib.Path(args.output)
    assert output_path.exists(), f"Unable to find {output_path.absolute()}"

    from_date = through_date = None
    if args.from_date:
        pd:datetime.datetime = dateparser.parse(args.from_date)
        from_date = datetime.date(year=pd.year, month=pd.month, day=pd.day)

    if args.through_date:
        pd:datetime.datetime = dateparser.parse(args.through_date)
        through_date = datetime.date(year=pd.year, month=pd.month, day=pd.day)

    organizer = BeanOrganizer(
        between=(from_date, through_date),
        output=output_path.absolute(),
        input_files=args.input_files,
        bean_file=args.bean_file,
        split_type=args.split_type,
        do_filter=True,
        filter_account=args.account,
        sort_method=args.split_type
    )

    # Now we can print the new File
    organizer.save_entries()

if __name__ == "__main__":
    import sys
    main()
