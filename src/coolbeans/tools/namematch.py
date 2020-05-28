import re
import typing
import dataclasses
import logging
import datetime
import pathlib


# Probably remove this support
from beancount.ingest.cache import _FileMemo as FileMemo


FILE_REX = (
    r"^(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)"
    r"[-.](s(?P<from_date>\d\d\d\d-\d\d-\d\d).)?"
    r"(?P<slug>[\w-]+)"
    r"(\.(?P<document>[\w-]+))?"
    r"(\.(?P<seq>[\d]+))?"
    r"\.(?P<ext>\w+)$")
FILE_RE = re.compile(FILE_REX, re.IGNORECASE)


@dataclasses.dataclass()
class FileDetails:
    file: pathlib.Path
    file_name: str
    slug: str
    ext: str
    document: typing.Optional[str]
    date: datetime.datetime
    from_date: typing.Optional[datetime.datetime]
    seq: typing.Optional[int] = 0

    @property
    def make_name(self):
        since = document = ''
        seq = ''

        if self.from_date:
            since = f".s{self.from_date.strftime('%Y-%m-%d')}"
        if self.document:
            document = f".{self.document}"

        if self.seq and self.seq != '0':
            seq = f".{self.seq}"

        return f"{self.date.strftime('%Y-%m-%d')}{since}.{self.slug}{document}{seq}.{self.ext}"

    def __repr__(self):
        """Attempt at a generic repr that uses indentation"""
        fields: dict = getattr(self, dataclasses._FIELDS)
        response = [f"{self.__class__.__name__}("]
        for field_name in fields:
            response.append(f"    {field_name}={repr(getattr(self, field_name))},")
        response.append(")")
        return '\n'.join(response)


def expand_file(file_path: typing.Union[str, pathlib.Path]) -> typing.Optional[FileDetails]:
    if isinstance(file_path, FileMemo):
        file_path = file_path.name
    full_file = pathlib.Path(file_path)
    file = full_file.name

    match = FILE_RE.match(file)
    if not match:
        return None
    matchgroup = match.groupdict()
    file_date = datetime.datetime(
        int(matchgroup['year']),
        int(matchgroup['month']),
        int(matchgroup['day'])
    )

    from_date = matchgroup.get('from_date', None)
    if from_date:
        from_date = datetime.datetime(*map(int, from_date.split('-')))

    # Handle file-clashing through renames
    seq = int(matchgroup.get('seq', 0) or 0)  # 'or 0' Handles the None case

    fd = FileDetails(
        file=full_file,
        file_name=file,
        slug=matchgroup['slug'].lower(),
        ext=matchgroup['ext'],
        document=matchgroup['document'],
        date=file_date,
        from_date=from_date,
        seq=seq
    )

    return fd
