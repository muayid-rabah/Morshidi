from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
from typing import Any
from uuid import UUID

import httpx

from app.core.config import settings
from app.offerings.models import MeetingBlock, Modality, OfferingSection, OfferingSnapshot, SourceType
from app.offerings.provider import CourseOfferingProvider, OfferingProviderUnavailable


class UniversityContractClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    def _configured(self) -> tuple[str, str]:
        base = (settings.uni_base_url or "").rstrip("/")
        key = settings.uni_service_key.get_secret_value() if settings.uni_service_key else ""
        if not base or not key:
            raise OfferingProviderUnavailable("University source is not configured")
        return base, key

    async def get_json(self, path: str) -> Any:
        base, key = self._configured()
        try:
            response = await self._client.get(
                f"{base}{path}", headers={"X-Uni-Api-Key": key, "Accept": "application/json"}, timeout=5
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise OfferingProviderUnavailable("University source is unavailable") from error

    async def load_student(self, student_id: str) -> dict[str, Any]:
        return await self.get_json(f"/v1/integration/students/{student_id}")

    async def current_term(self) -> dict[str, Any]:
        return await self.get_json("/v1/calendar")

    async def manifest(self) -> dict[str, Any]:
        result = await self.get_json("/v1/manifest")
        return result if isinstance(result, dict) else {}

    async def live_offerings(self, term_code: str) -> list[dict[str, Any]]:
        result = await self.get_json(f"/v1/offerings?term={term_code}")
        if not isinstance(result, list):
            raise OfferingProviderUnavailable("University contract returned invalid offerings")
        return result

    async def resolve_period(self, period_id: str, term_code: str) -> dict[str, Any] | None:
        if not settings.supabase_url or not settings.supabase_secret_key or not settings.uni_university_id:
            raise OfferingProviderUnavailable("University period mapping is not configured")
        try:
            UUID(period_id)
            UUID(settings.uni_university_id)
        except ValueError as error:
            raise OfferingProviderUnavailable("University period mapping is invalid") from error
        url = f"{settings.supabase_url.rstrip('/')}/rest/v1/mock_registration_target_periods"
        params = {
            "select": "id,period_key,source_version,provider_namespace,period_class",
            "id": f"eq.{period_id}", "university_id": f"eq.{settings.uni_university_id}",
            "period_key": f"eq.{term_code}", "is_expired": "eq.false", "limit": "1",
        }
        try:
            response = await self._client.get(url, params=params, headers={
                "apikey": settings.supabase_secret_key.get_secret_value(),
                "Authorization": f"Bearer {settings.supabase_secret_key.get_secret_value()}",
                "Accept": "application/json",
            }, timeout=5)
            response.raise_for_status()
            rows = response.json()
            return rows[0] if isinstance(rows, list) and rows else None
        except (httpx.HTTPError, ValueError) as error:
            raise OfferingProviderUnavailable("University period mapping is unavailable") from error

    async def find_period(self, term_code: str) -> dict[str, Any] | None:
        if not settings.supabase_url or not settings.supabase_secret_key or not settings.uni_university_id:
            raise OfferingProviderUnavailable("University period mapping is not configured")
        url = f"{settings.supabase_url.rstrip('/')}/rest/v1/mock_registration_target_periods"
        try:
            response = await self._client.get(url, params={
                "select": "id,period_key,source_version,provider_namespace,period_class",
                "university_id": f"eq.{settings.uni_university_id}", "period_key": f"eq.{term_code}",
                "is_expired": "eq.false", "limit": "2",
            }, headers={
                "apikey": settings.supabase_secret_key.get_secret_value(),
                "Authorization": f"Bearer {settings.supabase_secret_key.get_secret_value()}",
                "Accept": "application/json",
            }, timeout=5)
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list) or len(rows) != 1:
                return None
            return rows[0]
        except (httpx.HTTPError, ValueError) as error:
            raise OfferingProviderUnavailable("University period mapping is unavailable") from error


ARABIC_DAY_TO_ISO = {"الأحد": 7, "الاثنين": 1, "الثلاثاء": 2, "الأربعاء": 3, "الخميس": 4}


def _time(value: str) -> time:
    hour, minute = (int(part) for part in value.split(":", 1))
    return time(hour, minute)


class HttpUniversityOfferingProvider(CourseOfferingProvider):
    def __init__(self, contract: UniversityContractClient, university_id: str) -> None:
        self.contract = contract
        self.university_id = university_id

    async def load_snapshot(self, university_id: str, period_key: str) -> OfferingSnapshot | None:
        if university_id != self.university_id:
            return None
        try:
            calendar = await self.contract.current_term()
            manifest = await self.contract.manifest()
            term = calendar["currentTerm"]
            period = await self.contract.resolve_period(period_key, str(term["code"]))
            if period is None:
                return None
            raw = await self.contract.live_offerings(str(term["code"]))
            now = datetime.now(timezone.utc)
            sections: list[OfferingSection] = []
            for item in raw:
                days = item.get("days_array") if isinstance(item.get("days_array"), list) else []
                meetings = tuple(MeetingBlock(
                    day=ARABIC_DAY_TO_ISO[day], starts_at=_time(str(item["start_time"])),
                    ends_at=_time(str(item["end_time"])), timezone="Asia/Amman",
                ) for day in days if day in ARABIC_DAY_TO_ISO)
                capacity = int(item["capacity"]) if item.get("capacity") is not None else None
                enrolled = int(item["enrolled"]) if item.get("enrolled") is not None else None
                sections.append(OfferingSection(
                    section_id=str(item["id"]), course_code=str(item["course_code"]),
                    status=str(item.get("status") or "UNKNOWN"), modality=Modality.UNKNOWN,
                    campus=None, location=str(item.get("room") or "") or None, meetings=meetings,
                    capacity=capacity, enrolled=enrolled,
                    available=max(0, capacity - enrolled) if capacity is not None and enrolled is not None else None,
                    waitlist=None, provenance="MORSHIDI_UNIVERSITY_HTTP_CONTRACT",
                    student_visible=str(item.get("status", "")).lower() not in {"مغلقة", "closed"},
                ))
            version = str(max((int(item.get("version", 0)) for item in raw), default=0))
            snapshot_hash = sha256(f"{term['code']}:{version}".encode()).hexdigest()[:24]
            is_synthetic = manifest.get("synthetic") is True
            provenance = "MORSHIDI_UNIVERSITY_HTTP_CONTRACT / SYNTHETIC" if is_synthetic else "MORSHIDI_UNIVERSITY_HTTP_CONTRACT"
            return OfferingSnapshot(
                university_id=university_id, period_key=period_key,
                snapshot_id=f"uni-{snapshot_hash}", source_version=f"{term['code']}:{version}",
                source_type=SourceType.SYNTHETIC if is_synthetic else SourceType.INSTITUTIONAL,
                source_at=now, fresh_until=now + timedelta(seconds=60),
                complete=True, sections=tuple(sections), provenance=provenance,
            )
        except (OfferingProviderUnavailable, KeyError, TypeError, ValueError) as error:
            raise OfferingProviderUnavailable("University offering contract unavailable or invalid") from error
