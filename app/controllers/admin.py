from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import app.models.item as models
import app.schemas.item as schemas
from app.core.database import get_db
from app.services.auth import get_current_admin, verify_password, create_access_token

router = APIRouter(prefix="/admin", tags=["admin"])

templates: Jinja2Templates | None = None


def set_templates(t: Jinja2Templates):
    """Called once from app/main.py to inject the templates instance."""
    global templates
    templates = t


# ── Page view routes ──────────────────────────────────────────────────────────

@router.get("/")
def render_admin_login(request: Request):
    """Serves the Admin Login Screen."""
    return templates.TemplateResponse(request=request, name="admin_login.html")

@router.get("/dashboard")
def render_admin_dashboard(request: Request):
    """Serves the Secured Admin Dashboard."""
    return templates.TemplateResponse(request=request, name="admin_dashboard.html")


# ── Auth route ────────────────────────────────────────────────────────────────

@router.post("/login", response_model=schemas.Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Admin: Login to receive JWT Token."""
    admin = db.query(models.Admin).filter(models.Admin.username == form_data.username).first()
    if not admin or not verify_password(form_data.password, admin.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    access_token = create_access_token(data={"sub": admin.username})
    return {"access_token": access_token, "token_type": "bearer"}


# ── Protected CRUD routes ─────────────────────────────────────────────────────

@router.get("/items/all")
def get_all_items(
    admin: models.Admin = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin: View all items."""
    return db.query(models.Item).order_by(models.Item.id).all()


@router.post("/items")
def add_item(
    item: schemas.ItemCreate,
    admin: models.Admin = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin: Add a new item to the store."""
    new_item = models.Item(**item.model_dump())
    db.add(new_item)
    db.commit()
    return {"message": "Item added successfully"}


@router.put("/items/{item_id}")
def update_item(
    item_id: int,
    item_update: schemas.ItemUpdate,
    admin: models.Admin = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin: Update price or restock an item."""
    db_item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item_update.price is not None:
        db_item.price = item_update.price
    if item_update.stock_add is not None:
        db_item.stock += item_update.stock_add

    db.commit()
    return {"message": "Item updated successfully"}


@router.delete("/items/{item_id}")
def delete_item(
    item_id: int,
    admin: models.Admin = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin: Remove an item entirely."""
    db_item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    db.delete(db_item)
    db.commit()
    return {"message": "Item deleted"}
