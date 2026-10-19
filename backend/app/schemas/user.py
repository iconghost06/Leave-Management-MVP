from pydantic import AliasPath, BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_code: str
    name: str
    email: str
    role: str
    manager_name: str | None = Field(default=None, validation_alias=AliasPath("manager", "name"))
