import enum
from sqlalchemy import (
    Column, Integer, String, ForeignKey,
    DateTime, Enum, Boolean, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class GroupRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    moderator = "moderator"
    member = "member"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    memberships = relationship("GroupMembership", back_populates="user")


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"))
    is_closed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    memberships = relationship("GroupMembership", back_populates="group", cascade="all, delete-orphan")
    tree = relationship("GroupTree", uselist=False, back_populates="group", cascade="all, delete-orphan")


class GroupMembership(Base):
    __tablename__ = "group_memberships"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    role = Column(Enum(GroupRole), nullable=False)
    invite_token = Column(String, unique=True, nullable=True, index=True)
    accepted = Column(Boolean, default=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="uq_user_group"),
    )

    user = relationship("User", back_populates="memberships")
    group = relationship("Group", back_populates="memberships")


class GroupTree(Base):
    __tablename__ = "group_trees"

    group_id = Column(Integer, ForeignKey("groups.id"), primary_key=True)
    epoch = Column(Integer, default=1)
    veritree_state = Column(JSON, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    group = relationship("Group", back_populates="tree")
