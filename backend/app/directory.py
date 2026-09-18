from .config import settings
from .ldap_client import DirectoryError, LdapDirectory
from .mock import MockDirectory

_directory = None


def get_directory():
    global _directory
    if _directory is None:
        _directory = MockDirectory() if settings.mock else LdapDirectory()
    return _directory


__all__ = ["get_directory", "DirectoryError", "settings"]
