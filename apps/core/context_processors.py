from django.conf import settings


def app_meta(request):
    """Version and source-code URL, for the sidebar footer.

    `source_url` exists to satisfy AGPL section 13: anyone who runs a *modified*
    FarmSteader as a network service must offer its users the corresponding
    source, and the licence itself suggests a "Source" link in the interface as
    the way to do it. It is a setting rather than a constant precisely so that
    an operator who modifies the code can point it at *their* fork, which is
    what the licence actually requires of them -- pointing at upstream would not
    discharge the obligation.

    Empty by default, and the link is not rendered when it is empty, so an
    unconfigured install does not advertise a URL that does not exist.
    """
    return {
        "app_version": settings.APP_VERSION,
        "source_url": settings.FARMSTEADER_SOURCE_URL,
    }
