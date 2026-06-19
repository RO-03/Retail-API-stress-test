from database import SessionLocal
import models
import auth

def create_superuser():
    db = SessionLocal()
    try:
        # Check if an admin already exists to prevent duplicates
        existing_admin = db.query(models.Admin).filter(models.Admin.username == "admin").first()
        if existing_admin:
            print("Admin user already exists!")
            return

        # Hash the password and create the user
        hashed_pw = auth.get_password_hash("admin123")
        new_admin = models.Admin(username="admin", hashed_password=hashed_pw)
        
        db.add(new_admin)
        db.commit()
        print("✅ Success! Admin user created.")
        print("Username: admin")
        print("Password: admin123")
        
    except Exception as e:
        print(f"❌ Error creating admin: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_superuser()
