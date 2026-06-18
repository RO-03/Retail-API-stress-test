from sqlalchemy import Column, Integer, String, Float
from database import Base

class DBItem(Base):
    __tablename__ = "items"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    color_tone = Column(String)
    price = Column(Float)
    stock = Column(Integer)