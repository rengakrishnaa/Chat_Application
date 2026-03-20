import secrets
from typing import Optional, List, Tuple

from sqlalchemy.orm import Session

from models import User, Group, GroupMembership, GroupRole, GroupTree
from config import INVITE_TOKEN_BYTES


def get_or_create_user(
    db: Session,
    username: str,
    email: Optional[str] = None,
) -> User:
    user = db.query(User).filter_by(username=username).first()
    if user:
        if email and not user.email:
            user.email = email
            db.commit()
            db.refresh(user)
        return user

    user = User(username=username, email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def generate_invite_token() -> str:
    return secrets.token_urlsafe(INVITE_TOKEN_BYTES)


def add_membership(
    db: Session,
    user: User,
    group: Group,
    role: GroupRole,
) -> GroupMembership:
    existing = (
        db.query(GroupMembership)
        .filter_by(user_id=user.id, group_id=group.id)
        .first()
    )
    if existing:
        return existing

    token = generate_invite_token()
    membership = GroupMembership(
        user_id=user.id,
        group_id=group.id,
        role=role,
        invite_token=token,
        accepted=False,
    )
    db.add(membership)
    db.flush()
    return membership


# Hierarchy for removal: only a strictly higher role can remove a lower one (owner > admin > moderator > member).
_ROLE_ORDER = {GroupRole.owner: 0, GroupRole.admin: 1, GroupRole.moderator: 2, GroupRole.member: 3}


def remove_membership(
    db: Session,
    group_id: int,
    username: str,
    removed_by_username: Optional[str] = None,
) -> bool:
    """Remove a member from the group. If removed_by_username is set, enforces hierarchy: only higher roles can remove lower (owner > admin > moderator > member)."""
    target = (
        db.query(GroupMembership)
        .join(User, GroupMembership.user_id == User.id)
        .filter(GroupMembership.group_id == group_id, User.username == username)
        .first()
    )
    if not target:
        return False
    if target.role == GroupRole.owner:
        raise PermissionError("Cannot remove the group owner")

    if removed_by_username is not None:
        remover = (
            db.query(GroupMembership)
            .join(User, GroupMembership.user_id == User.id)
            .filter(
                GroupMembership.group_id == group_id,
                User.username == removed_by_username,
            )
            .first()
        )
        if not remover:
            raise PermissionError("You are not a member of this group")
        remover_order = _ROLE_ORDER.get(remover.role, 99)
        target_order = _ROLE_ORDER.get(target.role, 99)
        if remover_order >= target_order:
            raise PermissionError(
                "Only a higher role can remove a lower one. Hierarchy: owner > admin > moderator > member. "
                "Members cannot remove moderators; moderators cannot remove admins."
            )

    db.delete(target)
    db.flush()
    return True


def get_membership_by_token(db: Session, token: str) -> Optional[GroupMembership]:
    return db.query(GroupMembership).filter_by(invite_token=token).first()


def list_group_members(
    db: Session,
    group_id: int,
) -> List[dict]:
    rows = (
        db.query(GroupMembership)
        .join(User, GroupMembership.user_id == User.id)
        .filter(GroupMembership.group_id == group_id)
        .all()
    )
    return [
        {
            "username": m.user.username,
            "email": m.user.email,
            "role": m.role.value,
            "accepted": m.accepted,
        }
        for m in rows
    ]


def get_active_member_names(db: Session, group_id: int) -> Tuple[str, List[str], List[str]]:
    """Return (admin_name, moderator_names, member_names) for VeriTree rebuild."""
    rows = (
        db.query(GroupMembership)
        .join(User, GroupMembership.user_id == User.id)
        .filter(GroupMembership.group_id == group_id)
        .all()
    )
    admin = None
    moderators: List[str] = []
    members: List[str] = []

    for m in rows:
        if m.role in (GroupRole.owner, GroupRole.admin):
            if admin is None:
                admin = m.user.username
        elif m.role == GroupRole.moderator:
            moderators.append(m.user.username)
        else:
            members.append(m.user.username)

    if not moderators:
        moderators = ["mod1"]
    return admin or "admin", moderators, members


def require_role(
    db: Session,
    group_id: int,
    user_id: int,
    allowed: set,
):
    m = db.query(GroupMembership).filter_by(
        group_id=group_id,
        user_id=user_id,
    ).first()
    if not m or m.role not in allowed:
        raise PermissionError("Insufficient role")


def require_admin_or_owner(
    db: Session,
    group_id: int,
    username: str,
):
    m = (
        db.query(GroupMembership)
        .join(User, GroupMembership.user_id == User.id)
        .filter(
            GroupMembership.group_id == group_id,
            User.username == username,
        )
        .first()
    )
    if not m or m.role not in {GroupRole.admin, GroupRole.owner}:
        raise PermissionError("Admin or owner role required")


def is_accepted_member_of_group(
    db: Session,
    group_id: int,
    username: str,
) -> bool:
    """Return True if the user is a member of the group and has accepted the invite (required for chat)."""
    m = (
        db.query(GroupMembership)
        .join(User, GroupMembership.user_id == User.id)
        .filter(
            GroupMembership.group_id == group_id,
            User.username == username,
        )
        .first()
    )
    return m is not None and m.accepted
