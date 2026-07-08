# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Re-export of the shared SQL statement splitter.

The implementation moved into the product (``unique.core.sql_split``) when the
output validity gate (audit doc 04, M1) started needing it at transpile time;
tests and scripts keep importing it from here.
"""

from unique.core.sql_split import is_executable, split_statements

__all__ = ["is_executable", "split_statements"]
