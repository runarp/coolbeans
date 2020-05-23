import re
import typing
import dataclasses
import logging
import datetime
import pathlib


# Probably remove this support
from beancount.ingest.cache import _FileMemo as FileMemo


FILE_REX = (r"^(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)"
            r"[-.](?P<slug>[\w-]+).(?P<document>[\w-]+)\.(?P<ext>\w+)$")
FILE_RE = re.compile(FILE_REX, re.IGNORECASE)


@dataclasses.dataclass()
class FileDetails:
    file: pathlib.Path
    file_name: str
    slug: str
    ext: str
    document: str
    date: datetime.datetime


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
    fd = FileDetails(
        file=full_file,
        file_name=file,
        slug=matchgroup['slug'].lower(),
        ext=matchgroup['ext'],
        document=matchgroup['document'],
        date=file_date
    )

    return fd
