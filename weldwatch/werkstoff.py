import re
from .config import DEFAULTS

_GROUP = re.compile(r"^\(\s*(\d{1,2})(?:\s*([/+])\s*(\d{1,2}))?\s*\)$")

def parse_group_token(tok):
    """'(22)' -> [22]; '(1/8)' oder '(1+8)' -> [1, 8]; sonst None"""
    m = _GROUP.match(tok.strip())
    if not m:
        return None
    g = [int(m.group(1))]
    if m.group(3):
        g.append(int(m.group(3)))
    return g

def format_groups(groups, cfg=DEFAULTS):
    """Werkstoffgruppen als Text. Alu (22/23) immer als 'Gr.22/23'. Keine Angabe -> Gr.1."""
    if not groups:
        groups = [cfg["default_group"]]
    out, seen = [], set()
    for g in groups:
        txt = cfg["alu_text"] if g in cfg["gr_alu"] else f"Gr.{g}"
        if txt not in seen:
            out.append(txt); seen.add(txt)
    return " + ".join(out)
