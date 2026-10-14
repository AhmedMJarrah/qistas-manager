"""Admin-only, read-only progress dashboard. Event history is never rewritten."""
import csv
import io
import json
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from assignments import assigned_edges, summarize

VERDICTS = {'CONFIRM': 'تأكيد', 'REJECT': 'رفض', 'NEEDS_REVIEW': 'تحتاج متابعة'}


def local_time(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(ZoneInfo('Asia/Amman')).strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError):
        return value or 'لم يبدأ'


def dashboard_data(graph, tasks, rows):
    """Latest sheet event per (user, edge), retaining all events for history."""
    scoped = {e['id'] for e in graph['edges']
              if graph['nodes'][e['parent']]['kind'] == 'قانون'
              and graph['nodes'][e['child']]['kind'] == 'نظام'}
    latest = {}
    for row in rows:
        latest[row['reviewer'], row['edge_id']] = row
    people, assignments = [], {}
    for name, task in tasks.items():
        if task.get('admin'):
            continue
        edges = assigned_edges(graph, task)
        assignments[name] = {e['id'] for e in edges}
        stats = summarize(edges, rows, name)
        verdicts = Counter(r['verdict'] for r in stats['latest'].values())
        own_rows = [r for r in rows if r['reviewer'] == name]
        done = len(stats['done'])
        people.append({'المستخدم': name, 'الحصة': stats['total'],
                       'راجع': len(stats['latest']), 'محسوم': done,
                       'تأكيد': verdicts['CONFIRM'], 'رفض': verdicts['REJECT'],
                       'متابعة': len(stats['pending']), 'لم يبدأ': len(stats['unreviewed']),
                       'المتبقي للحسم': stats['total'] - done,
                       'الإنجاز %': round(100 * done / stats['total'], 1) if stats['total'] else 0,
                       'عمليات الحفظ التاريخية': len(own_rows),
                       'آخر نشاط — عمّان': local_time(own_rows[-1]['created_at']) if own_rows else 'لم يبدأ'})
    scoped_latest = [r for (_, eid), r in latest.items() if eid in scoped]
    by_edge = defaultdict(list)
    for row in scoped_latest:
        by_edge[row['edge_id']].append(row)
    conflicts = {eid: events for eid, events in by_edge.items()
                 if len({r['verdict'] for r in events}) > 1}
    done_edges = {eid for eid, events in by_edge.items() if eid not in conflicts
                  and all(r['verdict'] in ('CONFIRM', 'REJECT') for r in events)}
    outside = [r for (_, eid), r in latest.items() if eid not in scoped]
    owners = defaultdict(list)
    for user, ids in assignments.items():
        for eid in ids:
            owners[eid].append(user)
    overlaps = {eid: users for eid, users in owners.items() if len(users) > 1}
    return dict(people=people, latest=list(latest.values()), scoped=scoped,
                done=done_edges, reviewed=set(by_edge), conflicts=conflicts,
                outside=outside, overlaps=overlaps, unassigned=scoped-set(owners))


def csv_bytes(records):
    stream = io.StringIO(newline='')
    if records:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        for row in records:
            safe = {k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v)
                    for k, v in row.items()}
            writer.writerow(safe)
    return stream.getvalue().encode('utf-8-sig')


def render_dashboard(graph, tasks, rows, reviewer, accounts):
    import streamlit as st
    from ui_components import hero, metrics, section_title

    # Never trust a selected page or a URL as authorization.
    if not tasks.get(reviewer, {}).get('admin') or reviewer not in accounts:
        st.error('هذه الصفحة متاحة لمسؤول المشروع فقط.')
        st.stop()
        return
    data = dashboard_data(graph, tasks, rows)
    hero('الفريق، والتقدم، وما يحتاج قرارك.',
         'تابع حصص المتطوعين الستة وآخر قراراتهم من سجل Google Sheets.', 'لوحة مسؤول المشروع', True)
    metrics([('إجمالي العلاقات', f"{len(data['scoped']):,}", 'قانون ← نظام', 'navy'),
             ('محسومة بلا تعارض', f"{len(data['done']):,}", 'آخر القرارات المسجلة', 'teal'),
             ('المتبقي للحسم', f"{len(data['scoped']) - len(data['done']):,}", 'يشمل غير المراجع والمتابعة والتعارض', 'purple'),
             ('تعارض القرارات', f"{len(data['conflicts']):,}", 'علاقات تحتاج حسم المسؤول', 'navy')])
    total = len(data['scoped'])
    st.progress(len(data['done']) / total if total else 0, text='التقدم الإجمالي في حسم العلاقات')
    st.caption('المحسوم = تأكيد أو رفض. تعديل القرار لا يُحسب علاقة إضافية. المؤشرات تصف قرارات الفريق، ولا تشهد بصحة العلاقة قانونياً.')
    if data['overlaps'] or data['unassigned']:
        st.warning(f"فحص التوزيع: {len(data['overlaps'])} علاقة لها أكثر من متطوع، و{len(data['unassigned'])} علاقة بلا حصة.")
    overview, detail, history, issues = st.tabs(['تقدم المتطوعين', 'قرارات الفريق', 'السجل التاريخي', 'ما يحتاج انتباهك'])
    with overview:
        section_title('كل متطوع وحصته')
        st.dataframe(data['people'], hide_index=True, width='stretch',
                     column_config={'الإنجاز %': st.column_config.ProgressColumn('الإنجاز %', min_value=0, max_value=100, format='%.1f%%')})
        st.download_button('تنزيل ملخص التقدم CSV', csv_bytes(data['people']),
                           'team_progress.csv', 'text/csv', key='admin_progress_csv')
        for person in data['people']:
            user = person['المستخدم']
            with st.expander(f"{user} · {accounts.get(user, {}).get('display_name', user)} · {person['محسوم']} / {person['الحصة']}"):
                st.progress(person['الإنجاز %'] / 100)
                st.write(f"تأكيد: {person['تأكيد']} · رفض: {person['رفض']} · متابعة: {person['متابعة']} · لم يبدأ: {person['لم يبدأ']}")
                st.caption('آخر نشاط بتوقيت عمّان: ' + person['آخر نشاط — عمّان'])
                if user not in accounts:
                    st.info('الحصة جاهزة؛ أضف الحساب في Secrets حتى يستطيع الدخول.')
    with detail:
        user = st.selectbox('المتطوع', ['الجميع'] + sorted({r['reviewer'] for r in rows}), key='admin_user')
        decision = st.selectbox('القرار', ['الجميع'] + list(VERDICTS), format_func=lambda x: VERDICTS.get(x, x), key='admin_verdict')
        query = st.text_input('ابحث باسم القانون أو النظام أو معرف العلاقة', key='admin_query').strip().casefold()
        records = [r for r in data['latest'] if r['edge_id'] in data['scoped']
                   and (user == 'الجميع' or r['reviewer'] == user)
                   and (decision == 'الجميع' or r['verdict'] == decision)
                   and (not query or query in ' '.join([r['parent_name'], r['child_name'], r['edge_id']]).casefold())]
        display = [{'المتطوع': r['reviewer'], 'القانون': r['parent_name'], 'النظام': r['child_name'],
                    'القرار': VERDICTS[r['verdict']], 'وقت القرار — عمّان': local_time(r['created_at']),
                    'سبب القرار': r['note'], 'الرابط': r['evidence_url'], 'الدليل والمواد': r['evidence_text'],
                    'معرف العلاقة': r['edge_id']} for r in records]
        st.caption(f'{len(records):,} قرار حالي ضمن الفلاتر')
        st.dataframe(display, hide_index=True, width='stretch')
        st.download_button('تنزيل القرارات الظاهرة CSV', csv_bytes(display), 'filtered_reviews.csv', 'text/csv')
    with history:
        st.caption(f'{len(rows):,} عملية حفظ في النسخة الحالية وما يكافئها بتنسيق الأسطر؛ يشمل القرارات السابقة والتعديلات وخارج النطاق الحالي.')
        st.dataframe(list(reversed(rows)), hide_index=True, width='stretch')
        st.download_button('تنزيل سجل الفريق JSON', json.dumps({'dataset': 'EXTRACTED', 'dataset_version': graph['version'], 'reviews': rows}, ensure_ascii=False, indent=2), 'team_reviews.json', 'application/json', key='admin_history_json')
    with issues:
        section_title('قرارات متعارضة', len(data['conflicts']))
        for eid, events in data['conflicts'].items():
            with st.expander(events[0]['parent_name'] + ' ← ' + events[0]['child_name']):
                st.dataframe(events, hide_index=True, width='stretch')
        section_title('قرارات سابقة خارج نطاق قانون ← نظام', len(data['outside']))
        st.caption('تظل محفوظة في سجلها، ولا تدخل في نسبة إنجاز الحصة الحالية.')
        st.dataframe(data['outside'], hide_index=True, width='stretch')
        if not data['conflicts']:
            st.success('لا يوجد تعارض بين آخر القرارات المسجلة ضمن النطاق الحالي.')
