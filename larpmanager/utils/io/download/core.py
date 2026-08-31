# LarpManager - https://larpmanager.com
# Copyright (C) 2025 Scanagatta Mauro
#
# This file is part of LarpManager and is dual-licensed:
#
# 1. Under the terms of the GNU Affero General Public License (AGPL) version 3,
#    as published by the Free Software Foundation. You may use, modify, and
#    distribute this file under those terms.
#
# 2. Under a commercial license, allowing use in closed-source or proprietary
#    environments without the obligations of the AGPL.
#
# If you have obtained this file under the AGPL, and you make it available over
# a network, you must also make the complete source code available under the same license.
#
# For more information or to purchase a commercial license, contact:
# commercial@larpmanager.com
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR Proprietary
from __future__ import annotations

import csv
import io
import zipfile
from typing import Any

import pandas as pd
from django.http import HttpResponse

from larpmanager.utils.io.download.writing import export_data
from larpmanager.utils.security.csv_validation import SanitizingCsvWriter, sanitize_dataframe


def _temp_csv_file(column_headers: Any, data_rows: Any) -> Any:
    """Create CSV content from keys and values."""
    df = sanitize_dataframe(pd.DataFrame(data_rows, columns=column_headers))
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)
    return buffer.getvalue()


def zip_exports(context: Any, exports: Any, filename: Any) -> Any:
    """Create ZIP file containing multiple CSV exports.

    Args:
        context: Context dictionary with run information
        exports: List of (name, keys, values) tuples
        filename: Base filename for ZIP

    Returns:
        HttpResponse: ZIP file download response

    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for export_name, csv_headers, csv_rows in exports:
            if not csv_headers or not csv_rows:
                continue
            zip_file.writestr(f"{export_name}.csv", _temp_csv_file(csv_headers, csv_rows))
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.read(), content_type="application/zip")
    response["Content-Disposition"] = f"attachment; filename={context['run']!s} - {filename}.zip"
    return response


def download(context: Any, typ: Any, nm: Any) -> Any:
    """Generate downloadable ZIP export for model type."""
    exports = export_data(context, typ)
    return zip_exports(context, exports, nm.capitalize())


def get_writer(context: dict, nm: str) -> tuple[HttpResponse, csv.writer]:
    """Create CSV writer with proper headers for file download."""
    # Create HTTP response with CSV content type and download headers
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="{}-{}.csv"'.format(context["event"], nm)},
    )

    # Initialize CSV writer with tab delimiter
    writer = SanitizingCsvWriter(csv.writer(response, delimiter="\t"))
    return response, writer
