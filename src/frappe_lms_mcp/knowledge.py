"""Permission-respecting REST retrieval and bounded full-content search."""
import json
import os
from .tools import get_client
from .client import FrappeAPIError
from .text import plain_text

DEFAULT_SCHEMAS = {
    'Wiki Document': {'title':'title','content':'content','category':'parent_wiki_document','published':'is_published'},
    'Wiki Page': {'title':'title','content':'content','published':'published'},
    'Help Article': {'title':'title','content':'content','category':'category','published':'published'},
}

def schemas():
    available = {**DEFAULT_SCHEMAS, **json.loads(os.getenv('KB_FIELD_MAP', '{}'))}
    result={}
    for dt in os.getenv('KB_DOCTYPES','Wiki Document').split(','):
        dt=dt.strip()
        if dt not in available: raise ValueError('Configure KB_FIELD_MAP for custom DocType')
        result[dt]=available[dt]
    return result

def kb_filters(schema, category=''):
    filters=[[schema['published'],'=',1]] if schema.get('published') else []
    if category:
        if not schema.get('category'): return None
        filters.append([schema['category'],'=',category])
    return filters

def article(dt, row, schema):
    return {'name':dt+'::'+row['name'], 'doctype':dt,'document_name':row['name'],
        'title':row.get(schema['title'],''), 'category':row.get(schema.get('category',''),''),
        'content':plain_text(row.get(schema['content'],''))}

def search_rows(dt, fields, filters, query, limit=50):
    client=get_client()
    # REST or_filters searches all records server-side; never silently scan just the first page.
    params={'fields':json.dumps(fields),'filters':json.dumps(filters),
            'limit_page_length':limit+1,'order_by':'modified desc'}
    if query:
        params['or_filters']=json.dumps([[field,'like','%'+query+'%'] for field in fields if field not in {'name','parent_wiki_document'}])
    from urllib.parse import quote
    return client._request('GET','/api/resource/'+quote(dt,safe=''),params=params)['data']

def list_kb_articles(query='', category='', limit=50):
    limit=max(1,min(200,limit)); result=[]; truncated=False
    for dt,schema in schemas().items():
        filters=kb_filters(schema,category)
        if filters is None: continue
        fields=list(dict.fromkeys(['name',schema['title'],schema['content']]+([schema['category']] if schema.get('category') else [])))
        rows=search_rows(dt,fields,filters,query,limit)
        result.extend(article(dt,row,schema) for row in rows[:limit])
        truncated |= len(rows)>limit
    return {'articles':result[:limit], 'truncated':truncated or len(result)>limit}

def get_kb_article(name):
    configured=schemas()
    if '::' in name:
        dt,name=name.split('::',1)
        if dt not in configured: raise ValueError('DocType is not configured')
    elif len(configured)==1: dt=next(iter(configured))
    else: raise ValueError('Use a qualified DocType::name ID')
    schema=configured[dt]
    row=get_client().get_doc(dt,name)['data']
    if schema.get('published') and not row.get(schema['published']):
        raise FrappeAPIError('Article is not published',404)
    return article(dt,row,schema)

def search_lms(query):
    query=query.strip()
    if not query or len(query)>200: raise ValueError('Query must have 1-200 characters')
    results=[]; truncated=False
    for dt,fields in [('LMS Course',['name','title','short_introduction','description']),
                       ('Course Lesson',['name','title','content','body'])]:
        rows=search_rows(dt,fields,[],query)
        truncated |= len(rows)>50
        for row in rows[:50]:
            text='\n'.join(plain_text(row.get(f,'')) for f in fields[2:])
            pos=text.casefold().find(query.casefold()); start=max(0,pos-120)
            results.append({'doctype':dt,'name':row['name'],'title':row['title'],'excerpt':text[start:start+700]})
    kb=list_kb_articles(query=query)
    for row in kb['articles']:
        body=row.pop('content'); pos=body.casefold().find(query.casefold()); start=max(0,pos-120)
        row['excerpt']=body[start:start+700]; results.append(row)
    return {'results':results,'truncated':truncated or kb['truncated']}
