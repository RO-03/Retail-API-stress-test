from pydantic import BaseModel

class ItemBase(BaseModel):
    id: str
    name: str
    color_tone: str
    price: float
    stock: int

# Schema for creating a new item
class ItemCreate(ItemBase):
    pass

# Schema for reading an item (includes ORM config)
class Item(ItemBase):
    class Config:
        from_attributes = True  # Allows Pydantic to read data from SQLAlchemy objects