"""
The one place that talks to GRA E-VAT.

GRA gives its API documentation and test access to each taxpayer during onboarding and signs off
the integration before go-live, so only a simulator exists here today. Nothing is sent to GRA.
When the documents arrive, map the payload to GRA's format and send it from submit(), and make
mode() return "live" or "test". The rest of the app, and the receipt wording, follow mode().
"""


class EvatUnavailable(Exception):
    """GRA could not be reached. The document stays queued and can be sent again."""


def mode():
    return "simulated"


def submit(payload):
    """Returns {"accepted": bool, "reference": str, "message": str}. Raises EvatUnavailable."""
    return {"accepted": True, "reference": f"SIM-{payload['number']}", "message": ""}
