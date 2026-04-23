from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from app.database import get_db
from app.utils.dependencies import require_admin
from app.models.user import User
from app.services.settings_service import SettingsService
from app.services.audit_service import AuditService

router = APIRouter(prefix="/admin/settings", tags=["admin_settings"])


class SettingResponse(BaseModel):
    key:         str
    value:       Any
    description: str | None


class SettingCreateUpdate(BaseModel):
    value:       Any
    description: str | None = None


@router.get("", response_model=list[SettingResponse])
async def list_settings(
    skip: int = 0,
    limit: int = 50,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    settings = await SettingsService.list_settings(db, skip=skip, limit=limit)
    return [
        SettingResponse(
            key=s.key,
            value=s.value,
            description=s.description
        ) for s in settings
    ]


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    val = await SettingsService.get_setting(db, key)
    if val is None:
        raise HTTPException(404, detail="Setting not found.")

                                                                                
                                                                       
    description = None
    if key in SettingsService.DEFAULTS:
        description = SettingsService.DEFAULTS[key].get("description")

    return SettingResponse(
        key=key,
        value=val,
        description=description
    )


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    body: SettingCreateUpdate,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    old_val = await SettingsService.get_setting(db, key)

    changes = {
        "value": {"old": old_val, "new": body.value}
    }

    if body.description is not None:
        changes["description"] = {"new": body.description}

    setting = await SettingsService.set_setting(
        db=db,
        key=key,
        value=body.value,
        description=body.description
    )

    await AuditService.log_action(
        db=db,
        admin_id=admin_user.id,
        action="update_setting",
        target_entity_type="system_setting",
        target_entity_id=setting.id,
        changes=changes
    )

    await db.commit()
    await db.refresh(setting)

    return SettingResponse(
        key=setting.key,
        value=setting.value,
        description=setting.description
    )


@router.delete("/{key}", status_code=200)
async def delete_setting(
    key: str,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    deleted = await SettingsService.delete_setting(db, key)
    if not deleted:
        raise HTTPException(404, detail="Setting not found.")

    await AuditService.log_action(
        db=db,
        admin_id=admin_user.id,
        action="delete_setting",
        target_entity_type="system_setting",
        target_entity_id=admin_user.id,                                                                 
        changes={"key": key}
    )

    await db.commit()
    return {"message": "Setting deleted successfully."}
