import os,json,re,html,urllib.request,urllib.parse,xml.etree.ElementTree as ET,datetime,email.utils,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DOCS=ROOT/'docs'; DOCS.mkdir(exist_ok=True)
TZ=datetime.timezone(datetime.timedelta(hours=9)); now=datetime.datetime.now(TZ)
FEEDS=[('AI / LLM','AI LLM agents OpenAI Google Anthropic'),('Automation','AI agent enterprise workflow automation'),('Commerce','agentic commerce ecommerce retail AI'),('Korea','한국 이커머스 AI 에이전트 쇼핑')]
def fetch(url,timeout=20):
 req=urllib.request.Request(url,headers={'User-Agent':'AIDailyBriefing/1.0 (RSS reader)','Accept':'application/rss+xml,application/xml,text/xml,*/*'})
 with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()
def strip(s):return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',s or ''))).strip()[:650]
def collect():
 items=[];seen=set()
 for category,q in FEEDS:
  url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':q+' when:3d','hl':'ko','gl':'KR','ceid':'KR:ko'})
  try:
   root=ET.fromstring(fetch(url))
   for node in root.findall('.//item')[:18]:
    def v(tag):return (node.findtext(tag) or '').strip()
    title=strip(v('title'));link=v('link');description=strip(v('description'))
    if not title or not link or title.lower() in seen:continue
    seen.add(title.lower());items.append({'category':category,'title':title,'url':link,'summary':description,'published':v('pubDate')})
  except Exception as e:print('RSS warning:',category,str(e))
 return items[:65]
def generate(items):
 key=os.environ.get('GEMINI_API_KEY','').strip()
 if not key:raise RuntimeError('GEMINI_API_KEY missing')
model=os.environ.get('GEMINI_MODEL','gemini-3.5-flash-lite').strip()
 prompt='''당신은 한국 쇼핑몰 MD를 위한 AI 기술 뉴스 편집자입니다. 제공된 RSS 제목/요약/링크만을 근거로 중요 뉴스 5건을 선정하세요. 출처에 없는 사실, 수치, 인용, 기능, 날짜를 만들어내지 마세요. 최근 기사와 서로 다른 이슈를 우선하고 광고성 기사/중복을 피하세요. 제공된 링크를 그대로 사용하세요. RSS만으로 확인 불가능한 내용은 단정하지 마세요. 반드시 JSON 객체만 출력하세요. 스키마: {"headline":"오늘의 핵심 한 문장","items":[{"source_index":0,"title":"간결한 한국어 제목","summary":"확인된 핵심 사실 2문장","why_it_matters":"행사 일정, 판매자 자료 취합, 메일 응대, 상품 검증 등 MD 업무에 왜 중요한지 1~2문장","action":"실행 가능한 제안 1문장"}]} . 정확히 5개, source_index는 제공된 자료의 index입니다. 자료는 다음과 같습니다:\n'''+json.dumps([{'index':i,**x} for i,x in enumerate(items)],ensure_ascii=False)
 endpoint='https://generativelanguage.googleapis.com/v1beta/models/'+urllib.parse.quote(model,safe='')+':generateContent'
 payload={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'responseMimeType':'application/json','temperature':0.25,'maxOutputTokens':2800}}
 req=urllib.request.Request(endpoint,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key},method='POST')
 with urllib.request.urlopen(req,timeout=100) as r:result=json.load(r)
 raw=''.join(p.get('text','') for p in result['candidates'][0]['content']['parts'])
 parsed=json.loads(raw);used=set();out=[]
 for x in parsed.get('items',[]):
  i=x.get('source_index')
  if not isinstance(i,int) or i<0 or i>=len(items) or i in used:continue
  used.add(i);source=items[i]
  out.append({'title':str(x.get('title',''))[:160],'summary':str(x.get('summary',''))[:700],'why_it_matters':str(x.get('why_it_matters',''))[:600],'action':str(x.get('action',''))[:350],'url':source['url'],'source':source['title'],'published':source['published'],'category':source['category']})
 if len(out)!=5:raise ValueError('Model returned fewer than five valid unique items')
 return {'date':now.date().isoformat(),'generated_at':now.isoformat(),'headline':str(parsed.get('headline',''))[:300],'items':out,'note':'RSS 기사 제목과 요약을 기반으로 AI가 작성했습니다. 원문에서 상세 사실을 확인하세요.'}
def main():
 items=collect();print('RSS candidates:',len(items))
 if len(items)<5:raise RuntimeError('Not enough RSS candidates; preserving previous briefing')
 data=generate(items)
 (DOCS/'briefing.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Wrote docs/briefing.json for',data['date'])
if __name__=='__main__':main()
