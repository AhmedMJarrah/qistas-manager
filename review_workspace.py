"""Grouped law/bylaw review navigation; pure helpers preserve edge identities."""
import html
import re
import unicodedata
from collections import OrderedDict


def search_normalize(value):
    text = html.unescape(re.sub('<[^>]*>', ' ', str(value or '')))
    text = ''.join(c for c in unicodedata.normalize('NFKC', text)
                   if not unicodedata.combining(c) and c != 'ـ')
    text = text.translate(str.maketrans('أإآى٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', 'اااي01234567890123456789'))
    return ' '.join(re.findall(r'\w+', text.casefold()))


def search_match(query, value):
    # Tokens may appear in any order. Numeric tokens match whole numbers.
    words = search_normalize(value).split()
    return all(token in words if token.isdigit() else any(token in word for word in words)
               for token in search_normalize(query).split())


def searchable_node(node):
    return ' '.join(str(node.get(k, '')) for k in ('name', 'original_name', 'number', 'year', 'id', 'kind'))


def node_match(node, query='', number='', year=''):
    exact = lambda q, value: not q.strip() or search_normalize(q) == search_normalize(value)
    return search_match(query, searchable_node(node)) and exact(number, str(node.get('number', ''))) and exact(year, str(node.get('year', '')))


def article_numbers(edge):
    values = [str(a['article']) for a in edge.get('evidence', []) if a.get('article') is not None]
    # Only labelled mentions, never infer a legal basis from an arbitrary number.
    clause = search_normalize(edge.get('basis', ''))
    values.extend(re.findall(r'الماد(?:ة|ه)\s+(\d+)', clause))
    return list(dict.fromkeys(values))


def group_edges(edges, anchor):
    groups = OrderedDict()
    for edge in edges:
        groups.setdefault(edge[anchor], []).append(edge)
    return groups


def filter_work(graph, edges, anchor, query='', counterpart_query='', number='', year='', article=''):
    other = 'child' if anchor == 'parent' else 'parent'
    return [e for e in edges if node_match(graph['nodes'][e[anchor]], query, number, year)
            and node_match(graph['nodes'][e[other]], counterpart_query)
            and (not article.strip() or search_normalize(article) in
                 {search_normalize(a) for a in article_numbers(e)})]


def node_label(node):
    return f"{node['name']} · رقم {node.get('number') or 'غير محدد'} · {node.get('year') or 'سنة غير محددة'} · {node['id']}"


def render_workspace(graph, assigned, eligible, latest):
    import streamlit as st
    from ui_components import section_title

    def switch_direction():
        a = st.session_state.get('work_anchor_query', '')
        b = st.session_state.get('work_counterpart_query', '')
        st.session_state['work_anchor_query'], st.session_state['work_counterpart_query'] = b, a
        st.session_state['work_number'] = ''
        st.session_state['work_year'] = ''
        st.session_state['work_next_edge'] = st.session_state.get('selected_edge')
    mode = st.segmented_control('أراجع حسب', ['LAW', 'BYLAW'], default='LAW', required=True, key='work_direction',
                                on_change=switch_direction,
                                format_func=lambda v: 'القانون ← أنظمته' if v == 'LAW' else 'النظام ← قوانين سنده', width='stretch')
    anchor = 'child' if mode == 'BYLAW' else 'parent'
    other = 'parent' if anchor == 'child' else 'child'
    title, counterpart = ('النظام', 'القانون') if anchor == 'child' else ('القانون', 'النظام')
    with st.container(border=True):
        a, b = st.columns(2)
        with a:
            query = st.text_input('ابحث عن '+title, key='work_anchor_query', icon=':material/search:',
                                  placeholder='كلمات من الاسم بأي ترتيب… مثال: العمل')
        with b:
            other_query = st.text_input('ابحث عن '+counterpart+' المرتبط', key='work_counterpart_query',
                                        placeholder='اختياري… مثال: المرن')
        a, b, c, d = st.columns(4)
        with a: number = st.text_input('رقم '+title, key='work_number', placeholder='اختياري')
        with b: year = st.text_input('سنة '+title, key='work_year', placeholder='اختياري')
        with c: article = st.text_input('رقم مادة السند', key='work_article', placeholder='مثال: 140')
        with d:
            def reset():
                for k in ('work_anchor_query', 'work_counterpart_query', 'work_number', 'work_year', 'work_article', 'work_statuses'):
                    st.session_state.pop(k, None)
            st.button('مسح البحث والفلاتر', on_click=reset, icon=':material/filter_alt_off:', width='stretch')
        st.caption('البحث يتجاهل التشكيل واختلاف الهمزات ويقبل الأرقام العربية. الرقم والسنة يخصان '+title+' المختار. المواد المعروضة مستخرجة وتحتاج تدقيقًا.')

    matches = filter_work(graph, eligible, anchor, query, other_query, number, year, article)
    groups = group_edges(matches, anchor)
    st.caption(f'{len(groups):,} {title} مطابق · {len(matches):,} علاقة في قائمة العمل الحالية.')
    if not groups:
        st.info('لا توجد نتائج في حصتك بهذه الفلاتر. امسح البحث، أو اختر «كل حصتي» إذا سبق أن راجعت الحالة.')
        return None
    ids = sorted(groups, key=lambda k: search_normalize(graph['nodes'][k]['name']))
    navigation = st.session_state.pop('work_next_edge', None)
    next_edge = graph['edge_by_id'].get(navigation) if navigation else None
    signature = repr((mode, query, other_query, number, year, article, tuple(ids)))
    if st.session_state.get('work_group_signature') != signature:
        st.session_state['work_group_signature'] = signature
        st.session_state['work_group_page'] = 1
        st.session_state['work_branch_page'] = 1
    if next_edge and next_edge[anchor] in ids:
        st.session_state['work_group_page'] = ids.index(next_edge[anchor]) // 100 + 1
        st.session_state['work_group'] = next_edge[anchor]
    page_count = (len(ids) + 99) // 100
    if st.session_state.get('work_group_page', 1) > page_count:
        st.session_state['work_group_page'] = 1
    if page_count > 1:
        page = st.number_input('صفحة قائمة '+title, 1, page_count, key='work_group_page')
    else:
        page = 1
    batch = ids[(page - 1) * 100:page * 100]
    if st.session_state.get('work_group') not in batch:
        st.session_state['work_group'] = batch[0]
    chosen = st.selectbox('اختر '+title, batch, key='work_group',
                          format_func=lambda k: node_label(graph['nodes'][k])+f' · {len({e[other] for e in groups[k]})} {counterpart} مطابق')
    if st.session_state.get('work_previous_group') != (mode, chosen):
        st.session_state['work_previous_group'] = (mode, chosen)
        st.session_state['work_branch_page'] = 1
    assigned_group = [e for e in assigned if e[anchor] == chosen]
    group = sorted(groups[chosen], key=lambda e: (search_normalize(graph['nodes'][e[other]]['name']), e['id']))
    reviewed = sum(latest.get(e['id'], {}).get('verdict') in ('CONFIRM', 'REJECT') for e in assigned_group)
    node = graph['nodes'][chosen]
    st.markdown('<div class="tree-parent"><span class="tree-node-kind">'+html.escape(title)+'</span><h3>'+html.escape(node['name'])+'</h3><span class="tree-count">'+f'{len({e[other] for e in assigned_group}):,} {counterpart} في حصتي · {reviewed:,} / {len(assigned_group):,} علاقة محسومة'+'</span></div>', unsafe_allow_html=True)
    st.caption('هذه علاقات حصتك فقط؛ الأنظمة أو القوانين المعروضة لا تثبت اكتمال التشريع في المصدر. نفس القانون قد تكون له علاقات لدى متطوع آخر.')
    section_title(counterpart+' المرتبط — اختر علاقة لتدقيق سندها', len(group))
    branch_pages = (len(group) + 7) // 8
    edge_ids = [e['id'] for e in group]
    if navigation in edge_ids:
        st.session_state['work_branch_page'] = edge_ids.index(navigation) // 8 + 1
        st.session_state['selected_edge'] = navigation
    if st.session_state.get('work_branch_page', 1) > branch_pages:
        st.session_state['work_branch_page'] = 1
    if st.session_state.get('selected_edge') not in edge_ids:
        st.session_state['selected_edge'] = edge_ids[0]
    if branch_pages > 1:
        branch_page = st.number_input('صفحة '+counterpart+' المرتبط', 1, branch_pages, key='work_branch_page')
    else:
        branch_page = 1
    visible = group[(branch_page - 1) * 8:branch_page * 8]
    if st.session_state['selected_edge'] not in {e['id'] for e in visible}:
        st.session_state['selected_edge'] = visible[0]['id']
    st.caption(f'عرض {min((branch_page-1)*8+1, len(group))}–{min(branch_page*8, len(group))} من {len(group)} علاقة مطابقة · 8 علاقات في الصفحة')
    def choose(eid):
        st.session_state['selected_edge'] = eid
    for edge in visible:
        n = graph['nodes'][edge[other]]
        decision = latest.get(edge['id'], {}).get('verdict')
        label = {'CONFIRM': 'مؤكدة بقراري', 'REJECT': 'مرفوضة بقراري', 'NEEDS_REVIEW': 'تحتاج متابعة'}.get(decision, 'لم أراجعها')
        active = st.session_state['selected_edge'] == edge['id']
        with st.container(border=True):
            st.markdown('**'+html.escape(n['name'])+'**')
            st.caption(f"رقم {n.get('number') or 'غير محدد'} · سنة {n.get('year') or 'غير محددة'} · {label}")
            materials = article_numbers(edge)
            st.caption('مواد السند المذكورة: '+('، '.join(materials) if materials else 'غير محددة؛ تحتاج مراجعة المصدر'))
            st.button('العلاقة المختارة — الدليل والقرار أدناه' if active else 'تدقيق هذه العلاقة',
                      key='work_pick_'+edge['id'], type='primary' if active else 'secondary',
                      icon=':material/fact_check:', on_click=choose, args=(edge['id'],), width='stretch')
    selected = graph['edge_by_id'][st.session_state['selected_edge']]
    ordered = [e['id'] for k in ids for e in sorted(groups[k], key=lambda e: (search_normalize(graph['nodes'][e[other]]['name']), e['id']))]
    index = ordered.index(selected['id'])
    successor = ordered[(index + 1) % len(ordered)]
    return selected, successor
