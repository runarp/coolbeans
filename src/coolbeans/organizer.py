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
import sys
import pathlib
import datetime
import re
import dateparser
import argparse

# beancount imports
from beancount.core import data, account
from beancount.loader import load_file
from beancount.parser import printer

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
            entries_count = len(self.entries)
            self.add_file(file_path)
            print(f"Loaded {len(self.entries)-entries_count} new from {file_name}")

        if do_filter:
            # In place Filter
            self.entries = self.filter_entries(
                self.entries,
                source_files + [str(self.merge_file.absolute())],
                from_date,
                through_date,
                filter_account=filter_account
            )

    def filter_entries(self, entries, valid_files, date_start, date_end, filter_account=None):
        logger.debug(
            f"Filter {len(entries)} on:\n{valid_files}\n"
            f"between {date_start} and {date_end} in account {filter_account}"
        )
        result = []
        for entry in entries:
            if valid_files:
                if entry.meta.get('filename', '') not in valid_files:
                    # logger.debug(f"Skipping {entry} not in source file {valid_files}")
                    continue

            if entry.date < date_start or entry.date > date_end:
                continue

            if filter_account:
                if not re.fullmatch(filter_account, entry.meta['_account']):
                    logger.debug(f"Skipping {filter_account} != {entry.meta['_account']} ")
                    continue

            result.append(entry)
        logging.info(f"Filtered from {len(entries)} to {len(result)}.")
        return result

    def load_beanfile(self, file_name, stop_on_error=False):
        entries, errors, context = load_file(file_name)

        if errors:
            printer.print_errors(errors, sys.stderr)
            if stop_on_error:
                raise ValueError()

        return entries

    def add_file(self, file_name):
        """Add a new file to the existing entries"""
        entries = self.load_beanfile(file_name, stop_on_error=False)
        logger.debug(f"Found {len(entries)} potential entries in {file_name}")
        for entry in entries:
            self.safe_add_entry(entry)

    def safe_add_entry(self, entry):
        """Check for possible duplicate in the existing self.entries"""

        assert '_account' not in entry.meta, str(entry)

        # Skip Open Statements
        if isinstance(entry, data.Open):
            return

        if isinstance(entry, data.Document):
            return

        # Loaded Transactions could have a match-key, to help de-duplicate
        match_key = entry.meta.get('match-key', None)
        if not match_key:
            # Roll our own match-key for some things. Sha?
            match_key = printer.format_entry(entry)

        # Tag each entry with an "Account" Based on attribute, or best guess on Postings
        if isinstance(entry, data.Transaction) and entry.postings:
            # Computed Entry, don't add
            if entry.flag == 'P':
                return

        entry.meta['_account'] = self.guess_account(entry)

        # This will posibly delete entries from our source file.
        self.remove_exising_duplicate(entry)

        # Add back the good entry at the end
        self.entries.append(entry)
        self.entries.append(entry)

    def remove_exising_duplicate(self, entry: data.Directive):
        """
        In some cases the incoming "source" file contains entires that have been "matched" with a flag of '*'
        while the existing entry in the file has a '!' status.  In that case, we want to swap out the entries
        and write the New entry to the file.  This is usually as a result of Rules based Fixes in a staged file,
        such as new-entries.beans.  Since we're modifying an existing stream, this is a bit tricky and probably
        not the ideal way to handle this.

        Args:
            entry: the new entry to possibly swap in

        Returns:
            None, mutates self.entries instead.
        """

        # Use just match-key for now, this matching business is a whole different issue:
        match_key = entry.meta.get('match-key', None)
        found_match_key = False
        existing_entry = None

        # Should just be one!
        remove_list = []

        count = 0
        while match_key and not found_match_key:
            existing_entry = None

            if match_key in self.duplicates:  # Be careful with duplicate matches, use the original
                existing_entry = self.duplicates.get(match_key)

            if existing_entry:
                # Don't do anything since it's duplicate
                found_match_key = True
            else:
                # Make note of this match-key
                self.duplicates[match_key] = entry

            count += 1

            # We support multiple match keys in the format 'match-key-1' .. 'match-key-N'
            # TODO(gp) this is too complicated, remove
            match_key = entry.meta.get(f'match-key-{count}', None)

        if found_match_key:
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

        # Once we have a list of items that are "Matched" and went from '!' -> '*', delete the '!' ones:
        for item in remove_list:
            if item in self.entries:
                self.entries.remove(item)

    def sort_key(self, entry):
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

            def close(self):
                self.stream.close()

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

    def guess_account(self, entry: data.Directive) -> str:
        # Tag each entry with an "Account" Based on attribute, or best guess on Postings
        if isinstance(entry, data.Transaction) and entry.postings:
            logger.debug(f"Guessing account for {entry} in {entry.meta['filename']}")
            # Sort on the first account
            for posting in entry.postings:
                account_parts =  account.split(posting.account)
                if account_parts[0] in ("Assets", "Liabilities"):
                    return posting.account
            else:
                return entry.postings[0]
        elif hasattr(entry, 'account'):
            return entry.account
        else:
            return 'other'

    def save_entries(self):
        from beancount.core.display_context import DisplayContext
        context = DisplayContext()
        context.set_commas(True)
        if self.split_type == 'account':
            # Append records on a per-account-file basis
            entries = []
            previous_account = None
            streams_by_account = {}
            for entry in self.sorted_entries():
                filing_account = entry.meta.pop('_account', None) or self.guess_account(entry)

                if filing_account not in streams_by_account:
                    file_name = pathlib.Path(filing_account.replace(':', '.') + '.bean')
                    if self.merge_file.is_dir():
                        file_name = self.merge_file.joinpath(file_name)
                    streams_by_account[filing_account] = self.fold_injector(file_name.open("a"))

                stream = streams_by_account[filing_account]
                printer.print_entries(
                    [entry],
                    file=stream,
                    dcontext=context,
                )
            for stream in streams_by_account.values():
                stream.close()
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
        default="date",
        choices=('date', 'account'),
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
