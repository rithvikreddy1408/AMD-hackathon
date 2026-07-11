from typing import Optional, List
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship

class UserBase(SQLModel):
    email: str = Field(unique=True, index=True)
    is_active: bool = Field(default=True)

class User(UserBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hashed_password: str
    
    # Relationship to scenario runs
    scenario_runs: List["ScenarioRun"] = Relationship(back_populates="user")

class ScenarioRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    scenario_id: str = Field(index=True)
    status: str = Field(default="pending") # pending, running, completed, failed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    user_id: int = Field(foreign_key="user.id")
    user: User = Relationship(back_populates="scenario_runs")
