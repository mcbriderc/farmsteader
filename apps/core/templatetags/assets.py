"""Cache-busted static URLs.

`runserver` serves static files with a `Last-Modified` header and nothing else
-- no `Cache-Control`, no `ETag`. With no explicit freshness, Chromium falls
back to heuristic caching: it treats the response as fresh for 10% of the file's
age. `static/css/dist/styles.css` is git-ignored and typically weeks old by the
time anyone edits the theme, which buys the stale copy days of freshness, and
since Chrome 54 a plain reload revalidates only the document, not its still-fresh
subresources. The result is a CSS change that is invisible in every already-open
tab until the user knows to hard-reload -- which reads as "the fix didn't work"
rather than "the browser didn't ask".

Stamping the URL with the file's mtime makes a rebuild a *different URL*, so
there is no cache entry to go stale. This matters most in development, but the
stamp is harmless in production and buys the same guarantee across a deploy.

Falls back to the plain URL if the file cannot be stat'd -- a non-filesystem
storage backend, or a checkout where Tailwind has not been built yet.
"""

import os

from django import template
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_versioned(path):
    """`{% static %}` plus a `?v=<mtime>` stamp."""
    url = static(path)
    try:
        located = finders.find(path) or staticfiles_storage.path(path)
        return f"{url}?v={int(os.path.getmtime(located))}"
    except (OSError, NotImplementedError, TypeError, ValueError):
        return url
