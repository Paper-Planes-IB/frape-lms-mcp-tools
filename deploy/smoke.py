"""Exercise live MCP protocol, printing counts and booleans only."""
import asyncio,json,os,sys
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    url=sys.argv[1]; token=os.environ['MCP_AUTH_TOKEN']
    async with httpx.AsyncClient() as c:
        denied=await c.post(url,json={})
        assert denied.status_code==401, denied.status_code
    async with streamablehttp_client(url,headers={'Authorization':'Bearer '+token}) as (read,write,_):
        async with ClientSession(read,write) as session:
            await session.initialize()
            names={t.name for t in (await session.list_tools()).tools}
            assert len(names)==14 and 'delete_course' not in names and 'create_course' not in names
            async def call(name,args={}):
                response=await session.call_tool(name,args)
                if response.isError: raise RuntimeError(name+': '+str(response.content))
                return json.loads(response.content[0].text)
            courses=await call('list_courses',{'limit':200}); assert courses
            course=await call('get_course',{'course':courses[0]['name']})
            lesson=None
            for ch in course.get('outline',[]):
                if ch.get('lessons'):
                    chapter=await call('get_chapter',{'chapter':ch['name']})
                    lesson=await call('get_lesson',{'lesson':chapter['lessons'][0]['lesson']});break
            assert lesson is not None and isinstance(lesson.get('content'),str)
            quizzes=await call('list_quizzes',{'limit':200}); assert quizzes
            await call('get_quiz',{'quiz':quizzes[0]['name']})
            await call('list_enrollments',{'limit':1}); await call('list_batches')
            articles=await call('list_kb_articles'); assert articles['articles']
            assert all(set(row)=={'name','title','category','snippet'} and len(row['snippet'])<=300 for row in articles['articles'])
            list_bytes=len(json.dumps(articles,ensure_ascii=False).encode())
            article=await call('get_kb_article',{'name':articles['articles'][0]['name']});assert article['content']
            search=await call('search_lms',{'query':'BPM'});assert search['results']
            imported=await call('import_course_from_frappe',{'course_slug':courses[0]['name']});assert imported['ok']
            await call('list_cached_courses'); await call('get_cached_course',{'course_id':imported['cached']['id']})
            for name in ['create_course','delete_course']:
                bad=await session.call_tool(name,{'course':'nonexistent'}); assert bad.isError
            print(json.dumps({'unauthorized':401,'tools':sorted(names),'courses':len(courses),'quizzes':len(quizzes),
                  'lesson_text':True,'wiki_content':True,'article_count':len(articles['articles']),'article_list_bytes':list_bytes,'full_article_characters':len(article['content']),'search_results':len(search['results']),'cache':True,'writes_absent':True}))

asyncio.run(main())
