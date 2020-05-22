import typing
import logging
import importlib

logger = logging.getLogger(__name__)

def safe_plugin(func: typing.Callable) -> typing.Callable:
    # We might want to pull the logger out of the func module?
    try:
        log = importlib.import_module(func.__module__).logger
    except AttributeError:
        log = logger

    def do_work(*args):
        log.info(f"Loading Plugin {func.__name__}")
        try:
            return func(*args)
        except Exception as e:
            log.exception(f"{func.__name__}")
            raise

    return do_work
