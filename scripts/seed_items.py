from app.core.database import SessionLocal
import app.models.item as models


def seed_items():
    db = SessionLocal()
    try:
        if not db.query(models.Item).first():
            items = [
                models.Item(name='Wireless Mouse', price=25.99, stock=15000),
                models.Item(name='Mechanical Keyboard', price=89.50, stock=30),
                models.Item(name='27-inch Monitor', price=210.00, stock=15),
                models.Item(name='USB-C Hub', price=15.99, stock=100)
            ]
            db.add_all(items)
            db.commit()
            print('✅ Successfully seeded 4 default items!')
        else:
            print('Items already exist in the database.')
    except Exception as e:
        print(f'❌ Error seeding items: {e}')
    finally:
        db.close()


if __name__ == '__main__':
    seed_items()
