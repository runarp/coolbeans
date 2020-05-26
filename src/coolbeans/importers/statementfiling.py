"""
This Importer doesn't actually import.  It just provides
a parser to identify the account/date related to a file
provided that the file is in a certain format.

YYYY-MM-DD.SLUG.TYPE.EXT

If there's a meta['slug'] on any account directive that lines up
with this account, we will identify the file.

"""
import re
import datetime
import logging
import pathlib
import os
import sys


from beancount.ingest.cache import _FileMemo as FileMemo
from beancount.ingest import importer
from beancount.loader import load_file
from beancount.parser import parser
from beancount.core import data
from coolbeans.tools.namematch import expand_file

BEAN_FILE_ENV = 'BEAN_FILE'

logger = logging.getLogger(__name__)


class Importer(importer.ImporterProtocol):

    def __init__(self, bean_file: str=None):
        if bean_file is None:
            bean_file = os.environ.get(BEAN_FILE_ENV, None)

        assert pathlib.Path(bean_file).exists(), f"Unable to find bean file {beanfile}."

        self._auto_configure(bean_file)

    def _auto_configure(self, bean_file: str):
        """Given a beancount file, extract any Open tag 'slug' meta data."""
        entries, errors, context = load_file(bean_file, log_errors=sys.stderr)
        assert 'slugs' in context, "Requires 'coolbeans.plugins.slugs'"
        self.slugs = context['slugs']

    def name(self):
        return f"filing"

    def identify(self, file: FileMemo) -> bool:
        try:
            fd = expand_file(file.name)
            if fd.slug:
                return True
        except:
            return False

    def file_account(self, file):
        logger.debug(f"file_account({file}")
        fd = expand_file(file)
        if fd is None:
            return None
        return self.slugs[fd.slug]

    def file_date(self, file) -> datetime.datetime:
        logger.debug(f"file_date({file}")
        fd = expand_file(file)
        return fd.date

    def file_name(self, file):
        """Returns the name without the date portion"""
        logger.debug(f"file_name({file})")
        fd = expand_file(file)

        return f"{fd.slug}.{fd.document}.{fd.ext}".lower()
