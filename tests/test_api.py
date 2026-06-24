"""
tests/test_api.py
-----------------
pytest test suite for the Retail Store API.

Uses FastAPI's TestClient backed by an *in-memory SQLite* database so the
tests execute in any environment (CI/CD, local venv) without requiring a
running Postgres instance.

Run:
    pytest tests/ -v
"""

import os
import pytest

# ── Must be set BEFORE any app modules are imported ───────────────────────────
# database.py reads DATABASE_URL from the environment; setting it here prevents
# SQLAlchemy from ever trying to load psycopg2 during the test run.
os.environ["DATABASE_URL"] = "sqlite:///./test_retail.db"

# Now it is safe to import the app modules
from sqlalchemy import create_engine                         # noqa: E402
from sqlalchemy.orm import sessionmaker                      # noqa: E402

import database                                              # noqa: E402
import models                                                # noqa: E402

# ── Rebuild the engine for SQLite (no pool_size on StaticPool) ────────────────
from sqlalchemy.pool import StaticPool                       # noqa: E402

test_engine = create_engine(
    "sqlite:///./test_retail.db",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Patch the module-level objects so auth.get_db() uses our test session
database.engine = test_engine
database.SessionLocal = TestingSessionLocal

# Create all tables in the test database
models.Base.metadata.create_all(bind=test_engine)

import auth                                                  # noqa: E402

# Override get_db dependency so every request uses the test session
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Import app AFTER patching so create_all uses the test engine ──────────────
from main import app                                         # noqa: E402

app.dependency_overrides[auth.get_db] = override_get_db

from fastapi.testclient import TestClient                    # noqa: E402
client = TestClient(app)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_tables():
    """Wipe items and admins between tests for isolation."""
    yield
    db = TestingSessionLocal()
    db.query(models.Item).delete()
    db.query(models.Admin).delete()
    db.commit()
    db.close()


@pytest.fixture()
def seeded_item():
    """Insert a single item and return its id."""
    db = TestingSessionLocal()
    item = models.Item(name="Test Widget", price=9.99, stock=50)
    db.add(item)
    db.commit()
    db.refresh(item)
    item_id = item.id
    db.close()
    return item_id


@pytest.fixture()
def admin_token():
    """Create an admin account and return a valid Bearer token."""
    db = TestingSessionLocal()
    hashed = auth.get_password_hash("testpass")
    admin = models.Admin(username="testadmin", hashed_password=hashed)
    db.add(admin)
    db.commit()
    db.close()

    resp = client.post(
        "/admin/login",
        data={"username": "testadmin", "password": "testpass"},
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


# ── Health probe tests ─────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_200(self):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_payload(self):
        resp = client.get("/health")
        assert resp.json() == {"status": "ok"}


# ── Public customer route tests ───────────────────────────────────────────────

class TestPublicRoutes:
    def test_get_items_empty(self):
        """GET /items should return an empty list when the store has no items."""
        resp = client.get("/items")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_items_with_stock(self, seeded_item):
        """GET /items should return a list containing the seeded item."""
        resp = client.get("/items")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["name"] == "Test Widget"
        assert items[0]["stock"] == 50

    def test_purchase_item_success(self, seeded_item):
        """POST /purchase/{id} should decrement stock by 1."""
        resp = client.post(f"/purchase/{seeded_item}")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Purchase successful"

        # Verify stock was actually decremented
        db = TestingSessionLocal()
        item = db.query(models.Item).filter(models.Item.id == seeded_item).first()
        db.close()
        assert item.stock == 49

    def test_purchase_out_of_stock(self):
        """POST /purchase/{id} should return 409 when stock == 0."""
        db = TestingSessionLocal()
        item = models.Item(name="Sold Out", price=1.00, stock=0)
        db.add(item)
        db.commit()
        db.refresh(item)
        item_id = item.id
        db.close()

        resp = client.post(f"/purchase/{item_id}")
        assert resp.status_code == 409

    def test_purchase_nonexistent_item(self):
        """POST /purchase/{id} should return 409 for a non-existent item id."""
        resp = client.post("/purchase/99999")
        assert resp.status_code == 409


# ── Admin authentication tests ────────────────────────────────────────────────

class TestAdminAuth:
    def test_login_invalid_credentials(self):
        """POST /admin/login with wrong password should return 401."""
        resp = client.post(
            "/admin/login",
            data={"username": "nobody", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_login_success(self, admin_token):
        """A valid admin token must be a non-empty string."""
        assert isinstance(admin_token, str)
        assert len(admin_token) > 0

    def test_protected_route_without_token(self):
        """GET /admin/items/all without a token should return 401."""
        resp = client.get("/admin/items/all")
        assert resp.status_code == 401

    def test_protected_route_with_invalid_token(self):
        """GET /admin/items/all with a garbage token should return 401."""
        resp = client.get(
            "/admin/items/all",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401


# ── Admin CRUD tests ──────────────────────────────────────────────────────────

class TestAdminCRUD:
    def test_get_all_items_authenticated(self, admin_token, seeded_item):
        resp = client.get(
            "/admin/items/all",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_add_item(self, admin_token):
        payload = {"name": "New Gadget", "price": 49.99, "stock": 100}
        resp = client.post(
            "/admin/items",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Item added successfully"

        # Verify the item exists in the DB
        items = client.get("/items").json()
        assert any(i["name"] == "New Gadget" for i in items)

    def test_update_item_price(self, admin_token, seeded_item):
        resp = client.put(
            f"/admin/items/{seeded_item}",
            json={"price": 19.99},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

        db = TestingSessionLocal()
        item = db.query(models.Item).filter(models.Item.id == seeded_item).first()
        db.close()
        assert float(item.price) == pytest.approx(19.99, abs=0.01)

    def test_update_item_restock(self, admin_token, seeded_item):
        resp = client.put(
            f"/admin/items/{seeded_item}",
            json={"stock_add": 25},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

        db = TestingSessionLocal()
        item = db.query(models.Item).filter(models.Item.id == seeded_item).first()
        db.close()
        assert item.stock == 75  # 50 original + 25 added

    def test_update_nonexistent_item(self, admin_token):
        resp = client.put(
            "/admin/items/99999",
            json={"price": 5.00},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_delete_item(self, admin_token, seeded_item):
        resp = client.delete(
            f"/admin/items/{seeded_item}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Item deleted"

        # Confirm it's gone
        items = client.get("/items").json()
        assert all(i["id"] != seeded_item for i in items)

    def test_delete_nonexistent_item(self, admin_token):
        resp = client.delete(
            "/admin/items/99999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
