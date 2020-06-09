"""Base Extortion utilities

An extorter wrangles data out of ugly data formats.  The output isn't a perfect accounting record, but rather just
a list of dicts that are pseudo-usable for further processing.  In general, we like to:

* Capture as much usable information as possible
* Standardize on names/columns/headings where possible
* keep "business" logic out of this.  Things that might be specific to a person's bean workflow.
* Avoid "user" workflow specific things (which hopefully means don't read a beanfile for config.
"""

import typing


class ExtortionProtocol:
    """An Extortion Class accepts a file or stream and extracts records from the data.
    """

    FILE_OPEN_MODE: str = "r"
    DEBUG: bool = False

    HEADER_ATTRIBUTES = ('source_file', 'source_type', 'import_class', 'default_currency', 'default_account')
    source_file: str

    header: dict

    def __init__(self, debug=False):
        self.DEBUG = debug

    def set_header(self, record: dict):
        self.header = record

    def add_header(self, record: dict):
        record.update(self.header)
        return record

    def extort(self, stream: typing.IO[typing.AnyStr]) -> typing.Iterator:
        """This should be implemented by the subclass.  In general should end with a:

            yield self.add_header(record)
        """
        raise NotImplementedError
