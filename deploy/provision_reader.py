"""Run inside the Frappe bench after a verified database backup. Prints no credentials."""
import json
import os
import secrets
from pathlib import Path
import frappe
from frappe.permissions import add_permission

SITE = os.environ.get('FRAPPE_SITE','lms.178.130.50.200.sslip.io')
USER = 'lms-mcp-reader@paper-planes.ru'
ROLE = 'PP MCP Reader'
DOCTYPES = ['LMS Course','Course Chapter','Course Lesson','LMS Quiz','LMS Question',
            'LMS Enrollment','LMS Batch','Wiki Document']
frappe.init(site=SITE,sites_path='sites'); frappe.connect()
try:
    snapshot=Path('/tmp/mcp-permissions-before.json')
    if not snapshot.exists():
        snapshot.write_text(json.dumps({dt:[r.as_dict() for r in frappe.get_meta(dt).permissions] for dt in DOCTYPES},default=str))
        snapshot.chmod(0o600)
    if not frappe.db.exists('Role',ROLE):
        frappe.get_doc({'doctype':'Role','role_name':ROLE,'desk_access':0}).insert(ignore_permissions=True)
    for dt in DOCTYPES:
        if not frappe.db.exists('Custom DocPerm',{'parent':dt,'role':ROLE}):
            add_permission(dt,ROLE,ptype='read')
    if frappe.db.exists('User',USER):
        raise RuntimeError('Service user exists; inspect it before changing credentials')
    user=frappe.get_doc({'doctype':'User','email':USER,'first_name':'LMS MCP Reader',
        'enabled':0,'user_type':'System User','send_welcome_email':0,
        'roles':[{'role':ROLE}]})
    user.flags.no_welcome_mail=True
    user.insert(ignore_permissions=True)
    user.api_key=secrets.token_hex(16)
    user.api_secret=secrets.token_hex(32)
    user.set('roles', [{'role':ROLE}])
    user.save(ignore_permissions=True)
    frappe.db.set_value('User',USER,'enabled',1)
    payload={'FRAPPE_API_KEY':user.api_key,'FRAPPE_API_SECRET':user.get_password('api_secret')}
    path=Path('/tmp/mcp-reader-credentials.json'); path.write_text(json.dumps(payload)); path.chmod(0o600)
    frappe.db.commit();frappe.clear_cache(user=USER)
    actual=frappe.get_roles(USER)
    assert 'System Manager' not in actual and 'Administrator' not in actual
    for dt in DOCTYPES:
        assert frappe.has_permission(dt,'read',user=USER), dt
        for permission in ['write','create','delete','share','submit']:
            assert not frappe.has_permission(dt,permission,user=USER),(dt,permission)
    print(json.dumps({'user':USER,'roles':actual,'doctypes':DOCTYPES,'read_only_verified':True}))
finally:
    frappe.destroy()
