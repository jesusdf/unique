"""SQL DML/DDL converter: sqlglot-backed parse + emit across dialects.

Split into submodules (_base shared state/helpers, harvest, convert, emit);
this package re-exports the public API for backward compatibility."""

from unique.core.converter._base import *  # noqa: F401,F403

# Private helpers reached by attribute (``converter._emit_update``) or imported
# by name from the procedural transformer; ``import *`` skips underscored names.
# The ``as`` alias marks them as explicit re-exports for mypy (strict).
from unique.core.converter.convert import *  # noqa: F401,F403
from unique.core.converter.convert import _convert_update as _convert_update
from unique.core.converter.emit import *  # noqa: F401,F403
from unique.core.converter.emit import _emit_create_table as _emit_create_table
from unique.core.converter.emit import _emit_update as _emit_update
from unique.core.converter.harvest import *  # noqa: F401,F403
