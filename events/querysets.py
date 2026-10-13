from django.db.models import Count, F, Max, Min, Prefetch, Q, QuerySet, Sum
from django.utils import timezone

PUBLIC_STATUSES = ("published", "cancelled")
STAFF_TABS = ("upcoming", "past", "drafts", "cancelled", "archived")


class EventQuerySet(QuerySet):
    def with_dates(self):
        """Annotate start/end from positions, plus position count and total spots."""
        if "ends_at" in self.query.annotations:
            return self
        return self.annotate(
            starts_at=Min("positions__starts_at"),
            ends_at=Max("positions__ends_at"),
            position_count=Count("positions"),
            total_slots=Sum("positions__slots"),
        )

    def public(self):
        return self.filter(status__in=PUBLIC_STATUSES, archived_at__isnull=True)

    def upcoming(self, now=None):
        now = now or timezone.now()
        return self.with_dates().filter(ends_at__gte=now).order_by("starts_at", "pk")

    def past(self, now=None):
        now = now or timezone.now()
        return self.with_dates().filter(ends_at__lt=now).order_by("-starts_at", "-pk")

    def with_cover(self):
        from events.models import EventPhoto

        return self.prefetch_related(
            Prefetch("photos", queryset=EventPhoto.objects.order_by("position", "id"))
        )

    def featured(self, limit=3, now=None):
        upcoming = self.public().upcoming(now)
        pinned = upcoming.filter(pinned=True)
        return pinned if pinned.exists() else upcoming[:limit]

    def for_staff(self, tab, now=None):
        now = now or timezone.now()
        dated = self.with_dates()
        live = dated.filter(archived_at__isnull=True)
        if tab == "past":
            return live.filter(ends_at__lt=now).order_by("-starts_at", "-pk")
        if tab == "drafts":
            return live.filter(status="draft").order_by("-created_at", "-pk")
        if tab == "cancelled":
            return live.filter(status="cancelled").order_by(
                F("starts_at").desc(nulls_last=True), "-pk"
            )
        if tab == "archived":
            return dated.filter(archived_at__isnull=False).order_by("-archived_at", "-pk")
        # Upcoming, including drafts that have no positions (and so no dates) yet.
        return live.filter(Q(ends_at__gte=now) | Q(ends_at__isnull=True)).order_by(
            F("starts_at").asc(nulls_first=True), "pk"
        )
