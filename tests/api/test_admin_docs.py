import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.document import Document

@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient, db: AsyncSession):
                                               
                                   
                                  
    pass

@pytest.mark.asyncio
async def test_retry_document(client: AsyncClient, db: AsyncSession):
                                   
                                                   
                    
    pass

@pytest.mark.asyncio
async def test_delete_document(client: AsyncClient, db: AsyncSession):
                            
                                               
                    
    pass
