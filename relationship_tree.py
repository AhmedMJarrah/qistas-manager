"""Identity-based, one-level relationship tree. Every source edge is retained."""
from collections import OrderedDict


def group_relationships(edges):
    parents = OrderedDict()
    for edge in edges:
        parent = parents.setdefault(edge['parent'], {'parent_id': edge['parent'], 'children': OrderedDict(), 'edges': []})
        child = parent['children'].setdefault(edge['child'], {'child_id': edge['child'], 'edges': []})
        child['edges'].append(edge)
        parent['edges'].append(edge)
    return list(parents.values())


def render_relationship_tree(graph, edges, jump):
    import html
    import streamlit as st
    from common import clean, show_evidence
    from ui_components import badge, pager, section_title

    groups = group_relationships(edges)
    unique_children = {edge['child'] for edge in edges}
    st.caption(f'{len(groups):,} تشريع أب · {len(unique_children):,} تشريع ابن · {len(edges):,} سجل علاقة. أعداد الأبناء في كل فرع تخص الفلاتر الحالية.')
    page = pager(len(groups), 8, 'tree_parent_page')
    for index, group in enumerate(groups[(page-1)*8:page*8]):
        parent_id = group['parent_id']
        parent = graph['nodes'][parent_id]
        children = list(group['children'].values())
        with st.container(border=True, key='tree_parent_'+str(parent_id)):
            name = html.escape(clean(parent['name']))
            kind = html.escape(parent['kind'])
            st.markdown(f'<div class="tree-parent"><span class="tree-node-kind">الأب · {kind}</span><h3>{name}</h3><span class="tree-count">{len(children):,} أبناء · {len(group["edges"]):,} سجلات علاقة</span></div>', unsafe_allow_html=True)
            st.caption('الرقم: '+(parent['number'] or 'غير محدد')+' · السنة: '+(parent['year'] or 'غير محددة'))
            actions, fold = st.columns([2, 1])
            with actions:
                st.button('فتح التشريع الأب', key='tree_open_parent_'+str(parent_id), icon=':material/account_tree:', on_click=jump, args=(parent_id,), width='stretch')
            with fold:
                opened = st.toggle('عرض الأبناء', value=index==0, key='tree_expand_'+str(parent_id))
            if not opened:
                continue
            child_page = pager(len(children), 12, 'tree_child_page_'+str(parent_id)) if len(children)>12 else 1
            with st.container(key='tree_children_'+str(parent_id)):
                for branch in children[(child_page-1)*12:child_page*12]:
                    child_id = branch['child_id']
                    child = graph['nodes'][child_id]
                    records = branch['edges']
                    with st.container(border=True, key='tree_branch_'+str(parent_id)+'_'+str(child_id)):
                        st.markdown('<div class="tree-child"><span class="tree-node-kind">الابن · '+html.escape(child['kind'])+'</span><h4>'+html.escape(clean(child['name']))+'</h4></div>', unsafe_allow_html=True)
                        st.caption('الرقم: '+(child['number'] or 'غير محدد')+' · السنة: '+(child['year'] or 'غير محددة'))
                        # Multiple source records for one pair remain individually inspectable.
                        statuses = list(dict.fromkeys(edge['status'] for edge in records))
                        st.markdown(' '.join(badge(status) for status in statuses), unsafe_allow_html=True)
                        articles = list(dict.fromkeys(edge['article'] for edge in records if edge.get('article')))
                        if articles:
                            st.caption('المواد المذكورة: '+'؛ '.join(articles))
                        if len(records)>1:
                            st.caption(f'لهذا الأب والابن {len(records):,} سجلات مصدر مستقلة؛ جُمعت بصرياً فقط.')
                        st.button('فتح التشريع الابن', key='tree_open_child_'+str(parent_id)+'_'+str(child_id), icon=':material/arrow_back:', on_click=jump, args=(child_id,), width='stretch')
                        with st.expander('عبارة الإصدار والدليل', icon=':material/menu_book:'):
                            for position, edge in enumerate(records, 1):
                                if len(records)>1:
                                    section_title('سجل العلاقة '+str(position))
                                st.caption('معرّف العلاقة: '+edge['id'])
                                show_evidence(edge)
