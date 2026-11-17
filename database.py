from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Text, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

engine = create_engine('sqlite:///apply_bot.db', echo=False)
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
    # بررسی اینکه آیا ستون قدیمی و مشکل‌ساز link در جدول وجود دارد یا خیر
    with engine.connect() as conn:
        res = conn.execute(text("PRAGMA table_info(positions)")).fetchall()
        col_names = [row[1] for row in res]
        if "link" in col_names:
            print("🔄 در حال حذف ستون قدیمی 'link' و بروزرسانی جدول پوزیشن‌ها...")
            conn.execute(text("DROP TABLE IF EXISTS positions"))
            conn.commit()

    # ساخت جدول جدید و استاندارد (پروفایل شما در جدول users کاملاً دست‌نخورده باقی می‌ماند)
    Base.metadata.create_all(engine)
    print("✅ دیتابیس با موفقیت تعمیر و آماده شد!")