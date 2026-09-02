from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth import require_roles

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=schemas.AuditLogListResponse)
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    user_email: Optional[str] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "department_admin")),
):
    query = db.query(models.AuditLog)
    if action:
        query = query.filter(models.AuditLog.action == action)
    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)
    if user_email:
        query = query.filter(models.AuditLog.user_email == user_email)
    if user.role == models.UserRole.department_admin:
        # department admins only see their own actions
        query = query.filter(models.AuditLog.user_email == user.email)

    total = query.count()
    items = (
        query.order_by(models.AuditLog.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.AuditLogListResponse(total=total, page=page, page_size=page_size, items=items)
