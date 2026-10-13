"""Arabic assigned-work reviewer portal, Google Sheets only."""
from pathlib import Path
import hashlib
import html
import json
import time
import uuid
import streamlit as st
from common import design, load_extracted, norm, clean, identity_card, show_evidence, LABELS, node_search_text
from ui_components import hero, metrics, section_title, instruction_line, badge
from assignments import load_tasks, assigned_edges, summarize, DEFAULT_STEPS
from review_auth import authenticate
from sheets_store import SheetsStore, StoreError, SaveUncertain, make_event

ROOT = Path(__file__).resolve().parent
VERDICTS = {'CONFIRM': 'تأكيد بالدليل', 'REJECT': 'رفض بالدليل', 'NEEDS_REVIEW': 'مراجعة إضافية'}
design('مِعيار | مهام المتطوعين')
try:
    accounts = st.secrets.get('reviewers', {})
except Exception:
    accounts = {}
if not accounts:
    hero('مساحة المتطوعين.','مراجعة العلاقات بالدليل، مع مهمة واضحة لكل مراجع.','تسجيل الدخول',True)
    st.info('حسابات المراجعين لم تُضف بعد. مسؤول التطبيق يضيفها في إعدادات الاستضافة.')
    st.stop()

reviewer = st.session_state.get('reviewer_account')
signature = lambda user: hashlib.sha256((str(user.get('salt','')) + str(user.get('password_hash',''))).encode()).hexdigest()
if reviewer not in accounts or st.session_state.get('auth_signature') != signature(accounts.get(reviewer, {})) or time.time() - st.session_state.get('authenticated_at', 0) > 8 * 3600:
    for key in ('reviewer_account', 'auth_signature', 'authenticated_at', 'pending_saves'):
        st.session_state.pop(key, None)
    reviewer = None

if not reviewer:
    hero('مهمتك واضحة، وقرارك موثّق.','ادخل بحسابك لمعرفة الحالات المطلوبة منك، ومراجعتها خطوة بخطوة.','تسجيل دخول المتطوعين',True)
    with st.container(key='login_panel'):
        st.subheader('تسجيل الدخول')
        with st.form('login'):
            username = st.text_input('اسم المستخدم', placeholder='مثال: v1', max_chars=100)
            password = st.text_input('كلمة المرور', type='password', max_chars=200)
            submitted = st.form_submit_button('دخول', type='primary', width='stretch')
        if submitted:
            if time.time() < st.session_state.get('login_after', 0):
                st.warning('انتظر ثواني قليلة قبل محاولة جديدة.')
            elif authenticate(accounts, username, password):
                reviewer = username.strip()
                st.session_state.update(reviewer_account=reviewer, auth_signature=signature(accounts[reviewer]),
                                        authenticated_at=time.time(), login_failures=0)
                st.rerun()
            else:
                failures = st.session_state.get('login_failures', 0) + 1
                st.session_state['login_failures'] = failures
                st.session_state['login_after'] = time.time() + min(30, 2 ** min(failures, 5))
                st.error('اسم المستخدم أو كلمة المرور غير صحيحين.')
        st.caption('استخدم حسابك الشخصي؛ الحساب يحدد صاحب كل قرار محفوظ.')
    st.stop()

display = accounts[reviewer].get('display_name', reviewer)
try:
    tasks = load_tasks(ROOT / 'reviewer_tasks.json')
except (ValueError, OSError):
    st.error('تعذّر تحميل توزيع المهام. تواصل مع مسؤول المشروع.')
    st.stop()
task = tasks.get(reviewer)
with st.sidebar:
    st.markdown('<div class="reviewer-info"><small>المتطوع المسجل</small><strong>'+html.escape(display)+'</strong></div>', unsafe_allow_html=True)
    if st.button('تسجيل الخروج', icon=':material/logout:', width='stretch'):
        st.session_state.clear()
        st.rerun()
if not task:
    st.info('لم تُحدد مهمتك بعد. تواصل مع مسؤول المشروع لإضافتها؛ لن تظهر لك حالات خارج مهمة محددة.')
    st.stop()

graph = load_extracted()
assigned = assigned_edges(graph, task)
assigned_ids = {edge['id'] for edge in assigned}
hero('مرحباً '+str(display)+'، هذه مساحة عملك.','مراجعة بالدليل، تعليمات واضحة، وحفظ كل قرار في سجل الفريق.','مهام المتطوعين',True)
with st.container(key='my_task', border=True):
    section_title('المطلوب مني', subtitle=task.get('title', 'مراجعة العلاقات المخصصة لك'))
    st.write(task.get('instructions', 'راجع الحالات في حصتك واتبع خطوات المراجعة أدناه.'))
    types = lambda key: '، '.join(task.get(key, [])) or 'جميع الأنواع'
    st.caption('نوع الأب: '+types('parent_types')+' · نوع الابن: '+types('child_types'))
    if task.get('target', 0):
        st.caption(f"هدف المهمة: {task['target']} علاقة بقرار تأكيد أو رفض؛ المراجعة الإضافية لا تُحسب حسمًا.")
    with st.expander('خطوات المراجعة بالتفصيل', expanded=True, icon=':material/checklist:'):
        for number, step in enumerate(task.get('steps') or DEFAULT_STEPS, 1):
            st.write(f'{number}. {step}')

@st.cache_resource(show_spinner=False)
def connect_store():
    try:
        return SheetsStore(st.secrets['SHEET_ID'], st.secrets.get('SHEET_NAME', 'qistas_reviews'), st.secrets['gcp_service_account'])
    except StoreError:
        raise
    except Exception:
        raise StoreError('إعداد Google Sheets غير مكتمل. يلزم SHEET_ID وgcp_service_account في Secrets.') from None

@st.cache_data(ttl=30, show_spinner=False)
def read_rows(sheet_id, name, version, _store):
    return _store.read('EXTRACTED', version)

try:
    store = connect_store()
    rows = read_rows(store.sheet_id, store.worksheet_name, graph['version'], store)
except StoreError as exc:
    st.error(str(exc))
    st.info('تعليماتك ظاهرة، لكن المراجعة والحفظ ينتظران إعداد سجل الفريق. تواصل مع المسؤول.')
    st.stop()

summary = summarize(assigned, rows, reviewer)
metrics([('حصتي',f"{summary['total']:,}",'كل الحالات المخصصة لك','navy'),
         ('قرارات محسومة',f"{len(summary['done']):,}",'تأكيد أو رفض بالدليل','teal'),
         ('تحتاج متابعة',f"{len(summary['pending']):,}",'قراراتك بالمراجعة الإضافية','purple'),
         ('لم أبدأها',f"{len(summary['unreviewed']):,}",'حالات لم تسجل عليها قراراً','navy')])
if assigned:
    st.progress(len(summary['done']) / len(assigned), text=f"المحسوم من حصتك: {len(summary['done']):,} من {len(assigned):,}")
if task.get('target', 0) and len(summary['done']) >= task['target']:
    st.success('وصلت إلى هدف المهمة المحدد. يمكنك متابعة الحالات المتبقية بحسب توجيه المسؤول.')
if st.session_state.get('review_flash'):
    st.success(st.session_state.pop('review_flash'))

with st.sidebar:
    st.divider()
    st.markdown('### قائمة عملي')
    queue = st.radio('الحالات المعروضة', ['NEW', 'FOLLOW_UP', 'ALL'],
                     format_func=lambda x:{'NEW':'لم أبدأها','FOLLOW_UP':'تحتاج متابعة','ALL':'كل حصتي'}[x], key='queue_mode')
    parent_types = st.multiselect('نوع التشريع الأب', sorted({graph['nodes'][e['parent']]['kind'] for e in assigned}), key='parent_filter')
    child_types = st.multiselect('نوع التشريع الابن', sorted({graph['nodes'][e['child']]['kind'] for e in assigned}), key='child_filter')
    statuses = st.multiselect('حالة المصدر', sorted({e['status'] for e in assigned}), format_func=LABELS.get)
    if st.button('تحديث سجل الفريق', icon=':material/refresh:', width='stretch'):
        read_rows.clear()
        st.rerun()
    st.caption('الفلاتر تضيق حصتك؛ لا تضيف حالات خارج المهمة.')

query = st.text_input('ابحث داخل حصتك', placeholder='اسم الأب أو الابن أو معرّف الرابط…', key='work_search')
pool = summary['unreviewed'] if queue == 'NEW' else summary['pending'] if queue == 'FOLLOW_UP' else assigned_ids
candidates = [e for e in assigned if e['id'] in pool
              and (not parent_types or graph['nodes'][e['parent']]['kind'] in parent_types)
              and (not child_types or graph['nodes'][e['child']]['kind'] in child_types)
              and (not statuses or e['status'] in statuses)
              and (not query or norm(query) in norm(node_search_text(graph['nodes'][e['parent']])+' '+node_search_text(graph['nodes'][e['child']])+' '+e['id']))]
rank = {'REVIEW_REQUIRED':0, 'CANDIDATE_ONLY':1}
candidates.sort(key=lambda e:(rank.get(e['status'],2), e['id']))
st.caption(f'نتائج قائمة العمل الحالية: {len(candidates):,}. حالة المصدر منفصلة عن قرارك.')

if candidates:
    # Limit the widget size; navigation advances through all matching work in batches.
    pages = max(1, (len(candidates) + 99) // 100)
    if st.session_state.get('work_page',1) > pages:
        st.session_state['work_page'] = 1
    page = st.number_input('صفحة الحالات', min_value=1, max_value=pages, key='work_page')
    batch = candidates[(page-1)*100:page*100]
    ids = [e['id'] for e in batch]
    next_id = st.session_state.pop('next_id', None)
    if next_id in ids:
        st.session_state['selected_edge'] = next_id
    if st.session_state.get('selected_edge') not in ids:
        st.session_state['selected_edge'] = ids[0]
    edge_id = st.selectbox('الحالة الحالية', ids, key='selected_edge',
                           format_func=lambda eid:clean(graph['nodes'][graph['edge_by_id'][eid]['parent']]['name'])[:75]+' ← '+clean(graph['nodes'][graph['edge_by_id'][eid]['child']]['name'])[:75])
    edge = graph['edge_by_id'][edge_id]
    st.markdown(badge(edge['status']), unsafe_allow_html=True)
    instruction_line('المطلوب في هذه الحالة: تحقق من هوية التشريعين، ثم أثبت أو انْفِ اتجاه الرابط بمصدر؛ إن لم تكفِ الأدلة اختر مراجعة إضافية وحدد ما ينقص.')
    parent, child = st.columns(2, gap='large')
    with parent:
        section_title('التشريع الأب')
        identity_card(graph['nodes'][edge['parent']])
    with child:
        section_title('التشريع الابن')
        identity_card(graph['nodes'][edge['child']])
    with st.container(border=True):
        section_title('الدليل المتاح')
        show_evidence(edge)
    section_title('قراري لهذه الحالة', subtitle='لا يوجد قرار افتراضي؛ احفظ بعد قراءة الدليل.')
    with st.container(key='decision_panel', border=True):
        with st.form('decision_'+edge_id):
            verdict = st.radio('القرار', list(VERDICTS), index=None, format_func=VERDICTS.get, horizontal=True)
            note = st.text_area('سبب القرار — مطلوب', max_chars=4000, placeholder='ماذا يثبت الرابط أو يعارضه؟ وإن احتاج متابعة، ما المعلومة الناقصة؟')
            url = st.text_input('رابط الدليل', max_chars=2000, placeholder='https://…')
            text = st.text_area('مقتطف الدليل أو نص المادة', max_chars=12000, placeholder='اذكر المصدر ورقم المادة مع المقتطف ذي الصلة.')
            submitted = st.form_submit_button('حفظ والانتقال للحالة التالية', type='primary', icon=':material/task_alt:', width='stretch')
        if submitted:
            try:
                if edge_id not in assigned_ids:
                    raise ValueError('هذه الحالة خارج المهمة المخصصة لك.')
                fingerprint = hashlib.sha256(json.dumps([graph['version'],reviewer,edge_id,verdict,note.strip(),url.strip(),text.strip()],ensure_ascii=False).encode()).hexdigest()
                pending = st.session_state.setdefault('pending_saves', {})
                event = pending.get(fingerprint)
                if event is None:
                    event = make_event(str(uuid.uuid4()), graph, edge, reviewer, verdict, note, url, text)
                    pending[fingerprint] = event
                store.save(event)
                pending.pop(fingerprint, None)
                read_rows.clear()
                st.session_state['review_flash'] = 'تم تأكيد حفظ قرارك في Google Sheets. تستطيع العودة إليه من «كل حصتي».'
                if queue != 'NEW':
                    position = ids.index(edge_id)
                    st.session_state['next_id'] = ids[(position+1) % len(ids)]
                st.rerun()
            except (ValueError, StoreError) as exc:
                st.error(str(exc))
    own_history = [r for r in rows if r['edge_id']==edge_id and r['reviewer']==reviewer]
    if own_history:
        with st.expander('قراراتي السابقة لهذه الحالة', icon=':material/history:'):
            for event in reversed(own_history):
                st.write(VERDICTS[event['verdict']]+' · '+event['created_at'])
                st.write(event['note'])
                if event['evidence_url']:
                    st.write(event['evidence_url'])
                if event['evidence_text']:
                    st.write(event['evidence_text'])
else:
    st.info('لا توجد حالات مطابقة في هذه القائمة. اختر «تحتاج متابعة» أو «كل حصتي»، أو عدّل الفلاتر.')

st.divider()
own_rows = [r for r in rows if r['reviewer']==reviewer]
st.download_button('تنزيل سجل قراراتي JSON', json.dumps({'dataset':'EXTRACTED','dataset_version':graph['version'],'reviews':own_rows},ensure_ascii=False,indent=2),
                   file_name='my_reviews_'+reviewer+'.json', mime='application/json', icon=':material/download:')
if task.get('admin',False):
    with st.expander('متابعة الفريق — مسؤول المشروع', icon=':material/groups:'):
        for name, item in tasks.items():
            if item.get('admin'):
                continue
            stats = summarize(assigned_edges(graph,item),rows,name)
            st.write(f"**{name}** · الحصة {stats['total']:,} · المحسوم {len(stats['done']):,} · متابعة {len(stats['pending']):,} · لم يبدأ {len(stats['unreviewed']):,}")
        st.download_button('تنزيل سجل الفريق JSON', json.dumps({'dataset':'EXTRACTED','dataset_version':graph['version'],'reviews':rows},ensure_ascii=False,indent=2),
                           file_name='team_reviews.json', mime='application/json')
st.caption('قرارات المراجعة محفوظة مستقلة؛ ملفات التشريعات لا تتغير تلقائياً.')
