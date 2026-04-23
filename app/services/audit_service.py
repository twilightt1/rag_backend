import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.admin_audit import AdminActionLog

class AuditService:
    @staticmethod
    async def log_action(
        db: AsyncSession,
        admin_id: uuid.UUID,
        action: str,
        target_entity_type: str,
        target_entity_id: uuid.UUID,
        changes: dict[str, Any] | None = None,
    ) -> AdminActionLog:
        """
        Logs an administrative action to the database.

        Args:
            db: AsyncSession
            admin_id: UUID of the admin performing the action
            action: String describing the action (e.g., 'deactivate_user', 'update_setting')
            target_entity_type: String type of the entity affected (e.g., 'user', 'document', 'system_setting')
            target_entity_id: UUID of the entity affected
            changes: Optional dict describing what changed
        """
        log_entry = AdminActionLog(
            admin_id=admin_id,
            action=action,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            changes=changes or {}
        )
        db.add(log_entry)
        # We don't commit here, we let the route handler commit the transaction
        return log_entry
