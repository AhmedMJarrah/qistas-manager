"""Explicit parent/child type filters. Never reclassifies or confirms source edges."""
from common import norm,node_search_text
PRESETS={
 'تخصيص':([],[]),
 'الأنظمة الصادرة بموجب القوانين':(['قانون'],['نظام']),
 'التعليمات الصادرة بموجب الأنظمة':(['نظام'],['تعليمات']),
 'القوانين المرتبطة بالدستور':(['دستور'],['قانون']),
 'كل العلاقات':([],[]),
}
def filter_edges(g,parent_types=(),child_types=(),statuses=(),article='',query=''):
 result=[]
 for e in g['edges']:
  parent=g['nodes'][e['parent']];child=g['nodes'][e['child']]
  if parent_types and parent['kind'] not in parent_types:continue
  if child_types and child['kind'] not in child_types:continue
  if statuses and e['status'] not in statuses:continue
  if query and norm(query) not in norm(node_search_text(parent)+' '+node_search_text(child)+' '+e['id']):continue
  if article:
   values=[str(x.get('article','')) for x in e['evidence'] if x.get('article')]
   # Also parse explicit article markers from the parent-list issuance clause.
   import re
   values.extend(re.findall(r'الماد(?:ة|ه)\s*\(?\s*(\d+)',norm(e.get('basis',''))))
   if norm(article).strip() not in {norm(v).strip() for v in values}:continue
  result.append(e)
 return result

def render_type_browser(g,statuses=()):
 import streamlit as st,json,hashlib
 from common import follow
 from ui_components import section_title,instruction_line
 kinds=sorted({n['kind'] for n in g['nodes'].values()})
 def apply_preset():
  p,c=PRESETS[st.session_state['relation_preset']]
  st.session_state['pair_parents']=[x for x in p if x in kinds];st.session_state['pair_children']=[x for x in c if x in kinds]
  st.session_state.pop('pair_page',None)
 with st.container(border=True):
  st.selectbox('اختيار سريع',list(PRESETS),key='relation_preset',on_change=apply_preset)
  a,b=st.columns(2)
  with a:parents=st.multiselect('أنواع التشريع الأب',kinds,key='pair_parents',help='اختيار أكثر من نوع ممكن. فارغ يعني كل الأنواع.')
  with b:children=st.multiselect('أنواع التشريع الابن',kinds,key='pair_children',help='مثال: الأب قانون والابن نظام.')
  a,b=st.columns([3,1])
  with a:q=st.text_input('بحث داخل الآباء والأبناء',key='pair_query',icon=':material/search:')
  with b:art=st.text_input('رقم المادة',key='pair_article',placeholder='اختياري')
 matches=filter_edges(g,parents,children,statuses,art,q)
 fingerprint=hashlib.sha256(json.dumps([parents,children,list(statuses),art,q],ensure_ascii=False).encode()).hexdigest()
 if st.session_state.get('tree_filter_signature')!=fingerprint:
  st.session_state['tree_filter_signature']=fingerprint
  st.session_state['tree_parent_page']=1
  for key in list(st.session_state):
   if str(key).startswith(('tree_expand_','tree_child_page_')):st.session_state.pop(key,None)
 section_title('شجرة العلاقات المطابقة',len(matches),'كل تشريع أب يظهر مرة واحدة، وتحته أبناؤه المطابقون للفلاتر')
 instruction_line('افتح فرع الأب لعرض أبنائه، أو افتح تشريع الابن لاستكشاف آبائه وأبنائه. التجميع حسب المعرّف؛ يحتفظ كل سجل علاقة بحالته ودليله.')
 def jump(node_id):st.session_state['browse_mode']='LEGISLATION';follow(node_id)
 if matches:
  from relationship_tree import render_relationship_tree
  render_relationship_tree(g,matches,jump)
  export=[dict(edge_id=e['id'],parent_id=e['parent'],parent_name=g['nodes'][e['parent']]['name'],parent_number=g['nodes'][e['parent']]['number'],parent_year=g['nodes'][e['parent']]['year'],parent_original_name=g['nodes'][e['parent']]['original_name'],parent_type=g['nodes'][e['parent']]['kind'],child_id=e['child'],child_name=g['nodes'][e['child']]['name'],child_number=g['nodes'][e['child']]['number'],child_year=g['nodes'][e['child']]['year'],child_original_name=g['nodes'][e['child']]['original_name'],child_type=g['nodes'][e['child']]['kind'],status=e['status'],issued_art=e['basis'],basis_articles=e['evidence']) for e in matches]
  st.download_button('تنزيل النتائج المصفاة JSON',json.dumps({'dataset':'EXTRACTED_ONLY','dataset_version':g['version'],'relations':export},ensure_ascii=False,indent=2).encode(),file_name='filtered_relationships.json',mime='application/json',icon=':material/download:')
 else:st.info('لا توجد علاقات مطابقة لهذه الفلاتر في الشبكة الحالية. لا يعني ذلك غيابها قانونياً.')
