from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "jira_agent"

metadata = MetaData(schema=SCHEMA)


class Base(DeclarativeBase):
    metadata = metadata
