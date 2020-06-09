"""CSV Extractor

Introspect, normalize and create "records" from a CSV (or other Tuple like) data source.

"""

#  import logging
#  import typing
import csv
import re
import dateparser
import datetime

# Coolbean imports
from coolbeans.extort import ExtortionProtocol


class Extorter(ExtortionProtocol):

    reader = csv.DictReader

    column_mappings: dict = None

    import_class = "csv"

    def extort(self, stream):
        for record in self.reader(stream):
            record = self.default_header(record)
            yield self.process_record(record)

    def get_clean_mappings(self, sample_record):
        mapping = {}
        for attr in dir(self):
            match = re.match(r'clean_(?P<key>\w*)', attr)
            if match:
                grp = match.groupdict()
                mapping[grp['key']] = getattr(self, attr)

        return mapping

    def process_record(self, record):
        if self.column_mappings:
            for ugly, clean in self.column_mappings.items():
                if ugly in record:
                    record[clean] = record.pop(ugly)

        clean_mappings: dict = self.get_clean_mappings(record)

        for key, value in record.items():
            if key in clean_mappings:
                method = clean_mappings[key]
                # The 'clean_' method should modify the dict in place
                method(key, value, record)

        return record

    def clean_date(self, key, value, record):
        """Extract a Beans Friend date from value"""
        dt = dateparser.parse(value)
        return datetime.date(year=dt.year, month=dt.month, day=dt.day)

class ExtortMerrill(Extorter):
    """
    sample Record
    {
    "Trade Date": "3/28/2019",
    "Settlement Date": "3/28/2019",
    "Pending/Settled": "Settled",
    "Account Nickname": "--",
    "Account Registration": "CMA",
    "Account #": "29N-XXXXX",
    "Type": "FundTransfers",
    "Description 1 ": "Wire Transfer In",
    "Description 2": "WIRE TRF IN D49087027227 ORG=/002151067807",
    "Symbol/CUSIP #": "--",
    "Quantity": "--",
    "Price ($)": "--",
    "Amount ($)": "3,300.00"
  }
    """

    column_mappings = {
            "Trade Date": "date",
            "Account #": "account_number",
            "Type": "type",
            "Description 1 ": "narration",
            "Description 2": "meta-detail",
            "Symbol/CUSIP #": "symbol",
            "Quantity": "quantity",
            "Price ($)": "price",
            "Amount ($)": "amount"
        }

    def get_clean_mappings(self, record) -> dict:
        mapping = super().get_clean_mappings(record)
        mapping['quantity'] = self.clean_price
        return mapping

    def clean_price(self, key, value, record):
        if value == "--":
            value = ""
        record[key] = value

    def clean_amount(self, key: str, value: str, record: dict) -> None:
        # Strip paranthesis
        if value.startswith("("):
            value = '-' + value[1:-1]
        value.replace(',', '')

        record[key] = value
