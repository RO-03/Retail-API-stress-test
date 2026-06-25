from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str


class ItemCreate(BaseModel):
    name: str
    price: float
    stock: int


class ItemUpdate(BaseModel):
    price: float | None = None
    stock_add: int | None = None  # For restocking
