import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, Date, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class App(Base):
    __tablename__ = "apps"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id           = Column(String, nullable=False)        # store's own app ID
    store            = Column(String, nullable=False)        # 'google_play' | 'apple'
    app_name         = Column(String)
    category         = Column(String)
    developer        = Column(String)
    developer_email  = Column(String)
    developer_website= Column(String)
    last_updated     = Column(Date)
    rating           = Column(Float)
    installs         = Column(String)
    price            = Column(String)
    d2c_signals      = Column(Text)
    positive_keywords= Column(Text)
    discovered_at    = Column(DateTime, default=datetime.utcnow)
    status           = Column(String, default="discovered")
    # status values: discovered | evidence_collecting | scored |
    #                archived (score < threshold, no outreach) |
    #                waiting_approval | email_sent | reply_received |
    #                meeting_booked | won | lost
    score_at_archive = Column(Integer)   # snapshot of score when archived

    evidence  = relationship("Evidence", back_populates="app", cascade="all, delete-orphan")
    score     = relationship("OpportunityScore", back_populates="app", uselist=False, cascade="all, delete-orphan")
    contacts  = relationship("Contact", back_populates="app", cascade="all, delete-orphan")
    campaigns = relationship("OutreachCampaign", back_populates="app", cascade="all, delete-orphan")


class Evidence(Base):
    __tablename__ = "evidence"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id       = Column(UUID(as_uuid=True), ForeignKey("apps.id"), nullable=False)
    collector    = Column(String, nullable=False)   # 'app_health' | 'company_intel' | ...
    data         = Column(JSONB)                    # facts only — no scores
    confidence   = Column(Float, default=0.0)       # 0.0–1.0
    signals      = Column(ARRAY(Text))              # human-readable bullet points
    collected_at = Column(DateTime, default=datetime.utcnow)
    error        = Column(Text)

    app = relationship("App", back_populates="evidence")


class OpportunityScore(Base):
    __tablename__ = "opportunity_scores"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id           = Column(UUID(as_uuid=True), ForeignKey("apps.id"), nullable=False, unique=True)
    total_score      = Column(Integer)              # 0–100 (normalized from 110)
    grade            = Column(String)               # A | B | C | D
    collector_scores = Column(JSONB)                # {"app_health": 20, "company_intel": 12, ...}
    top_signals      = Column(ARRAY(Text))          # top 5 human-readable signals
    outreach_angle   = Column(Text)                 # best pitch angle
    total_llm_cost   = Column(Float, default=0.0)   # USD from llm_audit_log
    scored_at        = Column(DateTime, default=datetime.utcnow)

    app = relationship("App", back_populates="score")


class Contact(Base):
    __tablename__ = "contacts"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id       = Column(UUID(as_uuid=True), ForeignKey("apps.id"), nullable=False)
    name         = Column(String)
    title        = Column(String)
    email        = Column(String)
    linkedin_url = Column(String)
    twitter_url  = Column(String)
    confidence   = Column(Float, default=0.0)
    source       = Column(String)
    is_primary   = Column(Boolean, default=False)

    app       = relationship("App", back_populates="contacts")
    campaigns = relationship("OutreachCampaign", back_populates="contact")


class OutreachCampaign(Base):
    __tablename__ = "outreach_campaigns"

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id               = Column(UUID(as_uuid=True), ForeignKey("apps.id"), nullable=False)
    contact_id           = Column(UUID(as_uuid=True), ForeignKey("contacts.id"))
    email_subject        = Column(String)
    email_body           = Column(Text)
    followup_1_body      = Column(Text)
    followup_2_body      = Column(Text)
    status               = Column(String, default="draft")  # draft | approved | sent
    instantly_campaign_id= Column(String)
    created_at           = Column(DateTime, default=datetime.utcnow)
    approved_at          = Column(DateTime)
    sent_at              = Column(DateTime)

    app     = relationship("App", back_populates="campaigns")
    contact = relationship("Contact", back_populates="campaigns")


class LLMAuditLog(Base):
    __tablename__ = "llm_audit_log"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id            = Column(UUID(as_uuid=True), ForeignKey("apps.id"))
    collector         = Column(String)
    model             = Column(String)              # 'claude-haiku-4-5' | 'claude-sonnet-4-6' | 'gemini-pro'
    prompt_tokens     = Column(Integer)
    completion_tokens = Column(Integer)
    cost_usd          = Column(Float)
    latency_ms        = Column(Integer)
    prompt_preview    = Column(Text)                # first 500 chars
    created_at        = Column(DateTime, default=datetime.utcnow)
