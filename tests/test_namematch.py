import unittest
import datetime
import pathlib

from coolbeans.tools.namematch import FILE_RE, FileDetails, expand_file


class TestMatch(unittest.TestCase):
    def test_matches(self):
        name = "2018-04-27.trades.doc.csv"
        result = expand_file(name)
        self.assertEqual(result.date, datetime.datetime(year=2018, month=4, day=27))
        self.assertEqual(result.ext, 'csv')


    def test_matches(self):
        name = "2018-04-27.trades.doc.csv"
        result = expand_file(name)
        self.assertEqual(result.date, datetime.datetime(year=2018, month=4, day=27))
        self.assertEqual(result.ext, 'csv')
        self.assertEqual(result.document, 'doc')
        self.assertEqual(result.slug, 'trades')

    def test_matche2(self):
        name = "2020-01-03-aviator.statement.pdf"
        result = expand_file(name)
        self.assertEqual(
            result.date,
            datetime.datetime(year=2020, month=1, day=3))
        self.assertEqual(result.ext, 'pdf')
        self.assertEqual(result.slug, 'aviator')
        self.assertEqual(result.document, 'statement')

    def test_matche3(self):
        name = "2020-01-03-aviator.pdf"
        result = expand_file(name)
        self.assertEqual(
            result.date,
            datetime.datetime(year=2020, month=1, day=3))
        self.assertEqual(result.ext, 'pdf')
        self.assertEqual(result.slug, 'aviator')
        self.assertEqual(result.document, None)

    def test_matche4(self):
        name = "2018-09-27-ledger-USD-deposit.csv"
        result = expand_file(name)
        self.assertEqual(
            result.date,
            datetime.datetime(year=2018, month=9, day=27)
        )
        self.assertEqual(result.ext, 'csv')
        self.assertEqual(result.slug, 'ledger-usd-deposit')
        self.assertEqual(result.document, None)

    def test_since_date(self):
        file = pathlib.Path("2018-09-27.s2018-09-01.nbi-1857.csv")
        result = expand_file(file)
        self.assertEqual(
            result,
            FileDetails(
                file_name=file.name,
                date=datetime.datetime(year=2018, month=9, day=27),
                from_date=datetime.datetime(year=2018, month=9, day=1),
                slug="nbi-1857",
                ext="csv",
                file=file,
                document=None,
                seq=0
            )
        )

    def test_since_date2(self):
        file = pathlib.Path("2018-09-27.s2018-09-01.nbi-1857.export.csv")
        result = expand_file(file)
        self.assertEqual(
            result,
            FileDetails(
                file_name=file.name,
                date=datetime.datetime(year=2018, month=9, day=27),
                from_date=datetime.datetime(year=2018, month=9, day=1),
                slug="nbi-1857",
                ext="csv",
                file=file,
                document='export',
                seq=0
            )
        )

    def test_since_date_seq(self):
        file = pathlib.Path("2018-09-27.s2018-09-01.nbi-1857.export.2.csv")
        result = expand_file(file)
        self.assertEqual(
            result,
            FileDetails(
                file_name=file.name,
                date=datetime.datetime(year=2018, month=9, day=27),
                from_date=datetime.datetime(year=2018, month=9, day=1),
                slug="nbi-1857",
                ext="csv",
                file=file,
                document='export',
                seq=2
            )
        )

    def test_with_match_seq(self):
        file = pathlib.Path("ParaisoExpenses/Utility Statements/MERALCO/Paraiso/2020-01-20.paraiso-meralco.statment.pdf")
        result = expand_file(file)
        self.assertEqual(
            result,
            FileDetails(
                file_name=file.name,
                date=datetime.datetime(year=2020, month=1, day=20),
                from_date=None,
                slug="paraiso-meralco",
                ext="pdf",
                file=file,
                document='statement',
                seq=0
            )
        )
        self.assertEqual(file.name, result.make_name)
