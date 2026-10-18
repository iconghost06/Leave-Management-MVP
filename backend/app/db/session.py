from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)

# expire_on_commit=False keeps attributes readable after commit(), so the router
# can build the response without a lazy reload (DESIGN §1.1).
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
