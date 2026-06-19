from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text
import models, schemas, auth
from database import engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# ==========================================
# PUBLIC CUSTOMER ROUTES
# ==========================================

@app.get("/items")
def view_items(db: Session = Depends(auth.get_db)):
    """Customer: View all available items"""
    return db.query(models.Item).filter(models.Item.stock > 0).all()

@app.post("/purchase/{item_id}")
def purchase_item(item_id: int, db: Session = Depends(auth.get_db)):
    """Customer: High-concurrency atomic purchase"""
    # Raw SQL for atomic update to prevent race conditions during stress tests
    result = db.execute(
        text("UPDATE items SET stock = stock - 1 WHERE id = :id AND stock > 0 RETURNING id"),
        {"id": item_id}
    ).fetchone()
    
    if not result:
        raise HTTPException(status_code=409, detail="Item out of stock or does not exist")
    
    db.commit()
    return {"message": "Purchase successful"}


# ==========================================
# PROTECTED ADMIN ROUTES
# ==========================================

@app.post("/admin/login", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(auth.get_db)):
    """Admin: Login to receive JWT Token"""
    admin = db.query(models.Admin).filter(models.Admin.username == form_data.username).first()
    if not admin or not auth.verify_password(form_data.password, admin.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    access_token = auth.create_access_token(data={"sub": admin.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/admin/items")
def add_item(item: schemas.ItemCreate, admin: models.Admin = Depends(auth.get_current_admin), db: Session = Depends(auth.get_db)):
    """Admin: Add a new item to the store"""
    # Pydantic dict() is deprecated in v2, but keeping it as in nextplan.txt
    new_item = models.Item(**item.dict())
    db.add(new_item)
    db.commit()
    return {"message": "Item added successfully"}

@app.put("/admin/items/{item_id}")
def update_item(item_id: int, item_update: schemas.ItemUpdate, admin: models.Admin = Depends(auth.get_current_admin), db: Session = Depends(auth.get_db)):
    """Admin: Update price or restock an item"""
    db_item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    if item_update.price is not None:
        db_item.price = item_update.price
    if item_update.stock_add is not None:
        db_item.stock += item_update.stock_add
        
    db.commit()
    return {"message": "Item updated successfully"}

@app.delete("/admin/items/{item_id}")
def delete_item(item_id: int, admin: models.Admin = Depends(auth.get_current_admin), db: Session = Depends(auth.get_db)):
    """Admin: Remove an item entirely"""
    db_item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    db.delete(db_item)
    db.commit()
    return {"message": "Item deleted"}