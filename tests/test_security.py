import importlib
import json
import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.testclient import TestClient
from frappe_lms_mcp.security import AuthMiddleware
from frappe_lms_mcp.client import FrappeClient,FrappeAPIError
from frappe_lms_mcp.text import plain_text

@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv('MCP_AUTH_TOKEN','a'*48)
    monkeypatch.setenv('MCP_READ_ONLY','1')
    monkeypatch.setenv('FRAPPE_URL','https://lms.example.com')
    monkeypatch.setenv('FRAPPE_API_KEY','test-key')
    monkeypatch.setenv('FRAPPE_API_SECRET','test-secret')
    monkeypatch.delenv('MCP_ALLOW_QUERY_TOKEN',raising=False)

def app():
    async def ok(request): return JSONResponse({'ok':True})
    return AuthMiddleware(Starlette(routes=[Route('/mcp',ok,methods=['GET','POST','DELETE']),Route('/health',ok),Route('/sse',ok),Route('/messages/',ok,methods=['POST'])]))

@pytest.mark.parametrize('method,path',[('GET','/mcp'),('POST','/mcp'),('DELETE','/mcp'),('GET','/sse'),('POST','/messages/')])
def test_no_token(method,path):
    assert TestClient(app()).request(method,path).status_code==401

def test_auth(monkeypatch):
    c=TestClient(app())
    assert c.get('/health').status_code==200
    assert c.get('/mcp',headers={'Authorization':'Bearer '+'a'*48}).status_code==200
    assert c.get('/mcp?token='+'a'*48).status_code==401
    monkeypatch.setenv('MCP_ALLOW_QUERY_TOKEN','1')
    c=TestClient(app())
    assert c.get('/mcp?token='+'a'*48).status_code==200
    assert c.get('/mcp?token='+'a'*48,headers={'Authorization':'Bearer wrong'}).status_code==401
    assert c.get('/mcp?token='+'a'*48+'&token=wrong').status_code==401

def test_missing_token(monkeypatch):
    monkeypatch.delenv('MCP_AUTH_TOKEN')
    with pytest.raises(ValueError): app()

def test_tools():
    import asyncio
    from frappe_lms_mcp import server
    names={t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names==server.READ_TOOLS
    from mcp.server.fastmcp.exceptions import ToolError
    with pytest.raises(ToolError,match='Unknown tool'):
        asyncio.run(server.mcp.call_tool('delete_course',{'course':'x'}))

@pytest.mark.parametrize('method',['POST','PUT','DELETE','PATCH'])
def test_client_write_blocked(method):
    c=FrappeClient()
    with pytest.raises(FrappeAPIError,match='Read-only'): c._request(method,'/api/resource/LMS Course')
    with pytest.raises(FrappeAPIError,match='Read-only'): c.call_method('anything')
    c.close()

def test_token_only(monkeypatch):
    monkeypatch.delenv('FRAPPE_API_SECRET');monkeypatch.setenv('FRAPPE_PASSWORD','not-allowed')
    with pytest.raises(FrappeAPIError): FrappeClient()

def test_path_escaping():
    c=FrappeClient(); calls=[]
    def reply(request):
        calls.append(request)
        return httpx.Response(200,json={'data':{'name':'x'}})
    c._client.close();c._client=httpx.Client(transport=httpx.MockTransport(reply))
    c.get_doc('Course Lesson','abc?token=leak#frag')
    assert calls[0].url.query==b''
    assert b'%3F' in calls[0].url.raw_path
    c.close()

def test_text():
    body=json.dumps({'blocks':[{'type':'header','data':{'text':'Title','level':2}},
        {'type':'paragraph','data':{'text':'<b>Hello</b> <script>bad</script>world'}},
        {'type':'list','data':{'items':[{'content':'Nested','items':['Child']}]}}]})
    result=plain_text(body)
    assert '## Title' in result and 'Hello' in result and 'Nested' in result and 'Child' in result
    assert 'bad' not in result and 'blocks' not in result

def test_search_queries_full_content(monkeypatch):
    from frappe_lms_mcp import knowledge
    calls=[]
    class Fake:
        def _request(self,method,path,params):
            calls.append((method,path,params));return {'data':[]}
    monkeypatch.setattr(knowledge,'get_client',lambda:Fake())
    knowledge.search_lms('needle')
    assert len(calls)==3
    assert all(x[0]=='GET' for x in calls)
    assert 'content' in calls[1][2]['or_filters'] and 'body' in calls[1][2]['or_filters']
    assert 'is_published' in calls[2][2]['filters']
