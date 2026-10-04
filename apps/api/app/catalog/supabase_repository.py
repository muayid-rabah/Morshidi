"""Supabase Data API adapter that maps catalog rows to pure rules models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import logging
from time import perf_counter
from typing import Any
from uuid import UUID

import httpx

from app.core.request_timing import request_id_context
from app.advisor.models import ResolvedCourseReference
from app.catalog.roadmap_metadata import RoadmapPlanMetadata
from app.catalog.display import CourseDisplayIdentity
from app.catalog.errors import (
    CatalogIntegrityError,
    CatalogTransportError,
    StudyPlanNotFound,
    TargetCourseNotFound,
    TargetCourseNotInStudyPlan,
)
from app.rules.models import (
    CanTakeCatalog,
    CourseCatalogStatus,
    CourseIdentity,
    DependencyGroup,
    DependencyType,
    PlanCourseRule,
    PrerequisiteLogicStatus,
)
from app.progress.models import (
    AcademicProgressCatalog,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
)


class SupabaseAcademicCatalogRepository:
    """Read-only server-side adapter for the accepted academic catalog.

    ``server_key`` is used only as the Data API ``apikey`` credential.  It is
    deliberately never included in exception messages or stored in models.
    """

    def __init__(
        self,
        supabase_url: str,
        server_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not supabase_url.strip():
            raise ValueError("supabase_url must not be empty")
        if not server_key.strip():
            raise ValueError("server_key must not be empty")
        self._rest_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._server_key = server_key
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None

    async def close(self) -> None:
        """Close only a client created by this repository."""

        if self._owns_client:
            await self._client.aclose()

    async def load_university_course_identities(
        self, university_id: UUID | str,
    ) -> tuple[CourseDisplayIdentity, ...]:
        scope = str(UUID(str(university_id)))
        identities: list[CourseDisplayIdentity] = []
        for offset in range(0, 10000, 500):
            rows = await self._get_rows("courses", {
                "select": "id,course_code,name_ar,name_en,university_id",
                "university_id": f"eq.{scope}", "order": "id.asc",
                "limit": "500", "offset": str(offset),
            })
            for row in rows:
                if _required_text(row, "university_id", "course") != scope:
                    raise CatalogIntegrityError("Display course belongs to another university")
                names = tuple(row.get(key) for key in ("name_ar", "name_en"))
                if any(value is not None and not isinstance(value, str) for value in names):
                    raise CatalogIntegrityError("Invalid course display name")
                identities.append(CourseDisplayIdentity(
                    _required_text(row, "id", "course"),
                    _required_text(row, "course_code", "course"),
                    names[0].strip() or None if names[0] is not None else None,
                    names[1].strip() or None if names[1] is not None else None,
                ))
            if len(rows) < 500:
                if (len({item.course_id for item in identities}) != len(identities) or
                        len({item.course_code for item in identities}) != len(identities)):
                    raise CatalogIntegrityError("Ambiguous course display identities")
                return tuple(identities)
        raise CatalogIntegrityError("Course display catalog exceeds bounded size")

    async def load_target_rules(
        self,
        study_plan_id: UUID | str,
        target_course_code: str,
    ) -> CanTakeCatalog:
        """Resolve one plan target and map persisted dependency rows exactly."""

        plan_id = str(study_plan_id)
        plan = await self._load_study_plan(plan_id)
        university_id = self._university_id(plan)

        course_rows = await self._get_rows(
            "courses",
            {
                "select": "id,course_code,name_ar,catalog_status,university_id",
                "university_id": f"eq.{university_id}",
                "course_code": f"eq.{target_course_code}",
            },
        )
        if not course_rows:
            raise TargetCourseNotFound(
                "Target course code was not found in the study plan university"
            )
        if len(course_rows) != 1:
            raise CatalogIntegrityError("Multiple catalog courses matched one university code")
        target_course = course_rows[0]
        target_course_id = _required_text(target_course, "id", "course")
        self._course_identity(target_course)

        plan_course_rows = await self._get_rows(
            "study_plan_courses",
            {
                "select": "id,prerequisite_logic_status,raw_prerequisite_text",
                "study_plan_id": f"eq.{plan_id}",
                "course_id": f"eq.{target_course_id}",
            },
        )
        if not plan_course_rows:
            raise TargetCourseNotInStudyPlan(
                "Target course is not a member of the requested study plan"
            )
        if len(plan_course_rows) != 1:
            raise CatalogIntegrityError("Multiple study-plan memberships matched one target")
        plan_course = plan_course_rows[0]
        plan_course_id = _required_text(plan_course, "id", "study_plan_course")
        status = _enum_value(
            PrerequisiteLogicStatus,
            _required_text(plan_course, "prerequisite_logic_status", "study_plan_course"),
            "prerequisite_logic_status",
        )

        groups = await self._load_groups(plan_course_id)
        if status is PrerequisiteLogicStatus.NOT_APPLICABLE:
            if groups:
                raise CatalogIntegrityError("not_applicable target has dependency groups")
            dependency_groups: tuple[DependencyGroup, ...] = ()
            course_identities = (self._course_identity(target_course),)
        elif status in (
            PrerequisiteLogicStatus.UNRESOLVED,
            PrerequisiteLogicStatus.SOURCE_CONFLICT,
        ):
            if groups:
                raise CatalogIntegrityError("non-executable target has dependency groups")
            dependency_groups = ()
            course_identities = (self._course_identity(target_course),)
        else:
            if not groups:
                raise CatalogIntegrityError("verified target has no dependency group representation")
            dependency_groups, option_identities = await self._load_verified_dependencies(
                groups,
                university_id,
            )
            course_identities = _sorted_unique_course_identities(
                (self._course_identity(target_course), *option_identities)
            )

        raw_text = plan_course.get("raw_prerequisite_text")
        if raw_text is not None and not isinstance(raw_text, str):
            raise CatalogIntegrityError("raw_prerequisite_text is not text")
        target_name_ar = target_course.get("name_ar")
        if target_name_ar is not None and not isinstance(target_name_ar, str):
            raise CatalogIntegrityError("course name_ar is not text")
        target_code = _required_text(target_course, "course_code", "course")
        if target_code != target_course_code:
            raise CatalogIntegrityError("course response did not match requested target code")

        return CanTakeCatalog(
            study_plan_id=plan_id,
            plan_courses=(
                PlanCourseRule(
                    course_code=target_code,
                    prerequisite_logic_status=status,
                    dependency_groups=dependency_groups,
                    raw_prerequisite_text=raw_text,
                    target_name_ar=target_name_ar,
                ),
            ),
            courses=course_identities,
        )

    async def load_progress_catalog(
        self,
        study_plan_id: UUID | str,
    ) -> AcademicProgressCatalog:
        """Load the persisted plan, groups, and only its actual course members."""

        plan_id = str(study_plan_id)
        plan_rows = await self._get_rows(
            "study_plans",
            {"select": "id,total_credit_hours", "id": f"eq.{plan_id}"},
        )
        if not plan_rows:
            raise StudyPlanNotFound("Study plan was not found")
        if len(plan_rows) != 1:
            raise CatalogIntegrityError("Multiple study plans matched one identifier")
        plan_row = plan_rows[0]
        if _required_text(plan_row, "id", "study_plan") != plan_id:
            raise CatalogIntegrityError("Study plan response did not match requested identifier")

        group_rows = await self._get_rows(
            "requirement_groups",
            {
                "select": (
                    "id,study_plan_id,group_code,name_ar,name_en,scope,"
                    "requirement_type,required_credit_hours,display_order"
                ),
                "study_plan_id": f"eq.{plan_id}",
                "order": "display_order.asc,group_code.asc",
            },
        )
        groups = tuple(_progress_group(row) for row in group_rows)

        plan_course_rows = await self._get_rows(
            "study_plan_courses",
            {
                "select": (
                    "id,study_plan_id,requirement_group_id,credit_hours,display_order,"
                    "courses(course_code,name_ar,name_en,catalog_status)"
                ),
                "study_plan_id": f"eq.{plan_id}",
                "order": "display_order.asc,id.asc",
            },
        )
        plan_courses = tuple(_progress_plan_course(row) for row in plan_course_rows)
        return AcademicProgressCatalog(
            study_plan=ProgressStudyPlan(
                study_plan_id=plan_id,
                total_credit_hours=_required_decimal(plan_row, "total_credit_hours", "study_plan"),
            ),
            requirement_groups=groups,
            plan_courses=plan_courses,
        )

    async def load_roadmap_plan_metadata(self, study_plan_id: UUID | str) -> RoadmapPlanMetadata:
        plan_id = str(study_plan_id)
        rows = await self._get_rows(
            "study_plans",
            {"select": (
                "id,plan_number,effective_year,updated_at,"
                "academic_sources(source_type,retrieved_at,content_hash,snapshot_ref,source_status)"
            ), "id": f"eq.{plan_id}"},
        )
        if not rows:
            raise StudyPlanNotFound("Study plan was not found")
        if len(rows) != 1 or _required_text(rows[0], "id", "study_plan") != plan_id:
            raise CatalogIntegrityError("Roadmap plan metadata did not match requested plan")
        row = rows[0]
        year = row.get("effective_year")
        if year is not None and (isinstance(year, bool) or not isinstance(year, int)):
            raise CatalogIntegrityError("Roadmap effective year is not valid")
        source = row.get("academic_sources")
        if source is not None and not isinstance(source, Mapping):
            raise CatalogIntegrityError("Roadmap plan source is not valid")
        source = source or {}
        for field in ("source_type", "retrieved_at", "content_hash", "snapshot_ref", "source_status"):
            if source.get(field) is not None and not isinstance(source[field], str):
                raise CatalogIntegrityError("Roadmap plan source field is not valid")
        return RoadmapPlanMetadata(
            plan_id, _required_text(row, "plan_number", "study_plan"), year,
            _required_text(row, "updated_at", "study_plan"),
            source.get("source_type"), source.get("retrieved_at"), source.get("content_hash"),
            source.get("snapshot_ref"), source.get("source_status"),
        )

    async def load_advisor_course_catalog(
        self,
        study_plan_id: UUID | str,
    ) -> tuple[ResolvedCourseReference, ...]:
        """Load only canonical course identities in the requested study plan."""

        plan_id = str(study_plan_id)
        plan = await self._load_study_plan(plan_id)
        university_id = self._university_id(plan)
        rows = await self._get_rows(
            "study_plan_courses",
            {
                "select": "id,study_plan_id,courses(course_code,name_ar,name_en,university_id)",
                "study_plan_id": f"eq.{plan_id}",
                "order": "id.asc",
            },
        )
        resolved: list[ResolvedCourseReference] = []
        for row in rows:
            _required_text(row, "id", "study_plan_course")
            if _required_text(row, "study_plan_id", "study_plan_course") != plan_id:
                raise CatalogIntegrityError("Plan course belongs to another study plan")
            course = row.get("courses")
            if not isinstance(course, Mapping):
                raise CatalogIntegrityError("Plan course is missing its course relationship")
            if _required_text(course, "university_id", "course") != university_id:
                raise CatalogIntegrityError("Plan course belongs to another university")
            name_ar = _required_text(course, "name_ar", "course")
            if not name_ar.strip():
                raise CatalogIntegrityError("course name_ar is blank")
            name_en = course.get("name_en")
            if name_en is not None and (not isinstance(name_en, str) or not name_en.strip()):
                raise CatalogIntegrityError("course name_en is not valid text")
            resolved.append(
                ResolvedCourseReference(
                    course_code=_required_text(course, "course_code", "course"),
                    canonical_arabic_name=name_ar,
                    canonical_english_name=name_en,
                )
            )
        ordered = tuple(sorted(resolved, key=lambda item: item.course_code))
        if len({item.course_code for item in ordered}) != len(ordered):
            raise CatalogIntegrityError("Plan catalog contains duplicate course codes")
        return ordered

    async def load_plan_eligibility_catalog(
        self,
        study_plan_id: UUID | str,
    ) -> CanTakeCatalog:
        """Load all plan-course rules and dependency identities for in-memory simulation."""

        plan_id = str(study_plan_id)
        plan = await self._load_study_plan(plan_id)
        university_id = self._university_id(plan)

        plan_course_rows = await self._get_rows(
            "study_plan_courses",
            {
                "select": (
                    "id,prerequisite_logic_status,raw_prerequisite_text,display_order,credit_hours,"
                    "courses(id,course_code,name_ar,name_en,catalog_status,university_id)"
                ),
                "study_plan_id": f"eq.{plan_id}",
                "order": "display_order.asc,id.asc",
            },
        )
        if not plan_course_rows:
            return CanTakeCatalog(study_plan_id=plan_id, plan_courses=(), courses=())

        plan_course_ids = [
            _required_text(row, "id", "study_plan_course") for row in plan_course_rows
        ]

        # Load dependency groups in chunks to keep query string lengths safe
        group_rows: list[Mapping[str, Any]] = []
        chunk_size = 50
        for i in range(0, len(plan_course_ids), chunk_size):
            chunk = plan_course_ids[i : i + chunk_size]
            rows = await self._get_rows(
                "course_dependency_groups",
                {
                    "select": "id,study_plan_course_id,dependency_type,group_number",
                    "study_plan_course_id": f"in.({','.join(chunk)})",
                },
            )
            group_rows.extend(rows)

        # Load dependency options if any groups exist
        group_ids = [_required_text(row, "id", "dependency group") for row in group_rows]
        options_by_group: dict[str, list[CourseIdentity]] = {gid: [] for gid in group_ids}
        option_identities: list[CourseIdentity] = []
        if group_ids:
            for i in range(0, len(group_ids), chunk_size):
                chunk = group_ids[i : i + chunk_size]
                option_rows = await self._get_rows(
                    "course_dependency_options",
                    {
                        "select": "dependency_group_id,courses(course_code,catalog_status,university_id)",
                        "dependency_group_id": f"in.({','.join(chunk)})",
                    },
                )
                for row in option_rows:
                    gid = _required_text(row, "dependency_group_id", "dependency option")
                    if gid not in options_by_group:
                        raise CatalogIntegrityError("Dependency option belongs to an unexpected group")
                    nested_course = row.get("courses")
                    if not isinstance(nested_course, Mapping):
                        raise CatalogIntegrityError("Dependency option is missing its referenced course")
                    opt_univ = _required_text(nested_course, "university_id", "dependency course")
                    if opt_univ != university_id:
                        raise CatalogIntegrityError("Dependency course belongs to another university")
                    identity = self._course_identity(nested_course)
                    options_by_group[gid].append(identity)
                    option_identities.append(identity)

        mapping_started = perf_counter()
        # Index groups by study_plan_course_id
        groups_by_pc: dict[str, list[Mapping[str, Any]]] = {pid: [] for pid in plan_course_ids}
        for grow in group_rows:
            spc_id = _required_text(grow, "study_plan_course_id", "dependency group")
            if spc_id not in groups_by_pc:
                raise CatalogIntegrityError("Dependency group belongs to an unexpected study plan course")
            groups_by_pc[spc_id].append(grow)

        # Build plan course rules
        plan_rules: list[PlanCourseRule] = []
        plan_course_identities: list[CourseIdentity] = []

        for row in plan_course_rows:
            pc_id = _required_text(row, "id", "study_plan_course")
            nested_course = row.get("courses")
            if not isinstance(nested_course, Mapping):
                raise CatalogIntegrityError("Plan course is missing its course relationship")
            course_univ = _required_text(nested_course, "university_id", "course")
            if course_univ != university_id:
                raise CatalogIntegrityError("Plan course belongs to another university")
            course_code = _required_text(nested_course, "course_code", "course")
            target_identity = self._course_identity(nested_course)
            plan_course_identities.append(target_identity)

            status = _enum_value(
                PrerequisiteLogicStatus,
                _required_text(row, "prerequisite_logic_status", "study_plan_course"),
                "prerequisite_logic_status",
            )
            raw_text = row.get("raw_prerequisite_text")
            if raw_text is not None and not isinstance(raw_text, str):
                raise CatalogIntegrityError("raw_prerequisite_text is not text")
            name_ar = nested_course.get("name_ar")
            if name_ar is not None and not isinstance(name_ar, str):
                raise CatalogIntegrityError("course name_ar is not text")
            name_en = nested_course.get("name_en")
            if name_en is not None and not isinstance(name_en, str):
                raise CatalogIntegrityError("course name_en is not text")

            pc_groups = groups_by_pc[pc_id]
            if status is PrerequisiteLogicStatus.NOT_APPLICABLE:
                if pc_groups:
                    raise CatalogIntegrityError("not_applicable target has dependency groups")
                dep_groups: tuple[DependencyGroup, ...] = ()
            elif status in (
                PrerequisiteLogicStatus.UNRESOLVED,
                PrerequisiteLogicStatus.SOURCE_CONFLICT,
            ):
                if pc_groups:
                    raise CatalogIntegrityError("non-executable target has dependency groups")
                dep_groups = ()
            else:
                if not pc_groups:
                    raise CatalogIntegrityError("verified target has no dependency group representation")
                normalized_groups: list[tuple[str, DependencyType, int]] = []
                group_numbers: set[int] = set()
                for grow in pc_groups:
                    gid = _required_text(grow, "id", "dependency group")
                    dep_type = _enum_value(
                        DependencyType,
                        _required_text(grow, "dependency_type", "dependency group"),
                        "dependency_type",
                    )
                    number = _required_positive_int(grow, "group_number", "dependency group")
                    if number in group_numbers:
                        raise CatalogIntegrityError("Duplicate dependency group_number in target")
                    group_numbers.add(number)
                    normalized_groups.append((gid, dep_type, number))

                result_groups: list[DependencyGroup] = []
                for gid, dep_type, group_number in sorted(normalized_groups, key=lambda item: item[2]):
                    identities = options_by_group[gid]
                    if not identities:
                        raise CatalogIntegrityError("Dependency group has no options")
                    codes = [identity.course_code for identity in identities]
                    if len(codes) != len(set(codes)):
                        raise CatalogIntegrityError("Dependency group has duplicate option courses")
                    ordered_codes = tuple(sorted(codes))
                    result_groups.append(
                        DependencyGroup(
                            group_number=group_number,
                            dependency_type=dep_type,
                            option_course_codes=ordered_codes,
                        )
                    )
                dep_groups = tuple(result_groups)

            plan_rules.append(
                PlanCourseRule(
                    course_code=course_code,
                    prerequisite_logic_status=status,
                    dependency_groups=dep_groups,
                    raw_prerequisite_text=raw_text,
                    target_name_ar=name_ar,
                    target_name_en=name_en,
                    credit_hours=_required_decimal(row, "credit_hours", "study_plan_course"),
                )
            )

        all_identities = _sorted_unique_course_identities(
            (*plan_course_identities, *option_identities)
        )
        logging.getLogger("uvicorn.error").info(
            "degree_path_phase request_id=%s phase=prerequisite_graph_creation_ms value=%.1f",
            request_id_context.get(), (perf_counter() - mapping_started) * 1000,
        )
        return CanTakeCatalog(
            study_plan_id=plan_id,
            plan_courses=tuple(plan_rules),
            courses=all_identities,
            complete_plan_credits=True,
        )

    async def _load_study_plan(self, plan_id: str) -> Mapping[str, Any]:
        rows = await self._get_rows(
            "study_plans",
            {
                "select": "id,majors(faculties(university_id))",
                "id": f"eq.{plan_id}",
            },
        )
        if not rows:
            raise StudyPlanNotFound("Study plan was not found")
        if len(rows) != 1:
            raise CatalogIntegrityError("Multiple study plans matched one identifier")
        return rows[0]

    async def _load_groups(self, plan_course_id: str) -> tuple[Mapping[str, Any], ...]:
        rows = await self._get_rows(
            "course_dependency_groups",
            {
                "select": "id,dependency_type,group_number",
                "study_plan_course_id": f"eq.{plan_course_id}",
            },
        )
        return tuple(rows)

    async def _load_verified_dependencies(
        self,
        groups: Sequence[Mapping[str, Any]],
        university_id: str,
    ) -> tuple[tuple[DependencyGroup, ...], tuple[CourseIdentity, ...]]:
        normalized_groups: list[tuple[str, DependencyType, int]] = []
        group_numbers: set[int] = set()
        for row in groups:
            group_id = _required_text(row, "id", "dependency group")
            dependency_type = _enum_value(
                DependencyType,
                _required_text(row, "dependency_type", "dependency group"),
                "dependency_type",
            )
            number = _required_positive_int(row, "group_number", "dependency group")
            if number in group_numbers:
                raise CatalogIntegrityError("Duplicate dependency group_number in target")
            group_numbers.add(number)
            normalized_groups.append((group_id, dependency_type, number))

        group_ids = [group_id for group_id, _, _ in normalized_groups]
        option_rows = await self._get_rows(
            "course_dependency_options",
            {
                "select": "dependency_group_id,courses(course_code,catalog_status,university_id)",
                "dependency_group_id": f"in.({','.join(group_ids)})",
            },
        )
        options_by_group: dict[str, list[CourseIdentity]] = {group_id: [] for group_id in group_ids}
        for row in option_rows:
            group_id = _required_text(row, "dependency_group_id", "dependency option")
            if group_id not in options_by_group:
                raise CatalogIntegrityError("Dependency option belongs to an unexpected group")
            nested_course = row.get("courses")
            if not isinstance(nested_course, Mapping):
                raise CatalogIntegrityError("Dependency option is missing its referenced course")
            option_university_id = _required_text(nested_course, "university_id", "dependency course")
            if option_university_id != university_id:
                raise CatalogIntegrityError("Dependency course belongs to another university")
            options_by_group[group_id].append(self._course_identity(nested_course))

        result_groups: list[DependencyGroup] = []
        all_identities: list[CourseIdentity] = []
        for group_id, dependency_type, group_number in sorted(
            normalized_groups,
            key=lambda item: item[2],
        ):
            identities = options_by_group[group_id]
            if not identities:
                raise CatalogIntegrityError("Dependency group has no options")
            codes = [identity.course_code for identity in identities]
            if len(codes) != len(set(codes)):
                raise CatalogIntegrityError("Dependency group has duplicate option courses")
            ordered = tuple(sorted(identities, key=lambda identity: identity.course_code))
            result_groups.append(
                DependencyGroup(
                    group_number=group_number,
                    dependency_type=dependency_type,
                    option_course_codes=tuple(identity.course_code for identity in ordered),
                )
            )
            all_identities.extend(ordered)
        return tuple(result_groups), tuple(all_identities)

    async def _get_rows(
        self,
        resource: str,
        params: Mapping[str, str],
    ) -> list[Mapping[str, Any]]:
        try:
            response = await self._client.get(
                f"{self._rest_url}/{resource}",
                params=params,
                headers={
                    "apikey": self._server_key,
                    "Authorization": f"Bearer {self._server_key}",
                    "Accept": "application/json",
                },
            )
        except (httpx.TimeoutException, httpx.RequestError) as error:
            raise CatalogTransportError("GET", resource) from error
        if not 200 <= response.status_code < 300:
            raise CatalogTransportError("GET", resource, status_code=response.status_code)
        try:
            body = response.json()
        except ValueError as error:
            raise CatalogTransportError("decode response", resource) from error
        if not isinstance(body, list) or not all(isinstance(row, Mapping) for row in body):
            raise CatalogIntegrityError(f"{resource} response is not a row array")
        return list(body)

    @staticmethod
    def _university_id(plan: Mapping[str, Any]) -> str:
        majors = plan.get("majors")
        if not isinstance(majors, Mapping):
            raise CatalogIntegrityError("Study plan is missing its major relationship")
        faculties = majors.get("faculties")
        if not isinstance(faculties, Mapping):
            raise CatalogIntegrityError("Study plan is missing its faculty relationship")
        return _required_text(faculties, "university_id", "faculty")

    @staticmethod
    def _course_identity(row: Mapping[str, Any]) -> CourseIdentity:
        return CourseIdentity(
            course_code=_required_text(row, "course_code", "course"),
            catalog_status=_enum_value(
                CourseCatalogStatus,
                _required_text(row, "catalog_status", "course"),
                "catalog_status",
            ),
        )


def _required_text(row: Mapping[str, Any], field: str, resource: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise CatalogIntegrityError(f"{resource} is missing required {field}")
    return value


def _required_positive_int(row: Mapping[str, Any], field: str, resource: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CatalogIntegrityError(f"{resource} has invalid {field}")
    return value


def _required_nonnegative_int(row: Mapping[str, Any], field: str, resource: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CatalogIntegrityError(f"{resource} has invalid {field}")
    return value


def _required_decimal(row: Mapping[str, Any], field: str, resource: str):
    from decimal import Decimal, InvalidOperation

    value = row.get(field)
    if isinstance(value, bool) or value is None:
        raise CatalogIntegrityError(f"{resource} has invalid {field}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise CatalogIntegrityError(f"{resource} has invalid {field}") from error
    if not result.is_finite() or result < 0:
        raise CatalogIntegrityError(f"{resource} has invalid {field}")
    return result


def _optional_text(row: Mapping[str, Any], field: str, resource: str) -> str | None:
    value = row.get(field)
    if value is not None and (not isinstance(value, str) or not value):
        raise CatalogIntegrityError(f"{resource} has invalid {field}")
    return value


def _progress_group(row: Mapping[str, Any]) -> ProgressRequirementGroup:
    return ProgressRequirementGroup(
        group_id=_required_text(row, "id", "requirement_group"),
        study_plan_id=_required_text(row, "study_plan_id", "requirement_group"),
        group_code=_required_text(row, "group_code", "requirement_group"),
        name_ar=_required_text(row, "name_ar", "requirement_group"),
        name_en=_optional_text(row, "name_en", "requirement_group"),
        scope=_required_text(row, "scope", "requirement_group"),
        requirement_type=_enum_value(
            RequirementType,
            _required_text(row, "requirement_type", "requirement_group"),
            "requirement_type",
        ),
        required_credit_hours=_required_decimal(
            row, "required_credit_hours", "requirement_group"
        ),
        display_order=_required_nonnegative_int(row, "display_order", "requirement_group"),
    )


def _progress_plan_course(row: Mapping[str, Any]) -> ProgressPlanCourse:
    nested_course = row.get("courses")
    if not isinstance(nested_course, Mapping):
        raise CatalogIntegrityError("Plan course is missing its course relationship")
    return ProgressPlanCourse(
        plan_course_id=_required_text(row, "id", "study_plan_course"),
        study_plan_id=_required_text(row, "study_plan_id", "study_plan_course"),
        requirement_group_id=_required_text(
            row, "requirement_group_id", "study_plan_course"
        ),
        course_code=_required_text(nested_course, "course_code", "course"),
        catalog_status=_enum_value(
            CourseCatalogStatus,
            _required_text(nested_course, "catalog_status", "course"),
            "catalog_status",
        ),
        credit_hours=_required_decimal(row, "credit_hours", "study_plan_course"),
        display_order=_required_nonnegative_int(row, "display_order", "study_plan_course"),
        course_name_ar=_optional_text(nested_course, "name_ar", "course"),
        course_name_en=_optional_text(nested_course, "name_en", "course"),
    )


def _enum_value(enum_type: type[Any], value: str, field: str) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        raise CatalogIntegrityError(f"Unsupported {field}: {value}") from error


def _sorted_unique_course_identities(
    identities: Sequence[CourseIdentity],
) -> tuple[CourseIdentity, ...]:
    by_code: dict[str, CourseIdentity] = {}
    for identity in identities:
        previous = by_code.setdefault(identity.course_code, identity)
        if previous != identity:
            raise CatalogIntegrityError("Course code has conflicting catalog identities")
    return tuple(sorted(by_code.values(), key=lambda identity: identity.course_code))
