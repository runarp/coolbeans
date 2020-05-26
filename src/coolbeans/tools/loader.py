"""
Simple Proxy Loader to prevent us from loading
the same bean_file multiple times for a single Import
"""
import typing
from beancount import loader

CACHE = None

def load_file(*args, **kwds):
    global CACHE
    if CACHE is None:
        CACHE = loader.load_file(*args, **kwds)
    return CACHE

def Meta(**kwds) -> typing.Dict[str, typing.Any]:
    meta = {}
    meta.setdefault('lineno', 0)
    meta.setdefault('filename', None)
    meta.update(kwds)
    return meta

