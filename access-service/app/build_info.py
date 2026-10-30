"""The permission service reads its own packaged version, independent of CLI."""
from ._version import __version__


def application_version():
    return __version__
