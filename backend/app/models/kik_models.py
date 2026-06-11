"""
kik_models.py — Domeinmodellen voor de KIK-opvraag-flow.

Een *ketenpartij* (tenant) stelt gevalideerde indicator-vragen, via een
uitwisselprofiel, aan één of meer *zorgaanbieders*. Elke vraag gaat (gesimuleerd)
naar het datastation van de zorgaanbieder, dat het antwoord berekent en
terugstuurt. De antwoorden worden hier vastgelegd.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base, GUID


class AntwoordStatus(str, enum.Enum):
    OK        = "OK"
    GEEN_DATA = "GEEN_DATA"
    FOUT      = "FOUT"


class UitvraagStatus(str, enum.Enum):
    VOLTOOID  = "VOLTOOID"
    GEDEELTELIJK = "GEDEELTELIJK"
    MISLUKT   = "MISLUKT"


class Zorgaanbieder(Base):
    """Een zorgaanbieder die zich registreert om uitvragen te kunnen ontvangen."""
    __tablename__ = "zorgaanbieders"

    id              = Column(GUID(), primary_key=True, default=uuid.uuid4)
    naam            = Column(String(255), nullable=False)
    kvk             = Column(String(32), nullable=True)
    plaats          = Column(String(128), nullable=True)
    contact_email   = Column(String(255), nullable=True)
    datastation_url = Column(String(512), nullable=True)  # SPARQL-endpoint; leeg = simulatie
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    antwoorden = relationship("Antwoord", back_populates="zorgaanbieder")


class Uitvraag(Base):
    """Eén uitvraag van een ketenpartij: een profiel + indicatoren naar aanbieders."""
    __tablename__ = "uitvragen"

    id            = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id     = Column(GUID(), nullable=False, index=True)   # de ketenpartij
    created_by    = Column(GUID(), nullable=True)
    profiel_key   = Column(String(64), nullable=False)
    profiel_label = Column(String(255), nullable=False)
    status         = Column(Enum(UitvraagStatus), nullable=False, default=UitvraagStatus.VOLTOOID)
    doorlooptijd_ms = Column(Integer, nullable=True)   # max latency over de antwoorden (parallel model)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    antwoorden = relationship("Antwoord", back_populates="uitvraag",
                              cascade="all, delete-orphan", order_by="Antwoord.zorgaanbieder_naam")


class Antwoord(Base):
    """Eén berekend antwoord: (uitvraag × zorgaanbieder × indicator)."""
    __tablename__ = "antwoorden"

    id                = Column(GUID(), primary_key=True, default=uuid.uuid4)
    uitvraag_id       = Column(GUID(), ForeignKey("uitvragen.id", ondelete="CASCADE"), nullable=False, index=True)
    zorgaanbieder_id  = Column(GUID(), ForeignKey("zorgaanbieders.id"), nullable=True)
    zorgaanbieder_naam= Column(String(255), nullable=False)
    indicator_code    = Column(String(64), nullable=False)
    indicator_label   = Column(String(255), nullable=False)
    eenheid           = Column(String(32), nullable=True)
    waarde            = Column(Float, nullable=True)
    status            = Column(Enum(AntwoordStatus), nullable=False, default=AntwoordStatus.OK)
    toelichting       = Column(Text, nullable=True)
    duur_ms           = Column(Integer, nullable=True)   # gesimuleerde/echte datastation-latency
    computed_at       = Column(DateTime(timezone=True), server_default=func.now())

    uitvraag      = relationship("Uitvraag", back_populates="antwoorden")
    zorgaanbieder = relationship("Zorgaanbieder", back_populates="antwoorden")


class CapabilityStatus(str, enum.Enum):
    PRODUCTIE     = "productie"
    TEST          = "test"
    IMPLEMENTATIE = "implementatie"
    UITGEFASEERD  = "uitgefaseerd"


class AanbiederCapability(Base):
    """Welk uitwisselprofiel (+versie+status) een zorgaanbieder heeft geïmplementeerd.

    Gevoed via een CSV (single source of truth, beheerd door KIK-V Beheer) en in
    de app read-only. Vol-refresh bij import. Conform RFC ZIN-VCO.
    """
    __tablename__ = "aanbieder_capabilities"

    id                  = Column(GUID(), primary_key=True, default=uuid.uuid4)
    aanbieder_id_type   = Column(String(8), nullable=False)        # kvk | agb
    aanbieder_id        = Column(String(32), nullable=False, index=True)
    aanbieder_naam      = Column(String(255), nullable=False, index=True)
    software_leverancier= Column(String(255), nullable=True)
    uitwisselprofiel    = Column(String(64), nullable=False, index=True)   # profiel-key
    versie              = Column(String(32), nullable=False)
    status              = Column(Enum(CapabilityStatus), nullable=False)
    laatst_bijgewerkt   = Column(String(10), nullable=True)        # YYYY-MM-DD
    imported_at         = Column(DateTime(timezone=True), server_default=func.now())
