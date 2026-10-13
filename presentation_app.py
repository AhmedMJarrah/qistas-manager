"""Read-only presentation app: no review database or mutation controls."""
import streamlit as st
from common import *
from ui_components import hero,metrics,section_title,source_note,instruction_line
from relationship_filters import render_type_browser
design('مِعيار | استكشاف شبكة التشريعات')
hero('كل تشريع، ضمن شبكة علاقاته.','ابحث عن التشريع، استعرض آباءه وأبناءه، ثم انتقل بينهم بنقرة واحدة.','واجهة العرض أمام المدير')
source,g=source_selector('presentation_source')
mode=st.segmented_control('طريقة الاستعراض',['LEGISLATION','RELATIONSHIPS'],default='LEGISLATION',format_func=lambda x:':material/account_tree: تشريع وآباؤه وأبناؤه' if x=='LEGISLATION' else ':material/filter_alt: حسب نوع الأب والابن',width='stretch',key='browse_mode')
if st.session_state.get('last_source')!=source:
 st.session_state['last_source']=source
 for k in ['picked','selector','search','kind','parents_page','children_page','last_node','nav_history']:st.session_state.pop(k,None)
metrics([('سجلات التشريعات',f"{g['meta'].get('entities',len(g['nodes'])):,}",'تضم النسخ والتعديلات المتاحة','navy'),('العلاقات المباشرة',f"{len(g['edges']):,}",'ضمن المجموعة المختارة','teal'),('أنواع التشريعات',str(len({n['kind'] for n in g['nodes'].values() if n['kind']})),'يمكن تصفية الأب والابن حسب النوع','purple')])
source_note(source)
with st.sidebar:
 st.divider();st.markdown('### تصفية النتائج')
 kind=st.selectbox('نوع التشريع',['الكل']+sorted({n['kind'] for n in g['nodes'].values()}),key='kind')
 flags=st.checkbox('تضمين التاريخية والمحذوفة',value=True,key='show_history')
 statuses=st.multiselect('حالات الرابط',list(LABELS),format_func=LABELS.get,help='اتركه فارغاً لعرض جميع الحالات',key='status_filter')
 compact=st.toggle('عرض موجز للبطاقات',value=False,help='يقلل التفاصيل عند العرض أمام المدير',key='compact_view')
 def reset_filters():
  for key in ['search','kind','show_history','status_filter','compact_view']:st.session_state.pop(key,None)
 st.button('إعادة ضبط الفلاتر',icon=':material/filter_alt_off:',width='stretch',on_click=reset_filters)
 st.caption('واجهة للعرض فقط؛ لا تغيّر البيانات ولا تستقبل قرارات المراجعة.')
if mode=='RELATIONSHIPS':
 render_type_browser(g,statuses)
 st.stop()
with st.container(key='search_panel'):
 a,b=st.columns([4,1])
 with a:q=st.text_input('ابحث عن التشريع',key='search',placeholder='الاسم، الرقم، السنة، المعرف أو GUID…',icon=':material/search:')
 opts=[k for k,n in g['nodes'].items() if (kind=='الكل' or n['kind']==kind) and (flags or not(n['deleted'] or n['historical'])) and (not q or norm(q) in g['search'][k])]
 with b:st.caption('نتائج البحث');st.markdown(f'### {len(opts):,}')
 if not opts:st.warning('لا يوجد تشريع مطابق. جرّب اسماً أقصر أو أعد ضبط الفلاتر.',icon=':material/search_off:');st.stop()
 if st.session_state.get('selector') not in opts:st.session_state['selector']='97973' if '97973' in opts else next((k for k in opts if g['nodes'][k]['kind']=='دستور' and g['nodes'][k]['year']=='1952'),opts[0])
 picked=st.selectbox('اختر التشريع من القائمة',opts,format_func=lambda k:clean(g['nodes'][k]['name'])[:180]+f" · {g['nodes'][k]['kind']} · {g['nodes'][k]['pmk'] or k}",key='selector',help='اكتب داخل القائمة للبحث في جميع نتائجها')
if st.session_state.get('last_node')!=picked:
 st.session_state['last_node']=picked
 for k in ['parents_page','children_page']:st.session_state.pop(k,None)
 history=st.session_state.setdefault('nav_history',[])
 if not history or history[-1]!=picked:history.append(picked)
# History is presentation navigation only; it does not store legal decisions.
a,b=st.columns([1,5])
with a:
 history=st.session_state.get('nav_history',[])
 def previous_node():
  hs=st.session_state['nav_history'];hs.pop();target=hs.pop();follow(target)
 st.button('رجوع',icon=':material/arrow_forward:',disabled=len(history)<2,on_click=previous_node,width='stretch')
with b:st.caption('استكشاف الشبكة / '+g['nodes'][picked]['kind']+' / '+clean(g['nodes'][picked]['name'])[:100])
identity_card(g['nodes'][picked])
filter_edge=lambda e:(not statuses or e['status'] in statuses) and (flags or not(e['deleted'] or e['historical']))
parents=[e for e in g['parents'].get(picked,[]) if filter_edge(e)];children=[e for e in g['children'].get(picked,[]) if filter_edge(e)]
instruction_line('الأب هو التشريع الذي يستند إليه التشريع المختار وفق المصدر، والابن هو تشريع مرتبط بالمختار. صحة الاتجاه والأثر القانوني تحتاج دليلاً.')
a,b=st.columns(2,gap='large')
with a:section_title('التشريعات الأب',len(parents),'تشريعات يستند إليها السجل المختار');show_links(g,parents,'parent','parents',compact)
with b:section_title('التشريعات الأبناء',len(children),'تشريعات مرتبطة بالسجل المختار');show_links(g,children,'child','children',compact)
if g['candidates'].get(picked):
 with st.expander('مرشحو الهوية المختلف عليها',icon=':material/manage_search:'):
  for eid in list(dict.fromkeys(g['candidates'][picked]))[:20]:show_evidence(g['edge_by_id'][eid])
with st.expander('تغطية البيانات وحدود الثقة',icon=':material/policy:'):
 st.write('المطابقة البنيوية وتوافق الاستخراج لا يثبتان الدقة القانونية وحدهما. الصادرات الحالية لا تثبت اكتمال قاعدة الديوان. بيانات الديوان مؤجلة، ولا مقارنة أو دمج معها في هذا النشر.')
 st.json(g['meta'])
st.markdown('<div class="footer-note">مِعيار · عرض فقط · الهويات والنسخ المختلف عليها محفوظة دون دمج تلقائي</div>',unsafe_allow_html=True)
