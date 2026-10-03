"""Convert HTML and EditorJS to readable text without fetching embedded URLs."""
import json
from html.parser import HTMLParser

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.hidden=0
    def handle_starttag(self, tag, attrs):
        if tag in {'script','style'}: self.hidden += 1
        if tag in {'p','br','div','li','tr','h1','h2','h3'}: self.parts.append('\n')
        if tag == 'a':
            self.parts.append(' ' + dict(attrs).get('href','') + ' ')
    def handle_endtag(self, tag):
        if tag in {'script','style'}: self.hidden=max(0,self.hidden-1)
        if tag in {'p','div','li','tr'}: self.parts.append('\n')
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)

def html_text(value):
    p=TextParser(); p.feed(str(value)); return ''.join(p.parts).strip()

def flatten(value):
    if isinstance(value, str): return html_text(value)
    if isinstance(value, list): return '\n'.join(flatten(x) for x in value)
    if isinstance(value, dict):
        return '\n'.join(flatten(v) for k,v in value.items() if k in {
            'text','content','items','caption','url','source','embed','code','markdown','title','file','quiz'})
    return ''

def plain_text(value):
    if not value: return ''
    parsed=value
    if isinstance(value,str):
        try: parsed=json.loads(value)
        except (ValueError,TypeError): return html_text(value)
    if not isinstance(parsed,dict) or 'blocks' not in parsed:
        return flatten(parsed)
    chunks=[]
    for block in parsed.get('blocks',[]):
        data=block.get('data',{}); kind=block.get('type','')
        if kind=='header': chunks.append('#'*max(1,min(6,int(data.get('level',2))))+' '+html_text(data.get('text','')))
        elif kind=='code': chunks.append('```\n'+str(data.get('code',''))+'\n```')
        else: chunks.append(flatten(data))
    return '\n\n'.join(x for x in chunks if x)
