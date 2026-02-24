"""
Capturing VeriTree-GAKE simulator: runs the full protocol and captures
all intermediates for test vector generation. Subclasses veritree_gake.core.VeriTreeSimulator.
"""

import io
import sys
import time
import json
from typing import List, Dict, Any, Optional

# Import everything we need from the real implementation
from veritree_gake.core import (
    VeriTreeSimulator,
    Node,
    canonical_encode,
    canonical_decode,
    hash_sha256,
    hmac_sha256,
    hkdf_sha256,
    sha3_512,
    compute_sid_level,
    compute_sid_global,
)


def _hexify(obj: Any) -> Any:
    """Recursively convert bytes to hex strings for JSON."""
    if isinstance(obj, bytes):
        return obj.hex()
    if isinstance(obj, dict):
        return {k: _hexify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_hexify(x) for x in obj]
    return obj


class CapturingSimulator(VeriTreeSimulator):
    """Simulator that captures all intermediates into self._capture and self._combiner_capture."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._capture = {}
        self._combiner_capture = {}
        self._transcript_ordered = []  # byte-exact message sequence (list of bytes)

    def parent_mkem_broadcast(self, parent_id: str, children_ids: List[str],
                              family: str, nodes: Dict[str, Node],
                              kem_objs: Dict, downlinks: Dict,
                              commits: Dict, commit_sigs: Dict):
        super().parent_mkem_broadcast(
            parent_id, children_ids, family, nodes, kem_objs,
            downlinks, commits, commit_sigs
        )
        parent = nodes[parent_id]
        if parent.transcript:
            self._transcript_ordered.append(parent.transcript[-1])

    def child_uplink_kem(self, child_id: str, parent_id: str, family: str,
                         nodes: Dict[str, Node], kem_objs: Dict, uplinks: Dict):
        super().child_uplink_kem(child_id, parent_id, family, nodes, kem_objs, uplinks)
        child = nodes[child_id]
        if child.transcript:
            self._transcript_ordered.append(child.transcript[-1])

    def dual_commit(self, node: Node):
        encoded, sig = super().dual_commit(node)
        self._transcript_ordered.append(encoded)
        return encoded, sig

    def dual_open(self, node: Node):
        encoded, sig = super().dual_open(node)
        self._transcript_ordered.append(encoded)
        return encoded, sig

    def split_key_combiner(self, B_per_level: Dict[int, Dict[str, bytes]],
                           families: List[str], sid: bytes) -> bytes:
        """Override to capture K_grp, k_j, u_j, t before returning K_final."""
        from veritree_gake.core import hash_sha256 as h, hmac_sha256 as hm

        K_grp = {}
        for family in families:
            all_B = b"".join([
                B_per_level[lvl].get(family, b"\x00" * 32)
                for lvl in sorted(B_per_level.keys())
            ])
            K_grp[family] = hkdf_sha256(
                salt=hash_sha256(b"K_grp_salt"),
                ikm=all_B + sid,
                info=b"K_grp|" + family.encode() + b"|" + sid,
                length=32
            )
        k_j = {}
        for family in families:
            salt_j = hash_sha256(b"salt|" + family.encode())
            k_j[family] = hmac_sha256(salt_j, K_grp[family])
        u_j = {}
        for family in families:
            ctx_j = f"VTG:combiner|{family}|{sid.hex()}".encode()
            u_j[family] = (
                sha3_512(K_grp[family] + ctx_j + b"|chunk1")[:21] +
                sha3_512(K_grp[family] + ctx_j + b"|chunk2")[:21] +
                sha3_512(K_grp[family] + ctx_j + b"|chunk3")[:22]
            )
        t = bytes([0] * 32)
        families_sorted = sorted(families)
        for j_idx, family_j in enumerate(families_sorted):
            other_u = b"".join([
                u_j[f] for f_idx, f in enumerate(families_sorted) if f_idx != j_idx
            ])
            label_j = f"label|{family_j}".encode()
            hmac_val = hmac_sha256(k_j[family_j], other_u + label_j)
            t = bytes(a ^ b for a, b in zip(t, hmac_val))
        K_final = sha3_512(t)[:32]

        self._combiner_capture = {
            "K_grp": _hexify(K_grp),
            "salt1_hex": hash_sha256(b"salt|" + families_sorted[0].encode()).hex(),
            "salt2_hex": hash_sha256(b"salt|" + families_sorted[1].encode()).hex(),
            "k_j": _hexify(k_j),
            "u_j": _hexify(u_j),
            "intermediate_t_hex": t.hex(),
            "K_final_hex": K_final.hex(),
        }
        return K_final

    def run_demo_tree(self, admin_name: str, n_mod: int, members_per: int,
                      families: List[str] = None, sid: bytes = b"sid") -> Dict:
        """Run full protocol and capture all intermediates into self._capture."""
        def _to_hex(d):
            if isinstance(d, bytes):
                return d.hex()
            if isinstance(d, dict):
                return {k: _to_hex(v) for k, v in d.items()}
            return d

        self._capture = {}
        self._transcript_ordered = []
        self.total_bytes = 0
        families = families if families else self.default_families
        kem_objs = self.make_kem_objects(families)

        nodes, parent, children = {}, {}, {}
        admin_id = admin_name or "admin"
        nodes[admin_id] = Node(admin_id, "admin", level=2, families=families)
        parent[admin_id] = None
        children[admin_id] = []
        for i in range(n_mod):
            mid = f"mod{i+1}"
            nodes[mid] = Node(mid, "moderator", level=1, families=families)
            parent[mid] = admin_id
            children[mid] = []
            children[admin_id].append(mid)
        for i in range(n_mod):
            mid = f"mod{i+1}"
            for j in range(members_per):
                lid = f"{mid}-mem{j+1}"
                nodes[lid] = Node(lid, "member", level=0, families=families)
                parent[lid] = mid
                children[lid] = []
                children[mid].append(lid)

        for nid, node in nodes.items():
            for fam in families:
                pk, sk = kem_objs[fam].keygen()
                node.longterm_pk[fam] = pk
                node.longterm_sk[fam] = sk
                epk, esk = kem_objs[fam].keygen()
                node.ephemeral_pk[fam] = epk
                node.ephemeral_sk[fam] = esk
        for nid, node in nodes.items():
            node.sid_l = compute_sid_level([b"init"], node.level)

        downlinks = {}
        commits = {}
        commit_sigs = {}
        uplinks = {}
        downlinks_ephemeral = {}

        for p_id, child_ids in children.items():
            if not child_ids:
                continue
            for fam in families:
                self.parent_mkem_broadcast(
                    p_id, child_ids, fam, nodes, kem_objs,
                    downlinks, commits, commit_sigs
                )
        self._capture["downlinks"] = _to_hex(downlinks)

        for c_id, p_id in parent.items():
            if p_id is None:
                continue
            for fam in families:
                self.child_uplink_kem(c_id, p_id, fam, nodes, kem_objs, uplinks)
        self._capture["uplinks"] = _to_hex(uplinks)
        self._capture["nodes_keys"] = {
            nid: {
                fam: {"pk_hex": node.longterm_pk[fam].hex(), "sk_hex": node.longterm_sk[fam].hex()}
                for fam in families
            }
            for nid, node in nodes.items()
        }

        for p_id, child_ids in children.items():
            if not child_ids:
                continue
            downlinks_ephemeral[p_id] = {}
            for c_id in child_ids:
                downlinks_ephemeral[p_id][c_id] = {}
                for fam in families:
                    ct_ep, kprime = kem_objs[fam].encaps(nodes[c_id].ephemeral_pk[fam])
                    downlinks_ephemeral[p_id][c_id][fam] = {'ct': ct_ep, 'kprime_parent': kprime}
                    self.total_bytes += len(ct_ep['ct'])

        for nid in sorted(nodes.keys()):
            self.derive_level_secrets(
                nodes[nid], parent[nid], children.get(nid, []),
                downlinks, uplinks, downlinks_ephemeral, kem_objs
            )
        self._capture["level_secrets"] = {
            nid: {fam: node.level_secrets[fam].hex() for fam in node.families}
            for nid, node in nodes.items()
        }
        self._capture["tildeK"] = {nid: node.tildeK.hex() for nid, node in nodes.items()}

        for nid in sorted(nodes.keys()):
            self.dual_commit(nodes[nid])
        self._capture["dual_commit"] = {
            nid: {
                "KeX_hex": nodes[nid].tildeK.hex(),
                "mask_hex": nodes[nid].mask.hex(),
                "rho1_hex": nodes[nid].rho1.hex(),
                "rho2_hex": nodes[nid].rho2.hex(),
                "commit1_hex": nodes[nid].commit1.hex(),
                "commit2_hex": nodes[nid].commit2.hex(),
                "masked_hex": nodes[nid].masked.hex(),
            }
            for nid in sorted(nodes.keys())
        }
        self._capture["sid_l_hex"] = {nid: nodes[nid].sid_l.hex() for nid in nodes}

        time.sleep(0.01)
        opens = {}
        for nid in sorted(nodes.keys()):
            encoded, sig = self.dual_open(nodes[nid])
            opens[nid] = canonical_decode(encoded)
        self._capture["opens"] = opens

        for nid in sorted(nodes.keys()):
            self.verify_dual_open(nodes[nid], opens[nid])

        B_per_level = {}
        for level in sorted(set(n.level for n in nodes.values())):
            level_nodes = [nid for nid, n in nodes.items() if n.level == level]
            B_per_level[level] = {}
            for fam in families:
                xor_acc = bytes([0] * 32)
                for nid in level_nodes:
                    xor_acc = bytes(a ^ b for a, b in zip(xor_acc, nodes[nid].tildeK))
                B_per_level[level][fam] = xor_acc
        self._capture["B_per_level"] = _hexify(B_per_level)

        all_level_sids = [nodes[nid].sid_l for nid in sorted(nodes.keys())]
        global_sid = compute_sid_global(all_level_sids)
        self._capture["global_sid_hex"] = global_sid.hex()

        K_final = self.split_key_combiner(B_per_level, families, global_sid)
        self._capture["combiner"] = self._combiner_capture

        confirmation_tags = {}
        for nid in sorted(nodes.keys()):
            tag = self.key_confirmation(nodes[nid], K_final, global_sid)
            confirmation_tags[nid] = tag
        self._capture["confirmation_tags"] = confirmation_tags

        result = {
            'unanimous': True,
            'SK_hex': K_final.hex(),
            'global_sid': global_sid.hex(),
            'total_bytes': self.total_bytes,
            'nodes': {},
            'bandwidth_kb': round(self.total_bytes / 1024.0, 2),
        }
        for nid, node in nodes.items():
            result['nodes'][nid] = {
                'role': node.role,
                'level': node.level,
                'tildeK': node.tildeK.hex(),
                'masked': node.masked.hex(),
                'mask': node.mask.hex(),
                'confirm': node.confirm_tag,
                'transcript_length': len(node.transcript),
                'commit1': node.commit1.hex(),
                'commit2': node.commit2.hex(),
                'rho1': node.rho1.hex(),
                'rho2': node.rho2.hex(),
            }
        self._capture["nodes_full"] = result["nodes"]
        self._capture["result"] = result
        # Byte-exact full transcript and hash
        self._capture["full_transcript_ordered_hex"] = [b.hex() for b in self._transcript_ordered]
        import hashlib
        self._capture["transcript_hash_sha3_512"] = hashlib.sha3_512(b"".join(self._transcript_ordered)).hexdigest()
        return result


