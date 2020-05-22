"""
This Importer doesn't actuall import.  It just provides
a parser to identify the account/date related to a file
provided that the file is in a certain format.

YYYY-MM-DD-SLUG-TYPE.EXT

If there's a meta['slug'] on any account directive that lines up
with this account, we will identify this file.
"""
import re
import datetime
import dataclasses
from typing import Optional
import logging
import pathlib
from beancount.ingest.cache import _FileMemo as FileMemo

from beancount.ingest import importer
from beancount.parser import parser
from beancount.core import data

FILE_REX = (r"^(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)"
            r"[-.](?P<slug>[\w-]+).(?P<document>[\w-]+)\.(?P<ext>\w+)$")
FILE_RE = re.compile(FILE_REX, re.IGNORECASE)


logger = logging.getLogger(__name__)


@dataclasses.dataclass()
class FileDetails:
    file: pathlib.Path
    file_name: str
    slug: str
    ext: str
    document: str
    date: datetime.datetime


class Importer(importer.ImporterProtocol):

    def __init__(self, beanfile):
        self._auto_configure(beanfile)

    def _auto_configure(self, beanfile):
        logger.debug(f"Reading {beanfile}")
        slugs = {}
        entries, errors, context = parser.parse_file(beanfile)
        for entry in entries:
            if isinstance(entry, data.Open):
                slug = entry.meta.get('slug', None)
                if slug:
                    logger.debug(f"Found Slug {slug} for {entry.account}")
                    slugs[slug.lower()] = entry.account
        self.slugs = slugs

    def _expand_file(self, file_path) -> Optional[FileDetails]:
        try:
            if isinstance(file_path, FileMemo):
                file_path = file_path.name
            full_file = pathlib.Path(file_path)
            file = full_file.name

            logger.debug(f"Checking {file}")
            match = FILE_RE.match(file)
            if not match:
                return None
            matchgroup = match.groupdict()
            file_date = datetime.datetime(int(matchgroup['year']),
                                          int(matchgroup['month']),
                                          int(matchgroup['day']))
            fd = FileDetails(
                file=full_file,
                file_name=file,
                slug=matchgroup['slug'].lower(),
                ext=matchgroup['ext'],
                document=matchgroup['document'],
                date=file_date
            )
            logger.debug(f"Created File: {fd}")
        except Exception:
            logger.exception(f"While parsing {file_path}")
            raise
        return fd

    def name(self):
        return f"slugger"

    def identify(self, file: FileMemo) -> bool:
        try:
            fd = self._expand_file(file.name)
            if fd.slug:
                return True
        except:
            return False

    def file_account(self, file):
        logger.debug(f"file_account({file}")
        fd = self._expand_file(file)
        if fd is None: return None
        return self.slugs[fd.slug]

    def file_date(self, file) -> datetime.datetime:
        logger.debug(f"file_date({file}")
        fd = self._expand_file(file)
        return fd.date

    def file_name(self, file):
        """Returns the name without the date prtion"""
        logger.debug(f"file_name({file}")
        fd = self._expand_file(file)
        return f"{fd.slug}.{fd.document}.{fd.ext}".lower()
