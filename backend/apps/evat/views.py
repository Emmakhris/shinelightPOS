from django.db.models import Count
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.accounts.permissions import HasPerm
from apps.accounts.services import audit

from . import connector, services
from .models import EvatSubmission


class SubmissionSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = EvatSubmission
        fields = ["id", "kind", "kind_label", "number", "status", "status_label", "simulated", "reference", "message",
                  "attempts", "created_at", "sent_at"]


def _overview():
    counts = {row["status"]: row["n"] for row in EvatSubmission.objects.values("status").annotate(n=Count("pk"))}
    problems = EvatSubmission.objects.exclude(status=EvatSubmission.Status.ACCEPTED).order_by("created_at")[:200]
    latest = EvatSubmission.objects.filter(status=EvatSubmission.Status.ACCEPTED).order_by("-created_at")[:50]
    return {
        "mode": connector.mode(),
        "counts": {status: counts.get(status, 0) for status in EvatSubmission.Status.values},
        "submissions": SubmissionSerializer([*problems, *latest], many=True).data,
    }


@api_view(["GET"])
@permission_classes([HasPerm("manage_settings")])
def overview(request):
    return Response(_overview())


@api_view(["POST"])
@permission_classes([HasPerm("manage_settings")])
def send(request):
    """Send everything not yet accepted, for example after the internet comes back."""
    services.send_all()
    audit("evat_send_all", request.user, "evat")
    return Response(_overview())
