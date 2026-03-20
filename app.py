from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from typing import List, Dict, Any, Set, Optional
import json
import secrets
import logging

from sqlalchemy.orm import Session

from veritree_gake import VeriTreeManager, GroupSession
from database import get_db
from models import Group, GroupMembership, GroupRole, GroupTree
from crud import (
    get_or_create_user,
    add_membership,
    remove_membership,
    require_admin_or_owner,
    get_membership_by_token,
    list_group_members,
    get_active_member_names,
    is_accepted_member_of_group,
)
from email_service import send_invite_email
from config import APP_BASE_URL
from database import SessionLocal

logger = logging.getLogger(__name__)

app = FastAPI(title="VeriTree Secure Company Chat")

chat_sessions: Dict[int, GroupSession] = {}
clients: Dict[int, Set[WebSocket]] = {}

mgr = VeriTreeManager()


# ── Pydantic request / response schemas ──────────────────────────────────────

class MemberEntry(BaseModel):
    username: str
    email: Optional[str] = None

class GroupCreateRequest(BaseModel):
    name: str
    admins: List[MemberEntry]
    moderators: List[MemberEntry]
    members: List[MemberEntry]

class AddMemberRequest(BaseModel):
    username: str
    email: Optional[str] = None
    role: str = "member"

class RemoveMemberRequest(BaseModel):
    username: str  # user to remove
    removed_by: str  # username of the person performing the removal (must be higher in hierarchy)

class EncryptRequest(BaseModel):
    group_id: int
    user: str
    message: str

class RekeyRequest(BaseModel):
    user: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rebuild_tree_and_session(db: Session, group: Group) -> dict:
    """Rebuild the VeriTree for current members and refresh the crypto session (rekey).
    Per VeriTree-GAKE: after add/remove member we recompute the tree and derive a new
    group key so excluded members cannot derive future keys (forward secrecy)."""
    admin_name, moderators, members = get_active_member_names(db, group.id)

    moderators_for_tree = [
        f"mod{i+1}" for i in range(max(1, len(moderators)))
    ]

    tree_result = mgr.create_org_tree(
        admin_name,
        moderators_for_tree,
        members_per_mod=max(1, len(members)) if members else 1,
    )

    tree_row = db.query(GroupTree).filter_by(group_id=group.id).first()
    if tree_row:
        tree_row.veritree_state = tree_result
        tree_row.epoch = (tree_row.epoch or 0) + 1
    else:
        tree_row = GroupTree(group_id=group.id, epoch=1, veritree_state=tree_result)
        db.add(tree_row)

    db.flush()

    group_key = bytes.fromhex(secrets.token_hex(32))
    global_sid = bytes.fromhex(secrets.token_hex(32))
    chat_sessions[group.id] = GroupSession(group_key, global_sid)
    if group.id not in clients:
        clients[group.id] = set()

    return tree_result


async def _notify_ws(group_id: int, payload: dict):
    """Send a JSON payload to all WebSocket clients in a group."""
    data = json.dumps(payload)
    for client in list(clients.get(group_id, [])):
        try:
            await client.send_text(data)
        except Exception:
            clients[group_id].discard(client)


# ── UI ────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return _render_main_page()


@app.get("/join/{token}", response_class=HTMLResponse)
async def accept_invite(token: str, db: Session = Depends(get_db)):
    membership = get_membership_by_token(db, token)
    if not membership:
        raise HTTPException(status_code=404, detail="Invalid or expired invitation link.")

    if membership.accepted:
        return _render_join_page(
            membership.group.name,
            membership.group.id,
            membership.user.username,
            already=True,
        )

    membership.accepted = True
    db.commit()

    return _render_join_page(
        membership.group.name,
        membership.group.id,
        membership.user.username,
        already=False,
    )


# ── API: create group ────────────────────────────────────────────────────────

@app.post("/groups")
def create_group(req: GroupCreateRequest, db: Session = Depends(get_db)):
    if not req.admins:
        raise HTTPException(status_code=400, detail="At least one admin required")

    owner_entry = req.admins[0]
    owner = get_or_create_user(db, owner_entry.username, owner_entry.email)

    group = Group(name=req.name, owner_id=owner.id, is_closed=False)
    db.add(group)
    db.commit()
    db.refresh(group)

    invites_to_send: list[tuple[str, str, str]] = []
    invite_links: list[dict] = []

    def _add_entries(entries: List[MemberEntry], role: GroupRole):
        for entry in entries:
            user = get_or_create_user(db, entry.username, entry.email)
            m = add_membership(db, user, group, role)
            if m.invite_token:
                join_url = f"{APP_BASE_URL}/join/{m.invite_token}"
                invite_links.append({
                    "username": entry.username,
                    "email": entry.email or None,
                    "role": role.value,
                    "join_link": join_url,
                })
            if entry.email and m.invite_token:
                invites_to_send.append((entry.email, m.invite_token, role.value))

    _add_entries(req.admins, GroupRole.admin)
    _add_entries(req.moderators, GroupRole.moderator)
    _add_entries(req.members, GroupRole.member)

    owner_m = add_membership(db, owner, group, GroupRole.owner)
    if owner_m.role != GroupRole.owner:
        owner_m.role = GroupRole.owner
    owner_m.accepted = True
    db.commit()

    tree_result = _rebuild_tree_and_session(db, group)
    db.commit()

    emails_sent = 0
    for email, token, role in invites_to_send:
        if send_invite_email(email, group.name, token, role):
            emails_sent += 1

    return {
        "group_id": group.id,
        "name": group.name,
        "tree": {
            "tree_id": tree_result.get("tree_id"),
            "bandwidth_bytes": tree_result.get("bandwidth_bytes", 0),
            "unanimous": tree_result.get("unanimous", True),
        },
        "invite_links": invite_links,
        "emails_sent": emails_sent,
    }


# ── API: dynamic add member ──────────────────────────────────────────────────

@app.post("/groups/{group_id}/members")
def api_add_member(
    group_id: int,
    req: AddMemberRequest,
    db: Session = Depends(get_db),
):
    group = db.query(Group).filter_by(id=group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    role_map = {
        "admin": GroupRole.admin,
        "moderator": GroupRole.moderator,
        "member": GroupRole.member,
    }
    role = role_map.get(req.role)
    if not role:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")

    user = get_or_create_user(db, req.username, req.email)
    m = add_membership(db, user, group, role)

    tree_result = _rebuild_tree_and_session(db, group)
    db.commit()

    email_sent = False
    if req.email and m.invite_token:
        email_sent = send_invite_email(req.email, group.name, m.invite_token, role.value)

    join_link = f"{APP_BASE_URL}/join/{m.invite_token}" if m.invite_token else None
    tree_row = db.query(GroupTree).filter_by(group_id=group_id).first()
    return {
        "status": "added",
        "username": req.username,
        "role": role.value,
        "invite_token": m.invite_token,
        "join_link": join_link,
        "email_sent": email_sent,
        "tree_id": tree_result.get("tree_id"),
        "epoch": tree_row.epoch if tree_row else None,
    }


# ── API: dynamic remove member ───────────────────────────────────────────────

@app.delete("/groups/{group_id}/members")
def api_remove_member(
    group_id: int,
    req: RemoveMemberRequest,
    db: Session = Depends(get_db),
):
    group = db.query(Group).filter_by(id=group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    try:
        removed = remove_membership(db, group_id, req.username, removed_by_username=req.removed_by)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if not removed:
        raise HTTPException(status_code=404, detail="Member not found in group")

    tree_result = _rebuild_tree_and_session(db, group)
    db.commit()

    return {
        "status": "removed",
        "username": req.username,
        "tree_id": tree_result.get("tree_id"),
        "epoch": db.query(GroupTree).filter_by(group_id=group_id).first().epoch,
    }


# ── API: list members ────────────────────────────────────────────────────────

@app.get("/groups/{group_id}/members")
def api_list_members(group_id: int, db: Session = Depends(get_db)):
    group = db.query(Group).filter_by(id=group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"group_id": group_id, "members": list_group_members(db, group_id)}


# ── API: rekey ────────────────────────────────────────────────────────────────

@app.post("/groups/{group_id}/rekey")
def rekey_group(group_id: int, req: RekeyRequest, db: Session = Depends(get_db)):
    try:
        require_admin_or_owner(db, group_id, req.user)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    group = db.query(Group).filter_by(id=group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    tree_result = _rebuild_tree_and_session(db, group)
    db.commit()

    tree_row = db.query(GroupTree).filter_by(group_id=group_id).first()
    return {
        "status": "rekeyed",
        "new_epoch": tree_row.epoch,
        "tree_id": tree_result.get("tree_id"),
    }


# ── API: encrypt ──────────────────────────────────────────────────────────────

@app.post("/api/encrypt")
def api_encrypt(req: EncryptRequest, db: Session = Depends(get_db)):
    session = chat_sessions.get(req.group_id)
    if not session:
        raise HTTPException(status_code=404, detail="Group session not active")
    if not is_accepted_member_of_group(db, req.group_id, req.user):
        raise HTTPException(
            status_code=403,
            detail="You must be an accepted member of this group to send messages. Use the invite link to join.",
        )

    encrypted = session.encrypt_message(req.message.encode(), req.user).hex()
    return {
        "group_id": req.group_id,
        "user": req.user,
        "plaintext_preview": req.message,
        "encrypted": encrypted,
    }


# ── WebSocket broadcast ──────────────────────────────────────────────────────

@app.websocket("/ws/{group_id}")
async def ws_chat(
    websocket: WebSocket,
    group_id: int,
    username: str = Query(..., description="Your username; must be an accepted member of the group"),
):
    """Connect to group chat. Requires query param 'username'; user must be an accepted member of the group."""
    if not username or not username.strip():
        await websocket.close(code=4400, reason="Missing username. Use ?username=YourName")
        return
    username = username.strip()
    db = SessionLocal()
    try:
        group = db.query(Group).filter_by(id=group_id).first()
        if not group:
            await websocket.close(code=4404, reason="Group not found")
            return
        if not is_accepted_member_of_group(db, group_id, username):
            await websocket.close(
                code=4403,
                reason="Not a member of this group. Accept the invite link sent to your email first.",
            )
            return
    finally:
        db.close()

    await websocket.accept()
    if group_id not in clients:
        clients[group_id] = set()
    clients[group_id].add(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            for client in list(clients[group_id]):
                try:
                    await client.send_text(data)
                except Exception:
                    clients[group_id].discard(client)
    except WebSocketDisconnect:
        clients[group_id].discard(websocket)


# ── HTML renderers ────────────────────────────────────────────────────────────

def _render_join_page(group_name: str, group_id: int, username: str, already: bool) -> str:
    status = "You already accepted this invitation." if already else "Invitation accepted! You're now part of the group."
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Join Group - VeriTree</title>
  <style>{_css()}</style>
</head>
<body>
  <div class="container" style="max-width:520px; text-align:center; margin-top:80px;">
    <div class="card">
      <div class="logo">VeriTree</div>
      <h2>{'Already Joined' if already else 'Welcome!'}</h2>
      <p>{status}</p>
      <p><strong>Group:</strong> {group_name}</p>
      <p><strong>Username:</strong> {username}</p>
      <p style="font-size:12px; color:var(--text-muted); margin-top:12px;">You can now chat from this or any device. Use the button below to open the chat (your username and group are pre-filled).</p>
      <a href="/?group_id={group_id}&username={username}" class="btn" style="display:inline-block; margin-top:16px; text-decoration:none;">
        Open Chat
      </a>
    </div>
  </div>
</body>
</html>"""


def _css() -> str:
    return """\
:root {
  --bg: #0f0f1a;
  --surface: #1a1a2e;
  --surface2: #22223a;
  --primary: #4361ee;
  --primary-hover: #3a56d4;
  --danger: #ef476f;
  --danger-hover: #d63d5e;
  --success: #06d6a0;
  --text: #e8e8f0;
  --text-muted: #8888aa;
  --border: #2a2a44;
  --radius: 10px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
}
.container { max-width: 960px; margin: 0 auto; padding: 24px; }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  margin-bottom: 20px;
}
.logo {
  font-size: 28px; font-weight: 800; color: var(--primary);
  letter-spacing: -0.5px;
}
.logo span { color: var(--success); }
h2 { font-size: 18px; margin: 8px 0 16px; color: var(--text); }
label {
  display: block; font-size: 13px; font-weight: 600;
  color: var(--text-muted); margin-bottom: 4px; margin-top: 12px;
}
input[type="text"], input[type="email"], select {
  width: 100%; padding: 10px 12px; background: var(--surface2);
  border: 1px solid var(--border); border-radius: 6px;
  color: var(--text); font-size: 14px; outline: none;
  transition: border-color 0.2s;
}
input:focus, select:focus { border-color: var(--primary); }
input[readonly] { opacity: 0.9; cursor: not-allowed; }
.btn {
  padding: 10px 20px; border: none; border-radius: 6px;
  font-size: 14px; font-weight: 600; cursor: pointer;
  color: #fff; background: var(--primary);
  transition: background 0.2s;
}
.btn:hover { background: var(--primary-hover); }
.btn-danger { background: var(--danger); }
.btn-danger:hover { background: var(--danger-hover); }
.btn-sm { padding: 6px 14px; font-size: 12px; }
.row { display: flex; gap: 12px; flex-wrap: wrap; }
.row > * { flex: 1; min-width: 0; }
.member-row {
  display: flex; gap: 8px; align-items: center;
  margin-bottom: 6px;
}
.member-row input { flex: 1; }
.member-row .remove-btn {
  background: none; border: none; color: var(--danger);
  cursor: pointer; font-size: 18px; padding: 4px 8px;
}
.tag {
  display: inline-block; padding: 3px 10px; border-radius: 12px;
  font-size: 11px; font-weight: 700; text-transform: uppercase;
}
.tag-owner { background: #4361ee33; color: var(--primary); }
.tag-admin { background: #06d6a033; color: var(--success); }
.tag-moderator { background: #ffd16633; color: #ffc233; }
.tag-member { background: #ffffff15; color: var(--text-muted); }
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th, td {
  text-align: left; padding: 10px 12px;
  border-bottom: 1px solid var(--border); font-size: 13px;
}
th { color: var(--text-muted); font-weight: 600; font-size: 11px; text-transform: uppercase; }
#chat-box {
  height: 340px; overflow-y: auto; padding: 12px;
  background: var(--surface2); border-radius: 8px;
  margin: 12px 0; border: 1px solid var(--border);
}
.msg {
  margin-bottom: 8px; padding: 8px 12px;
  background: var(--bg); border-radius: 8px;
  font-size: 13px; line-height: 1.5;
}
.msg strong { color: var(--primary); }
.msg .cipher { font-size: 11px; color: var(--text-muted); word-break: break-all; }
.chat-input-row { display: flex; gap: 8px; }
.chat-input-row input { flex: 1; }
.tabs { display: flex; gap: 0; margin-bottom: 20px; }
.tab {
  padding: 10px 24px; cursor: pointer; font-weight: 600;
  font-size: 14px; border: 1px solid var(--border);
  background: var(--surface); color: var(--text-muted);
  transition: all 0.2s;
}
.tab:first-child { border-radius: var(--radius) 0 0 var(--radius); }
.tab:last-child { border-radius: 0 var(--radius) var(--radius) 0; }
.tab.active { background: var(--primary); color: #fff; border-color: var(--primary); }
.hidden { display: none; }
.toast {
  position: fixed; bottom: 24px; right: 24px; padding: 12px 24px;
  background: var(--success); color: #000; font-weight: 600;
  border-radius: 8px; font-size: 13px; z-index: 999;
  opacity: 0; transition: opacity 0.3s;
}
.toast.show { opacity: 1; }
.status { font-size: 12px; color: var(--text-muted); margin-top: 8px; }
.epoch-badge {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  background: var(--primary); color: #fff; font-size: 11px;
  font-weight: 700; margin-left: 8px;
}
@media (max-width: 640px) {
  .container { padding: 12px; }
  .row { flex-direction: column; }
  .tabs { flex-wrap: wrap; }
}
"""


def _render_main_page() -> str:
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>VeriTree Secure Chat</title>
  <style>{_css()}</style>
</head>
<body>
<div class="container">

  <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:20px;">
    <div>
      <div class="logo">Veri<span>Tree</span> Secure Chat</div>
      <p style="font-size:13px; color:var(--text-muted); margin-top:4px;">
        Post-quantum group key agreement &middot; End-to-end encrypted messaging
      </p>
    </div>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    <div class="tab active" onclick="switchTab('create')">Create Group</div>
    <div class="tab" onclick="switchTab('manage')">Manage Group</div>
    <div class="tab" onclick="switchTab('chat')">Chat</div>
  </div>

  <!-- ═══ TAB 1: CREATE GROUP ═══ -->
  <div id="tab-create">
    <div class="card">
      <h2>Create a New Secure Group</h2>

      <label>Group Name</label>
      <input type="text" id="group-name" placeholder="e.g. Project Alpha"/>

      <h3 style="margin-top:20px; font-size:14px; color:var(--success);">Admins</h3>
      <div id="admin-list"></div>
      <button class="btn btn-sm" style="margin-top:6px;" onclick="addMemberRow('admin-list')">+ Add Admin</button>

      <h3 style="margin-top:16px; font-size:14px; color:#ffc233;">Moderators</h3>
      <div id="mod-list"></div>
      <button class="btn btn-sm" style="margin-top:6px;" onclick="addMemberRow('mod-list')">+ Add Moderator</button>

      <h3 style="margin-top:16px; font-size:14px; color:var(--text-muted);">Members</h3>
      <div id="member-list"></div>
      <button class="btn btn-sm" style="margin-top:6px;" onclick="addMemberRow('member-list')">+ Add Member</button>

      <div style="margin-top:20px;">
        <button class="btn" onclick="createGroup()" id="create-btn">Create Group &amp; Run Protocol</button>
      </div>
      <div class="status" id="create-status"></div>
      <div id="invite-links-wrap" class="hidden" style="margin-top:16px; padding:12px; background:var(--surface2); border-radius:8px; border:1px solid var(--border);">
        <h4 style="font-size:13px; margin-bottom:8px; color:var(--success);">Invite links — share with members (e.g. by email or chat)</h4>
        <p style="font-size:12px; color:var(--text-muted); margin-bottom:10px;">Configure SMTP in .env or config to send these links by email. Until then, copy and share each link below.</p>
        <ul id="invite-links-list" style="list-style:none; font-size:12px;"></ul>
      </div>
    </div>
  </div>

  <!-- ═══ TAB 2: MANAGE GROUP ═══ -->
  <div id="tab-manage" class="hidden">
    <div class="card">
      <h2>Manage Group Members</h2>
      <p style="font-size:12px; color:var(--text-muted); margin-bottom:12px;">Removal follows hierarchy: only owner/admin can remove admins; only owner/admin/moderator can remove moderators; only higher roles can remove members.</p>
      <p id="manage-invite-lock-note" class="hidden" style="font-size:12px; color:var(--success); margin-bottom:8px;">Opened via invite link: Group ID and your username are locked.</p>
      <div class="row">
        <div>
          <label>Group ID <span id="manage-gid-lock-hint" class="hidden" style="color:var(--success); font-weight:normal;">(locked)</span></label>
          <input type="text" id="manage-gid" placeholder="e.g. 1"/>
        </div>
        <div>
          <label>Your username (authorizes remove) <span id="manage-actor-lock-hint" class="hidden" style="color:var(--success); font-weight:normal;">(locked)</span></label>
          <input type="text" id="manage-actor" placeholder="e.g. admin"/>
        </div>
        <div style="display:flex; align-items:flex-end;">
          <button class="btn" onclick="loadMembers()">Load Members</button>
        </div>
      </div>

      <div id="members-table-wrap" class="hidden" style="margin-top:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <h3 style="font-size:14px;">Current Members <span id="epoch-badge" class="epoch-badge"></span></h3>
          <button class="btn btn-sm" onclick="showAddPanel()">+ Add Member</button>
        </div>
        <table>
          <thead><tr><th>Username</th><th>Email</th><th>Role</th><th>Status</th><th></th></tr></thead>
          <tbody id="members-tbody"></tbody>
        </table>
      </div>

      <!-- Add member sub-panel -->
      <div id="add-member-panel" class="hidden card" style="margin-top:16px; border-color:var(--primary);">
        <h3 style="font-size:14px; margin-bottom:12px;">Add New Member</h3>
        <div class="row">
          <div>
            <label>Username</label>
            <input type="text" id="new-member-name" placeholder="username"/>
          </div>
          <div>
            <label>Email</label>
            <input type="email" id="new-member-email" placeholder="user@example.com"/>
          </div>
          <div>
            <label>Role</label>
            <select id="new-member-role">
              <option value="member">Member</option>
              <option value="moderator">Moderator</option>
              <option value="admin">Admin</option>
            </select>
          </div>
        </div>
        <div style="margin-top:12px; display:flex; gap:8px;">
          <button class="btn" onclick="addMember()">Add &amp; Send Invite</button>
          <button class="btn" style="background:var(--surface2);" onclick="hideAddPanel()">Cancel</button>
        </div>
        <div class="status" id="add-status"></div>
      </div>

      <div class="status" id="manage-status"></div>
    </div>
  </div>

  <!-- ═══ TAB 3: CHAT ═══ -->
  <div id="tab-chat" class="hidden">
    <div class="card">
      <h2>Encrypted Group Chat</h2>
      <p style="font-size:12px; color:var(--text-muted); margin-bottom:12px;">Only <strong>accepted</strong> group members can connect. Use the exact username from your invite; accept the join link (e.g. from email) first if you haven&apos;t yet.</p>
      <div class="row" style="margin-bottom:12px;">
        <div>
          <label>Group ID <span id="chat-gid-lock-hint" class="hidden" style="color:var(--success); font-weight:normal;">(locked from invite link)</span></label>
          <input type="text" id="chat-gid" placeholder="e.g. 1"/>
        </div>
        <div>
          <label>Your Username <span id="chat-user-lock-hint" class="hidden" style="color:var(--success); font-weight:normal;">(locked from invite link)</span></label>
          <input type="text" id="chat-user" placeholder="e.g. alice" autocomplete="username"/>
        </div>
        <div style="display:flex; align-items:flex-end;">
          <button class="btn" onclick="connectChat()">Connect</button>
        </div>
      </div>
      <div id="chat-connected" class="hidden">
        <div id="chat-box"></div>
        <div class="chat-input-row">
          <input type="text" id="chat-input" placeholder="Type a message..."
                 onkeydown="if(event.key==='Enter')sendMessage();"/>
          <button class="btn" onclick="sendMessage()">Send</button>
        </div>
      </div>
      <div class="status" id="chat-status"></div>
    </div>
  </div>

</div><!-- /container -->

<div class="toast" id="toast"></div>

<script>
/* ── helpers ── */
function $(id) {{ return document.getElementById(id); }}

function toast(msg) {{
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3000);
}}
function copyInviteLink(btn) {{
  const link = btn.getAttribute('data-link');
  if (link) {{ navigator.clipboard.writeText(link); toast('Link copied'); }}
}}

function switchTab(name) {{
  ['create','manage','chat'].forEach(t => {{
    $('tab-'+t).classList.toggle('hidden', t !== name);
  }});
  document.querySelectorAll('.tab').forEach((el, i) => {{
    el.classList.toggle('active', el.textContent.toLowerCase().includes(name.slice(0,4)));
  }});
}}

/* ── dynamic member rows for create form ── */
function addMemberRow(containerId) {{
  const div = document.createElement('div');
  div.className = 'member-row';
  div.innerHTML = `
    <input type="text" placeholder="username" class="mr-name"/>
    <input type="email" placeholder="email (optional)" class="mr-email"/>
    <button class="remove-btn" onclick="this.parentElement.remove()">&times;</button>
  `;
  $(containerId).appendChild(div);
}}

function collectEntries(containerId) {{
  const rows = $(containerId).querySelectorAll('.member-row');
  const entries = [];
  rows.forEach(r => {{
    const name = r.querySelector('.mr-name').value.trim();
    const email = r.querySelector('.mr-email').value.trim();
    if (name) entries.push({{ username: name, email: email || null }});
  }});
  return entries;
}}

/* seed one row per section */
addMemberRow('admin-list');
addMemberRow('mod-list');
addMemberRow('member-list');

/* When opened via invite link (?group_id=1&username=alice): lock Group ID and username everywhere so they cannot be changed */
(function() {{
  const params = new URLSearchParams(location.search);
  const gid = params.get('group_id');
  const un = params.get('username');
  const fromInviteLink = !!(gid && un);
  if (fromInviteLink) {{
    const lock = (id, value, hintId) => {{
      const el = $(id);
      if (el) {{ el.value = value; el.readOnly = true; el.setAttribute('readonly', 'readonly'); }}
      const h = hintId && $(hintId);
      if (h) h.classList.remove('hidden');
    }};
    lock('chat-gid', gid, 'chat-gid-lock-hint');
    lock('chat-user', un, 'chat-user-lock-hint');
    lock('manage-gid', gid, 'manage-gid-lock-hint');
    lock('manage-actor', un, 'manage-actor-lock-hint');
    const note = $('manage-invite-lock-note');
    if (note) note.classList.remove('hidden');
    switchTab('chat');
  }} else if (gid) {{
    $('chat-gid').value = gid;
  }}
}})();

/* ── create group ── */
let currentGroupId = null;

async function createGroup() {{
  const name = $('group-name').value.trim() || 'Untitled';
  const admins = collectEntries('admin-list');
  const mods = collectEntries('mod-list');
  const members = collectEntries('member-list');

  if (admins.length === 0) {{
    $('create-status').textContent = 'At least one admin is required.';
    return;
  }}

  $('create-btn').disabled = true;
  $('create-status').textContent = 'Running VeriTree-GAKE protocol...';

  try {{
    const res = await fetch('/groups', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ name, admins, moderators: mods, members }})
    }});
    if (!res.ok) {{
      $('create-status').textContent = 'Error: ' + (await res.text());
      return;
    }}
    const data = await res.json();
    currentGroupId = data.group_id;

    $('create-status').textContent =
      `Group created (ID: ${{data.group_id}}) | Tree: ${{data.tree.tree_id}} | BW: ${{data.tree.bandwidth_bytes}} B | Unanimous: ${{data.tree.unanimous}}`;
    if (data.emails_sent > 0) $('create-status').textContent += ` | ${{data.emails_sent}} invite email(s) sent.`;

    $('chat-gid').value = data.group_id;
    $('manage-gid').value = data.group_id;

    const wrap = $('invite-links-wrap');
    const list = $('invite-links-list');
    if (data.invite_links && data.invite_links.length > 0) {{
      wrap.classList.remove('hidden');
      list.innerHTML = '';
      data.invite_links.forEach(inv => {{
        const li = document.createElement('li');
        li.style.marginBottom = '8px';
        li.innerHTML = `<strong>${{inv.username}}</strong>${{inv.email ? ' (' + inv.email + ')' : ''}} — <a href="${{inv.join_link}}" target="_blank" rel="noopener" style="color:var(--primary); word-break:break-all;">${{inv.join_link}}</a> <button class="btn btn-sm" style="margin-left:6px;" onclick="copyInviteLink(this)" data-link="${{inv.join_link.replace(/"/g, '&quot;')}}">Copy</button>`;
        list.appendChild(li);
      }});
      toast('Group created! Share the invite links above (or check email if SMTP is configured).');
    }} else {{
      toast('Group created!');
    }}
  }} catch (e) {{
    $('create-status').textContent = 'Error: ' + e;
  }} finally {{
    $('create-btn').disabled = false;
  }}
}}

/* ── manage members ── */
async function loadMembers() {{
  const gid = $('manage-gid').value.trim();
  if (!gid) return;
  $('manage-status').textContent = 'Loading...';

  try {{
    const res = await fetch(`/groups/${{gid}}/members`);
    if (!res.ok) {{ $('manage-status').textContent = 'Error: ' + (await res.text()); return; }}
    const data = await res.json();

    const tree = await fetch(`/groups/${{gid}}/members`);
    $('members-table-wrap').classList.remove('hidden');

    const tbody = $('members-tbody');
    tbody.innerHTML = '';
    data.members.forEach(m => {{
      const tr = document.createElement('tr');
      const tagClass = 'tag-' + m.role;
      tr.innerHTML = `
        <td>${{m.username}}</td>
        <td style="color:var(--text-muted)">${{m.email || '—'}}</td>
        <td><span class="tag ${{tagClass}}">${{m.role}}</span></td>
        <td>${{m.accepted ? '✓ Accepted' : 'Pending'}}</td>
        <td>${{m.role !== 'owner' ?
          `<button class="btn btn-danger btn-sm" onclick="removeMember('${{m.username}}')">Remove</button>` :
          ''}}</td>
      `;
      tbody.appendChild(tr);
    }});
    $('manage-status').textContent = `${{data.members.length}} member(s) loaded.`;
  }} catch (e) {{
    $('manage-status').textContent = 'Error: ' + e;
  }}
}}

function showAddPanel() {{ $('add-member-panel').classList.remove('hidden'); }}
function hideAddPanel() {{ $('add-member-panel').classList.add('hidden'); $('add-status').textContent = ''; }}

async function addMember() {{
  const gid = $('manage-gid').value.trim();
  const username = $('new-member-name').value.trim();
  const email = $('new-member-email').value.trim();
  const role = $('new-member-role').value;

  if (!gid || !username) {{ $('add-status').textContent = 'Group ID and username required.'; return; }}

  $('add-status').textContent = 'Adding & rekeying...';
  try {{
    const res = await fetch(`/groups/${{gid}}/members`, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ username, email: email || null, role }})
    }});
    if (!res.ok) {{ $('add-status').textContent = 'Error: ' + (await res.text()); return; }}
    const data = await res.json();
    let status = `Added ${{username}} (epoch ${{data.epoch}}).`;
    if (data.email_sent) status += ' Invite email sent.';
    else if (data.join_link) status += ' Share the join link below (configure SMTP in config to send by email).';
    $('add-status').innerHTML = status + (data.join_link ? ' <button class="btn btn-sm" id="add-copy-btn">Copy link</button>' : '');
    if (data.join_link) {{
      const link = data.join_link;
      $('add-status').append(document.createTextNode(' ' + link));
      const btn = document.getElementById('add-copy-btn');
      if (btn) btn.onclick = () => {{ navigator.clipboard.writeText(link); toast('Link copied'); }};
    }}
    toast(`${{username}} added to group. Tree rekeyed.`);
    hideAddPanel();
    loadMembers();
  }} catch (e) {{
    $('add-status').textContent = 'Error: ' + e;
  }}
}}

async function removeMember(username) {{
  const gid = $('manage-gid').value.trim();
  const removedBy = $('manage-actor').value.trim();
  if (!gid) return;
  if (!removedBy) {{ $('manage-status').textContent = 'Enter your username to authorize removal.'; return; }}
  if (!confirm(`Remove ${{username}} from the group? This triggers a rekey.`)) return;

  $('manage-status').textContent = 'Removing & rekeying...';
  try {{
    const res = await fetch(`/groups/${{gid}}/members`, {{
      method: 'DELETE',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ username, removed_by: removedBy }})
    }});
    if (!res.ok) {{ $('manage-status').textContent = 'Error: ' + (await res.text()); return; }}
    const data = await res.json();
    $('manage-status').textContent = `${{username}} removed (epoch ${{data.epoch}}). Tree rekeyed.`;
    toast(`${{username}} removed. Forward secrecy ensured.`);
    loadMembers();
  }} catch (e) {{
    $('manage-status').textContent = 'Error: ' + e;
  }}
}}

/* ── chat ── */
let ws = null;

function connectChat() {{
  const gid = $('chat-gid').value.trim();
  const user = $('chat-user').value.trim();
  if (!gid || !user) {{ $('chat-status').textContent = 'Enter Group ID and username.'; return; }}

  if (ws) {{ ws.close(); }}

  $('chat-status').textContent = 'Connecting...';
  const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${{wsProto}}//${{location.host}}/ws/${{gid}}?username=${{encodeURIComponent(user)}}`);

  ws.onopen = () => {{
    $('chat-status').textContent = 'Connected to group ' + gid;
    $('chat-connected').classList.remove('hidden');
    currentGroupId = Number(gid);
  }};

  ws.onclose = (event) => {{
    $('chat-status').textContent = event.code === 4403
      ? 'Not a member of this group. Accept the invite link from your email (or the link shared with you) first.'
      : 'Disconnected.';
  }};

  ws.onmessage = (event) => {{
    try {{
      const msg = JSON.parse(event.data);
      if (msg.type === 'rekey') {{
        appendSystem(`Tree rekeyed (epoch ${{msg.epoch}}). Forward secrecy updated.`);
        return;
      }}
      if (msg.type === 'member_added') {{
        appendSystem(`${{msg.username}} joined the group.`);
        return;
      }}
      if (msg.type === 'member_removed') {{
        appendSystem(`${{msg.username}} was removed from the group.`);
        return;
      }}
      appendMessage(msg.user, msg.plaintext_preview, msg.encrypted);
    }} catch (e) {{}}
  }};
}}

function appendMessage(user, plaintext, ciphertext) {{
  const box = $('chat-box');
  const div = document.createElement('div');
  div.className = 'msg';
  div.innerHTML = `<strong>${{user}}</strong>: ${{plaintext || ''}}
    <div class="cipher">cipher: ${{(ciphertext || '').slice(0, 60)}}...</div>`;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}}

function appendSystem(text) {{
  const box = $('chat-box');
  const div = document.createElement('div');
  div.className = 'msg';
  div.style.borderLeft = '3px solid var(--success)';
  div.innerHTML = `<em style="color:var(--success)">${{text}}</em>`;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}}

async function sendMessage() {{
  if (!ws || ws.readyState !== WebSocket.OPEN) {{ toast('Not connected.'); return; }}
  const user = $('chat-user').value.trim() || 'anon';
  const msg = $('chat-input').value.trim();
  if (!msg) return;

  try {{
    const res = await fetch('/api/encrypt', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ group_id: currentGroupId, user, message: msg }})
    }});
    const data = await res.json().catch(() => ({{}}));
    if (!res.ok) {{
      toast(data.detail || 'Failed to send');
      return;
    }}
    ws.send(JSON.stringify(data));
    $('chat-input').value = '';
  }} catch (e) {{
    toast('Encrypt error: ' + e);
  }}
}}
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    from config import APP_HOST, APP_PORT
    uvicorn.run("app:app", host=APP_HOST, port=APP_PORT, reload=True)
