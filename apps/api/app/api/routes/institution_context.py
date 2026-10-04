"""Read-only, authenticated student institution presentation context."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.auth import CurrentUser, get_current_user
from app.institution_context import InstitutionProviderRegistry, ProviderUnavailable
from app.services.student import StudentService

router = APIRouter(prefix="/api/v1/me", tags=["institution-context"])


@router.get("/institution-context")
async def current_institution(user: Annotated[CurrentUser, Depends(get_current_user)],
                              request: Request, response: Response):
    service: StudentService | None = getattr(request.app.state, "student_service", None)
    registry: InstitutionProviderRegistry | None = getattr(request.app.state, "institution_registry", None)
    if service is None or registry is None:
        raise HTTPException(503, "INSTITUTION_CONTEXT_UNAVAILABLE")
    # Never accept an institution ID from query, body, JWT claims, or prompt text.
    institution_id = await service.resolve_student_university_id(user.user_id)
    try:
        bundle = registry.resolve(institution_id)
    except ProviderUnavailable:
        raise HTTPException(503, "INSTITUTION_CONTEXT_UNAVAILABLE") from None
    if bundle.config.context.status != "ACTIVE":
        raise HTTPException(503, "INSTITUTION_CONTEXT_UNAVAILABLE")
    response.headers["Cache-Control"] = "private, no-store"
    return bundle.config.public_view()
