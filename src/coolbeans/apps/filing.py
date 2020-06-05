"""Statement Filing CLI

CLI to let us use the Statement Filing Plugin

Purely a name-match based filing system.  Reads the "slug" of the file name to decide on the folder without reading
the contents.  Good for well formatted file names and obtuse data.
"""

# stdlib imports
import os
import sys
import argparse
import pathlib
import logging
import pprint
import typing

# beancount imports
from beancount.loader import load_file

from coolbeans.tools.namematch import expand_file
from coolbeans.apps import BEAN_FILE_ENV


logger = logging.getLogger(__name__)


def filing_handler(
        source_directories: typing.List[pathlib.Path],
        destination: pathlib.Path,
        slugs: typing.Dict[str, str],
        dry_run=False
        ):
    """Recurse through a list of source directories looking for filing matching a regular expression format:

    Args:
        source_directories (list): Source Folders to search
        destination: Single target folder, we will create Assests/Liabilities under this
        slugs: slug dict to use.
        dry_run: if True we dont' do any real work, just print out details

    Returns:
        None -- Moves files instead
    """

    for folder in source_directories:
        for file in folder.rglob("*"):
            match = expand_file(file)
            if match is None:
                continue

            account = slugs.get(match.slug, None)
            if not account:
                account = slugs.get(match.slug.replace('-', ''), None)
            if not account:
                logger.info(f"Unable to find matching account for slug {match.slug}. [{match.file}]"
                            f"\n{pprint.pformat(slugs)}")
                continue

            sub_directory = account.replace(':', '/')
            target_directory = destination.joinpath(sub_directory)

            # Just incase
            target_file = target_directory.joinpath(match.make_name)
            count = 0

            if target_file == file:
                # noop
                continue

            # Rename duplicate files
            possible_target: pathlib.Path = target_file
            sep = '.'
            while possible_target.exists():
                print(f"Found matching file {possible_target}")
                count += 1
                possible_target = target_file.parent.joinpath(
                    target_file.stem
                    + sep + str(count)
                    + target_file.suffix
                )

            if not dry_run:
                if not (target_directory.exists() and target_directory.is_dir()):
                    print(f"mkdir {target_directory}")
                target_directory.mkdir(parents=True, exist_ok=True)
                file.rename(possible_target)
                print(f"MOVED {file} -> {possible_target}")
            else:
                if not (target_directory.exists() and target_directory.is_dir()):
                    logger.info(f"DRY: mkdir {target_directory}")
                    print(f"DRY: mkdir {target_directory}")
                logger.info(f"DRY: mv {file} -> {possible_target}")
                print(f"mv {file} -> {possible_target}")


def configure_parser(parser):
    default_file = os.environ.get(BEAN_FILE_ENV, None)
    parser.add_argument(
        '-e', '--existing',
        metavar=BEAN_FILE_ENV,
        default=default_file,
        type=pathlib.Path,
        dest='bean_file',
        help=f"Beancount file to read the Open slugs. {'Default is '+ default_file if default_file else ''}"
    )
    parser.add_argument(
        '-v', '--debug',
        action='store_true',
        default=False
    )
    parser.add_argument(
        '-n', '--dry-run',
        action='store_true',
        default=False
    )
    parser.add_argument(
        dest='destination_folder',
        metavar='DESTINATION',
        type=pathlib.Path
    )
    parser.add_argument(
        dest='source_folders',
        metavar='SOURCE',
        nargs='+',
        type=pathlib.Path,
        help="Source folder(s) to scan for documents.",
        default=list()
    )
    return parser


def main():
    parser = argparse.ArgumentParser("Filing App")
    configure_parser(parser)

    args = parser.parse_args()

    if not args.bean_file.exists():
        print(f"Unable top find {args.bean_file}.")
        sys.exit(1)

    for folder in args.source_folders:
        assert isinstance(folder, pathlib.Path)
        if not folder.is_dir():
            print(f"Invalid source folder {folder}.")
            sys.exit(1)

    if not args.destination_folder.is_dir():
        print(f"Invalid destination folder {args.destination_folder}.")
        sys.exit(1)

    if args.debug:
        logging.basicConfig(
            format="%(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
            level=logging.DEBUG,
            stream=sys.stderr
        )

    # Read the Beanfile
    logger.info(f"Loading {args.bean_file}.")
    entries, errors, context = load_file(
        args.bean_file,
        log_errors=logger.error,
        log_timings=logger.info
    )
    logger.info(f"Read {len(entries)} entries.")

    slugs = context['slugs']

    filing_handler(
        source_directories=args.source_folders,
        destination=args.destination_folder,
        slugs=slugs,
        dry_run=args.dry_run,
    )

if __name__ == "__main__":
    main()
