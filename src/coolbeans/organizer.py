"""
# The Organizer
Take an existing beancount file.  And "Organize" the entires such that:

input file (staged.bean) -> [year].bean

within year.bean, we sort by:

meta['global-sort'], DATE, meta['sort'], [Balance, Transaction, Note], Primary Account

In general, year files always need to be round-tripable, this allows for clean "filing" of new
transactions, progmatic balancing/matching of transactions.

"""
import typing
import logging
import sys
import pathlib
import datetime
import re
import dateparser

# beancount imports
from beancount.core import data, account
from beancount.loader import  load_file, load_string
from beancount.parser import printer


# Logger
logger = logging.getLogger(__name__)


class BeanOrganizer:

    entries: list = None
    duplicates: set = None
    year: int = None

    def __init__(
            self,
            between:typing.Tuple[datetime.date, datetime.date],
            merge_file:pathlib.Path,
            bean_file:pathlib.Path,
            stage_files:list,
            filter_account:str=None
    ):
        from_date, through_date = between
        self.duplicates = set()
        self.entries = []
        self.merge_file = merge_file

        # First add the existing core file:
        self.bean_file = pathlib.Path(bean_file).absolute()
        self.add_file(bean_file)

        source_files = [str(pathlib.Path(merge_file).absolute())]

        # Now Merge the Stage Files
        for file_name in stage_files:
            file_path = str(pathlib.Path(file_name).absolute())
            source_files.append(file_path)
            self.add_file(file_path)

        # In place Filter
        self.entries = self.filter_entries(
            self.entries,
            source_files,
            from_date,
            through_date,
            filter_account=filter_account
        )

    def filter_entries(self, entries, valid_files, date_start, date_end, filter_account=None):
        result = []
        for entry in entries:
            if entry.meta.get('filename', '') not in valid_files:
                continue
            if entry.date < date_start or entry.date > date_end:
                continue

            if filter_account:
                found = False
                for posting in entry.postings:
                    if posting.account == filter_account:
                        found = True
                        break
                if not found:
                    continue

            result.append(entry)
        logging.info(f"Filtered from {len(entries)} to {len(result)} based on {valid_files}.")
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

        found_match = False
        existing_entry = None
        remove_list = []

        # TODO do a yaml.load(match_key) to support list
        count = 0
        while match_key and not found_match:
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
        account_sort_key = ()
        amount_sort_key = 0
        text_sort_key = ""

        # Not sure in what cases this is needed, but just incase
        if isinstance(entry, data.TxnPosting):
            entry = entry.txn

        if isinstance(entry, data.Transaction) and entry.postings:
            # Sort on the first account
            posting: data.Posting = entry.postings[0]
            account_sort_key = tuple(account.split(posting.account))
            amount_sort_key = -abs(posting.price.number) if posting.price else 0
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

        return (
            entry.meta.get('global-sort', 100),
            entry.date,
            entry.meta.get('sort', 100),
#           entry.meta.get('lineno', 0) if , # Not sure how highly to prioritize existing position.
            data.SORT_ORDER.get(type(entry), 0),
            account_sort_key,
            amount_sort_key,
            text_sort_key,
        )

    def sorted_entries(self, sort_key=None):
        if not sort_key:
            sort_key = self.sort_key

        self.entries.sort(key=sort_key)

        for entry in self.entries:
            yield entry

    def fold_injector(self, outstream):

        class StreamProxy:
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

        return StreamProxy(outstream)

    def save_entries(self):
        # We will want to roll our own
        with open(self.merge_file, "w") as outstream:
            printer.print_entries(
                list(self.sorted_entries()),
                file=self.fold_injector(outstream)
            )

def main():
    import argparse
    parser = argparse.ArgumentParser("Organizer")
    parser.add_argument("-e", "--existing", required=True, dest="bean_file")

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
        "-m", "--merge-file",
        default=None,
        help="The bean file to sort entries into."
    )
    parser.add_argument(
        "stage_file",
        nargs='*',
        help="Source files to load entries from."
    )
    args = parser.parse_args()

    # We "merge" into this file.  Entries not originating from this file are ignored
    merge_file = pathlib.Path(args.merge_file)
    assert merge_file.exists(), f"Unable to find {merge_file.absolute()}"

    pd:datetime.datetime = dateparser.parse(args.from_date)
    from_date = datetime.date(year=pd.year, month=pd.month, day=pd.day)
    pd:datetime.datetime = dateparser.parse(args.through_date)
    through_date = datetime.date(year=pd.year, month=pd.month, day=pd.day)

    organizer = BeanOrganizer(
        between=(from_date, through_date),
        merge_file=merge_file.absolute(),
        bean_file=args.bean_file,
        stage_files=args.stage_file
    )

    # Now we can print the new File
    organizer.save_entries()

if __name__ == "__main__":
    import sys
    logging.basicConfig(stream=sys.stderr)
    main()
