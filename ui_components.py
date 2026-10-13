"""Shared visual components. No access to source data or review storage."""
import html,json,streamlit as st

PALETTES={'VERIFIED_STRUCTURAL':('#e5f4ec','#267456','مطابق بنيوياً'),'CONFIRMED_IDENTITY_ERROR':('#fff0ed','#b3433c','تعارض هوية مؤكد'),'REVIEW_REQUIRED':('#fff6df','#956616','بحاجة مراجعة'),'NO_CANDIDATE':('#edf0f5','#647087','غير محسوم'),'CANDIDATE_ONLY':('#ecebfa','#66589f','مرشح')}
def badge(status):
 bg,fg,label=PALETTES.get(status,('#edf0f5','#647087',status));return f'<span class="pill" style="background:{bg};color:{fg}">{html.escape(label)}</span>'
def hero(title,subtitle,tag='عرض شبكة التشريعات',review=False):
 icon='✓' if review else '⌘'
 st.markdown(f'<div class="hero"><div class="hero-copy"><span class="hero-tag">مِعيار · {html.escape(tag)}</span><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div><div class="hero-icon" aria-hidden="true">{icon}</div></div>',unsafe_allow_html=True)
def metrics(items):
 cols=st.columns(len(items))
 for c,(label,value,hint,tone) in zip(cols,items):
  with c:st.markdown(f'<div class="metric-tile"><div class="metric-label">{html.escape(label)}</div><div class="metric-number tone-{tone}">{html.escape(str(value))}</div><div class="metric-hint">{html.escape(hint)}</div></div>',unsafe_allow_html=True)
def source_note(source):
 if source=='DIWAN':title='صادرات الديوان';text='22,752 علاقة مباشرة + 22,455 ارتباطاً مسمّى. اتساق المرجع فحص بنيوي؛ اتجاه الارتباطات المسمّاة غير محسوم.'
 else:title='الشبكة المستخرجة';text='22,676 علاقة جُمعت ضمن الشبكة الحالية. توافق جانبَي الاستخراج دليل مساعد، ولا يمثل تحققاً قانونياً رسمياً.'
 st.markdown(f'<div class="source-note"><span class="source-dot"></span><div><strong>{title}</strong><p>{text}</p></div><span class="source-label">مجموعة مستقلة</span></div>',unsafe_allow_html=True)
def section_title(title,count=None,subtitle=''):
 n=f'<span>{count:,}</span>' if count is not None else ''
 st.markdown(f'<div class="section-title"><h3>{html.escape(title)}</h3>{n}</div>'+ (f'<p class="section-subtitle">{html.escape(subtitle)}</p>' if subtitle else ''),unsafe_allow_html=True)
def relation_header(name,kind,status,article,number='',year=''):
 st.markdown(f'<div class="relation-copy">{badge(status)}<h4>{html.escape(name[:360])}</h4><div class="relation-meta">{html.escape(kind)} <span>·</span> الرقم: {html.escape(number or "غير محدد")} <span>·</span> السنة: {html.escape(year or "غير محددة")} <span>·</span> المادة {html.escape(article or "غير محددة")}</div></div>',unsafe_allow_html=True)
def instruction_line(text):st.markdown(f'<div class="instruction">{html.escape(text)}</div>',unsafe_allow_html=True)
def pager(total,page_size,key):
 pages=max(1,(total+page_size-1)//page_size)
 if st.session_state.get(key,1)>pages:st.session_state[key]=1
 a,b,c=st.columns([1,2,1])
 def move(delta):st.session_state[key]=min(pages,max(1,st.session_state.get(key,1)+delta))
 with a:st.button('السابق',key=key+'_prev',icon=':material/chevron_right:',disabled=st.session_state.get(key,1)<=1,on_click=move,args=(-1,),width='stretch')
 with b:page=st.number_input('الصفحة',min_value=1,max_value=pages,key=key,label_visibility='collapsed');st.caption(f'صفحة {page} من {pages} · {total:,} نتيجة')
 with c:st.button('التالي',key=key+'_next',icon=':material/chevron_left:',disabled=page>=pages,on_click=move,args=(1,),width='stretch')
 return page
