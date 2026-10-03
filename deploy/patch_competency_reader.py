"""Patch the installed competency hook, preserving all other behavior.

Run against the active module AND its persistent deployment source after backup.
The service still needs ordinary Frappe read permissions; this hook cannot grant them.
"""
import sys
from pathlib import Path
p=Path(sys.argv[1]);s=p.read_text()
marker='# Dedicated MCP reader: role permissions still enforce read-only.'
if marker in s:
    print('Already patched');raise SystemExit(0)
needle='def document_permission(doc, ptype=None, user=None, permission_type=None):\n'
if s.count(needle)!=1: raise RuntimeError('Unexpected hook signature; review manually')
backup=p.with_suffix(p.suffix+'.before-mcp')
if backup.exists(): raise RuntimeError('Backup already exists; review before patching')
backup.write_text(s)
s=s.replace(needle,needle+"    # Dedicated MCP reader: role permissions still enforce read-only.\n    if (user or frappe.session.user) == 'lms-mcp-reader@paper-planes.ru' and (ptype or permission_type) in ('read', 'select'):\n        return True\n",1)
compile(s,str(p),'exec');p.write_text(s);print('Patched read/select for service user')
