import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings_service import SettingsService
from app.models.system_setting import SystemSetting

@pytest.fixture
def mock_redis():
    with patch("app.services.settings_service.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_redis_instance = AsyncMock()
        mock_get_redis.return_value = mock_redis_instance
        yield mock_redis_instance


@pytest.mark.asyncio
async def test_get_setting_fallback(mock_redis):
    mock_db = MagicMock(spec=AsyncSession)
    mock_db.scalar = AsyncMock(return_value=None)

                                     
    mock_redis.get.return_value = None

                                                    
    value = await SettingsService.get_setting(mock_db, "maintenance_mode")

                                     
    assert value is False

                              
    mock_redis.setex.assert_called_once_with(
        f"{SettingsService.CACHE_PREFIX}maintenance_mode",
        SettingsService.CACHE_TTL,
        json.dumps(False)
    )

@pytest.mark.asyncio
async def test_get_setting_cache_hit(mock_redis):
    mock_db = MagicMock(spec=AsyncSession)

                                               
    mock_redis.get.return_value = json.dumps(True)

    value = await SettingsService.get_setting(mock_db, "maintenance_mode")

    assert value is True
                                           
    mock_db.scalar.assert_not_called()
                                   
    mock_redis.setex.assert_not_called()
