from pydantic import BaseModel


class ErrorOut(BaseModel):
    """The shape of every error body (SPEC §9). Used to document responses in OpenAPI."""

    code: str
    message: str
