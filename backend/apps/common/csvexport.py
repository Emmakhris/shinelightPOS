import csv

from django.http import HttpResponse


def csv_response(filename, columns, rows):
    """columns: list of (key, header). rows: list of dicts."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow([header for _, header in columns])
    for row in rows:
        writer.writerow([row.get(key, "") for key, _ in columns])
    return response


def wants_csv(request):
    return request.query_params.get("export") == "csv"
