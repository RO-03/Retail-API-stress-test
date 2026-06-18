from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import models
import schemas
from database import SessionLocal, engine

# Automatically create the database tables if they don't exist
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Dependency: Opens a DB session for a request, and closes it when done
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper function to seed initial data if the database is empty
def init_db(db: Session):
    if db.query(models.DBItem).first() is None:
        initial_items = [
            models.DBItem(id="1", name="Linen Button-Down", color_tone="Warm Mustard", price=45.0, stock=15),
            models.DBItem(id="2", name="Tailored Chinos", color_tone="Earth Brown", price=60.0, stock=8),
            models.DBItem(id="3", name="Lightweight Jacket", color_tone="Olive Green", price=85.0, stock=5)
        ]
        db.add_all(initial_items)
        db.commit()

# Seed the database on startup
with SessionLocal() as db:
    init_db(db)

@app.get("/")
def serve_frontend():
    # You can paste your exact index.html code into an index.html file in the same directory!
    return FileResponse("index.html")

@app.get("/api/inventory", response_model=list[schemas.Item])
def get_inventory(db: Session = Depends(get_db)):
    # Replaces reading the CSV
    items = db.query(models.DBItem).all()
    return items

@app.post("/api/inventory", status_code=201)
def add_item(item: schemas.ItemCreate, db: Session = Depends(get_db)):
    # Check if item exists in DB
    db_item = db.query(models.DBItem).filter(models.DBItem.id == item.id).first()
    if db_item:
        raise HTTPException(status_code=400, detail="Item ID already exists")
    
    # Replaces appending to CSV
    new_item = models.DBItem(**item.model_dump())
    db.add(new_item)
    db.commit()
    return {"message": "Item added to inventory"}

@app.post("/api/purchase/{item_id}")
def purchase_item(item_id: str, db: Session = Depends(get_db)):
    # Perform an atomic update: tell the DB to decrement stock ONLY if stock > 0
    updated_count = db.query(models.DBItem)\
        .filter(models.DBItem.id == item_id, models.DBItem.stock > 0)\
        .update({"stock": models.DBItem.stock - 1}, synchronize_session=False)
    
    # Save the changes
    db.commit()

    # If updated_count is 0, it means the item either didn't exist OR stock was 0
    if updated_count == 0:
        # Let's do a quick check to give the correct error message
        item_exists = db.query(models.DBItem).filter(models.DBItem.id == item_id).first()
        if not item_exists:
            raise HTTPException(status_code=404, detail="Item not found")
        raise HTTPException(status_code=400, detail="Out of stock")

    return {"message": "Purchase successful"}

@app.post("/api/restock/{item_id}")
def restock_item(item_id: str, amount: int, db: Session = Depends(get_db)):
    # Find the specific item in the database
    db_item = db.query(models.DBItem).filter(models.DBItem.id == item_id).first()
    
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")
        
    # Increase the stock
    db_item.stock += amount
    db.commit() 
    
    return {"message": f"Restocked {db_item.name} by {amount} units."}