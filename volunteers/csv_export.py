"""CSV downloads that open cleanly in Excel and can't smuggle in formulas."""

import csv

from django.http import HttpResponse

FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe(value) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_PREFIXES) else text


def csv_response(filename, header, rows) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")  # BOM: Excel reads the file as UTF-8
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe(value) for value in row])
    return response
