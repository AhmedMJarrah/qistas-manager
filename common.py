from pathlib import Path
import csv,json,re,html,gzip,collections,hashlib
import streamlit as st
ROOT=Path(__file__).resolve().parent
LABELS={'VERIFIED_STRUCTURAL':'مطابق بنيوياً','CONFIRMED_IDENTITY_ERROR':'تعارض هوية مؤكد','REVIEW_REQUIRED':'بحاجة مراجعة','NO_CANDIDATE':'غير محسوم','CANDIDATE_ONLY':'مرشح'}
KINDS={'LAW':'قانون','BYLAW':'نظام','CONSTITUTION':'دستور','INSTRUCTION':'تعليمات','AGREEMENT':'اتفاقية','AMENDMENT':'تعديل','RULE':'حكم قضائي','EXPLANATION':'تفسير'}
def clean(t):return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]*>',' ',t or ''))).strip()
def norm(t):return clean(t).replace('أ','ا').replace('إ','ا').replace('آ','ا').replace('ـ','').translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789')).lower()
def valid(v):return v not in ('','NULL','0',None)
def ident(e):return '|'.join(e[k] for k in ('Entity_Type','pmk_ID','GUID'))

def legislation_title(value):
 """Extract explicit title/number/year without guessing or rewriting source names."""
 original=clean(value)
 digits=str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹','01234567890123456789')
 result=dict(name=original,original_name=original,number='',year='',name_review_required=False)
 prefix=re.match(r'^(?:قانون|نظام|تعليمات|قرار|جدول|ملحق|اتفاقية|تعميم|بلاغ|بيان|دستور|إعلان|اعلان|لائحة|قواعد)(?:\s+رقم\s+(?P<number>[0-9٠-٩۰-۹]+(?:/[0-9٠-٩۰-۹]+)?))?\s+لسنة\s+(?P<year>[0-9٠-٩۰-۹]{4})(?=\s|\(|$)',original)
 if not prefix:
  # A title with an explicit trailing year has no implied legislation number.
  year=re.search(r'لسنة\s+([0-9٠-٩۰-۹]{4})\s*$',original)
  if year:result['year']=year.group(1).translate(digits)
  return result
 result['number']=(prefix.group('number') or '').translate(digits)
 result['year']=prefix.group('year').translate(digits)
 remaining=original[prefix.end():].strip()
 if not remaining.startswith('('):return result
 depth=0;closing=None
 for index,char in enumerate(remaining):
  if char=='(':depth+=1
  elif char==')':
   depth-=1
   if depth==0:closing=index;break
 if closing is None:
  result['name_review_required']=True;return result
 title=remaining[1:closing].strip();suffix=remaining[closing+1:].strip()
 years=[x.translate(digits) for x in re.findall(r'لسنة\s+([0-9٠-٩۰-۹]{4})',title)]
 if not title or suffix.startswith('(') or (years and years[-1]!=result['year']):
  result['name_review_required']=True;return result
 # Keep qualifiers such as "معدل", "مؤقت", and "وتعديلاته" exactly as supplied.
 if suffix and not title.endswith(suffix):title+=' '+suffix
 result['name']=title
 return result

def node_search_text(node):
 return ' '.join(str(node.get(field,'')) for field in ['name','original_name','number','year','kind','id'])

def design(title):
 st.set_page_config(page_title=title,page_icon=':material/account_tree:',layout='wide',initial_sidebar_state='expanded')
 st.markdown('<style>'+ (ROOT/'styles.css').read_text(encoding='utf-8') +'</style>',unsafe_allow_html=True)
 with st.sidebar:
  st.markdown('<div class="brand"><strong>مِعيار</strong><small>التشريع ضمن شبكة علاقاته</small></div>',unsafe_allow_html=True)

def edge_id(prefix,value):return prefix+'-'+hashlib.sha256(value.encode()).hexdigest()[:24]
@st.cache_resource(show_spinner='تحميل الشبكة المستخرجة…')
def load_extracted():
 path=ROOT/'legislation_graph.json';d=json.loads(path.read_text(encoding='utf-8'));nodes={k:dict(id=k,**legislation_title(r['name']),kind=r.get('kind') or 'غير مصنف',pmk='',guid='',deleted=False,historical=False,modleg='',source='شبكة مستخرجة',raw=r) for k,r in d['nodes'].items()};edges=[]
 for i,r in enumerate(d['edges'],1):
  edges.append(dict(id=edge_id('S',f"{r['parent']}|{r['child']}|{i}"),parent=r['parent'],child=r['child'],status='CANDIDATE_ONLY' if r['agreement']=='both' else 'REVIEW_REQUIRED',source='شبكة مستخرجة',row=str(i),article='، '.join(str(a.get('article','')) for a in r['basis_articles']),basis=r['issued_art'],deleted=False,historical=False,raw=r,evidence=r['basis_articles']))
 return indexed(nodes,edges,[],d['meta'],hashlib.sha256(path.read_bytes()).hexdigest()[:24],{})
def indexed(nodes,edges,associated,meta,version,candidates):
 parents=collections.defaultdict(list);children=collections.defaultdict(list)
 for e in edges:parents[e['child']].append(e);children[e['parent']].append(e)
 ai=collections.defaultdict(list)
 for a in associated:
  for k in set(a['owners']+a['candidates']):ai[k].append(a)
 search={k:norm(node_search_text(n)+' '+str(n.get('pmk',''))+' '+str(n.get('guid',''))) for k,n in nodes.items()}
 return dict(nodes=nodes,edges=edges,parents=parents,children=children,associated=associated,associated_index=ai,meta=meta,version=version,candidates=candidates,search=search,edge_by_id={e['id']:e for e in edges})
def source_selector(key):
 st.sidebar.markdown('### مجموعة البيانات')
 st.sidebar.markdown('<div class="reviewer-info"><small>المجموعة المستخدمة الآن</small><strong>شبكة التشريعات المستخرجة</strong></div>',unsafe_allow_html=True)
 st.sidebar.caption('العرض والمراجعة على الشبكة المستخرجة فقط. بيانات الديوان مؤجلة ومنفصلة.')
 return 'EXTRACTED',load_extracted()

def follow(node_id):
 st.session_state['picked']=node_id;st.session_state['search']='';st.session_state['kind']='الكل';st.session_state['selector']=node_id
 for k in ['parents_page','children_page']:st.session_state.pop(k,None)

def identity_card(n):
 with st.container(border=True):
  name=clean(n['name']);pill=html.escape(n['kind'])+' · '+html.escape(n['source'])
  st.markdown('<div class="identity-head"><span class="type-pill">'+pill+'</span><h2>'+html.escape(name[:700])+'</h2></div>',unsafe_allow_html=True)
  cols=st.columns(5)
  fields=[('الرقم',n['number'] or 'غير محدد'),('السنة',n['year'] or 'غير محددة'),('معرف الديوان' if n['pmk'] else 'مفتاح المصدر',n['pmk'] or n['id']),('GUID',n['guid'] or 'غير متاح'),('ModLeg',n['modleg'] or 'غير متاح في التصدير')]
  for c,(label,value) in zip(cols,fields):
   with c:st.markdown('<div class="identity-data"><small>'+html.escape(label)+'</small><strong class="'+('guid' if label=='GUID' else '')+'">'+html.escape(value)+'</strong></div>',unsafe_allow_html=True)
  if n['deleted'] or n['historical']:st.caption('مؤشر حذف / تاريخية محفوظ في التصدير.')
  if n.get('name_review_required'):st.caption('صيغة العنوان تحتاج مراجعة؛ عُرض الاسم كما ورد في المصدر.')
  if n.get('original_name') and n['original_name']!=n['name']:
   with st.expander('العنوان كما ورد في المصدر',icon=':material/article:'):st.text(n['original_name'])
  if len(name)>700:
   with st.expander('عرض العنوان كاملاً',icon=':material/article:'):st.text(name)

def show_evidence(e):
 st.caption(f"{e['source']} · سجل {e['row']} · {LABELS[e['status']]}")
 if e['basis']:st.write(e['basis'])
 for a in e['evidence']:st.write(a.get('text',''))
 st.caption('اتجاه الرابط مستخرج من البيانات؛ صحة الأساس القانوني والنسخة تحتاج مراجعة الدليل.')
 with st.expander('بيانات المرجع كاملة',icon=':material/data_object:'):st.json(e['raw'])

def show_links(g,es,other,prefix,compact=False):
 from ui_components import relation_header,pager
 if not es:st.info('لا تظهر علاقات ضمن التصدير والفلاتر الحالية؛ لا يعني ذلك انعدام العلاقة القانونية.',icon=':material/info:');return
 page_size=12 if not compact else 20
 page=pager(len(es),page_size,prefix+'_page') if len(es)>page_size else 1
 for e in es[(page-1)*page_size:page*page_size]:
  n=g['nodes'][e[other]]
  with st.container(border=True):
   relation_header(clean(n['name']),n['kind'],e['status'],e['article'],n['number'],n['year'])
   st.button('فتح التشريع',key=prefix+'_'+e['id'],on_click=follow,args=(n['id'],),width='stretch',icon=':material/arrow_back:',help='انتقل إلى بطاقة هذا التشريع وعرض علاقاته')
   if not compact:
    with st.expander('المصدر والدليل',icon=':material/menu_book:'):show_evidence(e)
