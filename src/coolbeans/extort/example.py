"""Example Extorter, useful as a starting point"""

import datetime
import decimal
import typing
import logging

from coolbeans.extort.base import ExtortionProtocol


logger = logging.getLogger(__name__)


class Extorter(ExtortionProtocol):

    FILE_OPEN_MODE = None  # This requires a file-name, not a

    def extort(self, stream: typing.Union[typing.IO[typing.AnyStr], str]):
        """Extract as much information as possible from the workbook"""

        for row in stream:
            yield dict(row)
