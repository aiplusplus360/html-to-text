"""Turn a page into the article, not the navigation."""

__version__ = "0.1.0"

from .core import *  # noqa: F401,F403
from .core import __all__ as _core_all

__all__ = list(_core_all)
