import pytest
import uuid
from unittest.mock import MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.admin_audit import AdminActionLog
from app.services.audit_service import AuditService

@pytest.mark.asyncio
async def test_log_action():
               
    admin_id = uuid.uuid4()
    target_id = uuid.uuid4()
    action = "test_action"
    target_type = "test_entity"
    changes = {"old": "value", "new": "value2"}

                     
    mock_db = MagicMock(spec=AsyncSession)

                      
    log_entry = await AuditService.log_action(
        db=mock_db,
        admin_id=admin_id,
        action=action,
        target_entity_type=target_type,
        target_entity_id=target_id,
        changes=changes
    )

                                
    assert log_entry.admin_id == admin_id
    assert log_entry.action == action
    assert log_entry.target_entity_type == target_type
    assert log_entry.target_entity_id == target_id
    assert log_entry.changes == changes

                              
    mock_db.add.assert_called_once_with(log_entry)
