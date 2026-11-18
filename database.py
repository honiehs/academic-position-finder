import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Text, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

os.makedirs("data", exist_ok=True)

engine = create_engine('sqlite:///data/apply_bot.db', echo=False)
Base = declarative_base()

class UserProfile(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    resume_file_id = Column(String)
    resume_file_path = Column(String)
    target_degrees = Column(String)
    target_field = Column(String)
    target_countries = Column(String)
    has_language_cert = Column(Boolean)
    language_score = Column(String)
    positions = relationship("Position", back_populates="user")
    language = Column(String, nullable=True)  # 'fa' or 'en'

class Position(Base):
    __tablename__ = 'positions'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    raw_text = Column(Text)
    extracted_link = Column(String)
    requirements = Column(Text)
    deadline = Column(String)
    needs_supervisor = Column(Boolean, default=False)
    status = Column(String, default="Pending")
    user = relationship("UserProfile", back_populates="positions")

SessionLocal = sessionmaker(bind=engine)

def init_db():
    with engine.connect() as conn:
        res = conn.execute(text("PRAGMA table_info(positions)")).fetchall()
        col_names = [row[1] for row in res]
        if "link" in col_names:
            conn.execute(text("DROP TABLE IF EXISTS positions"))
            conn.commit()
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE user_profiles ADD COLUMN language VARCHAR"))
            conn.commit()
        except Exception:
            pass
    print("✅ دیتابیس با موفقیت آماده شد!")