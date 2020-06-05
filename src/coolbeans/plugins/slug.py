import re
import logging
# beancount imports
from beancount.core import data
from coolbeans.utils import safe_plugin

logger = logging.getLogger(__name__)


__plugins__ = ['account_slug_plugin']

SLUG_OPEN_META_KEY = 'slug'  # name under meta
SLUG_CONTEXT_KEY = 'slugs'    # name in context


def clean_slug(slug):
    """Clean a possible Slug string to remove dashes and lower case."""
    return slug.replace('-', '').lower()


def account_slug(entries, context):
    """Given a set of entries, pull out any slugs and add them to the context"""
    slugs = context.setdefault(SLUG_CONTEXT_KEY, {})

    # Pull out any 'slug' meta data
    for entry in entries:
        if not isinstance(entry, data.Open):
            continue
        slug = entry.meta.get(SLUG_OPEN_META_KEY, None)
        if not slug:
            continue
        slug = clean_slug(slug)
        multiple = re.split(r'[\s,]', slug)

        for s in multiple:
            if not s:
                continue

            slugs[s] = entry.account

    return entries, []


account_slug_plugin = safe_plugin(account_slug)
