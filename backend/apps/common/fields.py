from django.db import models


def MoneyField(**kwargs):
    kwargs.setdefault("max_digits", 14)
    kwargs.setdefault("decimal_places", 2)
    kwargs.setdefault("default", 0)
    return models.DecimalField(**kwargs)


def QtyField(**kwargs):
    kwargs.setdefault("max_digits", 14)
    kwargs.setdefault("decimal_places", 3)
    kwargs.setdefault("default", 0)
    return models.DecimalField(**kwargs)
