"""Landsbankinn of Iceland, Personal CSV file export

Sample Row/Headers are:
Dagsetning	Vaxtadagur	Tilvísun	Skýring	Texti	Upphæð	Staða	Númer útibús	Stutt tilvísun
5/15/20 0:00	5/15/20 0:00	GV165636	Fj.skatt gengishagnað	Guðmundur Rúnar Pétursson	-199.2	7,258.2	0152
"""

import datetime
import decimal
import typing
import dataclasses
import logging

import openpyxl

from coolbeans.extort.base import ExtortionProtocol


logger = logging.getLogger(__name__)


HEADER_MAP = dict(
    date='Dagsetning',
    #   posting_date='Vaxtadagur',
    refference='Tilvísun',
    tx_id='Stutt tilvísun',
    payee='Texti',
    narration='Skýring',
    amount='Upphæð',
    balance='Staða',
    #   bank_number='Númer útibús',
)
MAP_BY_VALUE = dict((v.lower(), k) for (k, v) in HEADER_MAP.items())

INFO_MAP = dict(
    account_number="B2",
    balance="B3",
    currency="B4",
    owner="B5",
    social="B6",
    account_name="B7"
)


def map_header(row:list, value_map: dict):
    # Reverse the Map to be by Foreign Character
    # print(f"{row} | {value_map}")
    row = [cell.value.lower().strip() for cell in row]
    return dict(
        (v, row.index(k)) for (k, v) in value_map.items()
    )


def extort_row(row, header, mapping):
    """Returns a single record"""

    parameters = {}
    for field, index in mapping.items():
        cell = row[index]
        value = cell.value

        if field == 'date':
            value = datetime.date(
                year=value.year,
                month=value.month,
                day=value.day
            )

        if field == 'amount':
            value = decimal.Decimal(value).quantize(decimal.Decimal("0.01"))

        parameters[field] = value

    # pass-through parameters (the entire header)
    parameters.update(header)

    return parameters


def pull_info(wb) -> dict:
    sheet = wb['Reikningur']
    result = {}
    for field, loc in INFO_MAP.items():
        result[field] = sheet[loc].value
    return result


class Extorter(ExtortionProtocol):

    def extort(self, stream: typing.IO[typing.AnyStr]):
        """Extract as much information as possible from the workbook"""

        wb = openpyxl.open(
            stream,
            read_only=True,
        )
        sheet = wb.active

        context = pull_info(wb)
        col_map = {}

        for row in sheet.rows:
            if not col_map:
                col_map = map_header(row, MAP_BY_VALUE)
            else:
                yield self.add_header(
                    extort_row(row, col_map, context)
                )
