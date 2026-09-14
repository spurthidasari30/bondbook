"""Optional isolated development-only seed data. Run only against a disposable database."""
from main import Base, SessionLocal, User, Memory, create_token, engine, new_invite_code, pwd_context
from datetime import date

Base.metadata.create_all(engine)
db = SessionLocal()
if not db.query(User).filter_by(email="alice@example.com").first():
    alice = User(name="Alice", email="alice@example.com", password_hash=pwd_context.hash("password123"), invite_code=new_invite_code(db), avatar_color="#8064d7")
    bob = User(name="Bob", email="bob@example.com", password_hash=pwd_context.hash("password123"), invite_code=new_invite_code(db), avatar_color="#e07a9b")
    db.add_all([alice, bob]); db.flush(); alice.friend_id = bob.id; bob.friend_id = alice.id
    db.add(Memory(owner_id=alice.id, title="Our first coffee catch-up", description="The cinnamon rolls were far too large, and it was perfect.", memory_date=date.today(), category="Happy", tags="coffee, weekend", mood="Joyful", visibility="Shared"))
    db.commit()
    print("Created alice@example.com and bob@example.com (password: password123).")
else:
    print("Seed users already exist; nothing changed.")
db.close()
