"""Selectable relationship tasks; law/bylaw allocations and event IDs stay intact."""
import copy
import hashlib
from collections import Counter
from assignments import resolve_handoffs

LAW_BYLAW = 'law_bylaw'
VOLUNTEERS = ['v1', 'v2', 'v3', 'v4', 'v5', 'v6']
LABELS = {'قانون': 'القانون', 'نظام': 'النظام', 'دستور': 'الدستور',
          'تعليمات': 'التعليمات', 'قرار': 'القرار', 'ملحق': 'الملحق',
          'جدول': 'الجدول', 'اخرى': 'التشريع الآخر', '': 'التشريع غير المصنف'}


def task_catalog(graph):
    counts = Counter((graph['nodes'][e['parent']]['kind'], graph['nodes'][e['child']]['kind'])
                     for e in graph['edges'])
    ordered = sorted(counts, key=lambda pair: (pair != ('قانون', 'نظام'), -counts[pair], pair))
    result = {}
    for parent, child in ordered:
        key = LAW_BYLAW if (parent, child) == ('قانون', 'نظام') else 'pair_' + hashlib.sha256((parent+'|'+child).encode()).hexdigest()[:12]
        result[key] = {'id': key, 'parent_kind': parent, 'child_kind': child,
                       'parent_label': LABELS.get(parent, parent), 'child_label': LABELS.get(child, child),
                       'title': f"{parent or 'غير مصنف'} ← {child or 'غير مصنف'}", 'total': counts[parent, child]}
    return result


def select_tasks(graph, base_tasks, rows, context):
    if context['id'] == LAW_BYLAW:
        return resolve_handoffs(base_tasks, rows)
    edges = [e for e in graph['edges']
             if graph['nodes'][e['parent']]['kind'] == context['parent_kind']
             and graph['nodes'][e['child']]['kind'] == context['child_kind']]
    # Existing decisions outside the original law/bylaw task keep their owner.
    known_ids = {e['id'] for e in edges}
    started = {}
    for row in rows:
        if row['reviewer'] in VOLUNTEERS and row['edge_id'] in known_ids:
            started.setdefault(row['edge_id'], row['reviewer'])
    allocation = {name: [] for name in VOLUNTEERS}
    for edge in edges:
        owner = started.get(edge['id']) or VOLUNTEERS[int(hashlib.sha256(edge['id'].encode()).hexdigest(), 16) % 6]
        allocation[owner].append(edge['id'])
    tasks = {}
    for name, base in base_tasks.items():
        task = copy.deepcopy(base)
        for field in ('incoming_transfers', 'exclude_edge_ids', 'restore_edge_ids', 'statuses'):
            task.pop(field, None)
        task.update(parent_types=[context['parent_kind']], child_types=[context['child_kind']],
                    partitions=1, partition=0, target=0, explicit_edge_ids=True,
                    edge_ids=[e['id'] for e in edges] if base.get('admin') else allocation.get(name, []),
                    title='تدقيق ارتباطات '+context['title'],
                    instructions='تحقق من هوية التشريعين واتجاه العلاقة ونوعها الفعلي، ثم راجع المواد والدليل. وجود التشريع في قائمة ارتباطات لا يثبت أنه سند إصدار.',
                    steps=['تأكد من اسم ورقم وسنة كل تشريع والنسخة المقصودة.',
                           'اقرأ الدليل والمواد وحدد نوع الارتباط واتجاهه؛ لا تفترض أنه إصدار بمجرد ذكر تشريع.',
                           'اختر تأكيد العلاقة أو رفضها أو مراجعة إضافية عند نقص الدليل.',
                           'السبب والمواد والرابط والمقتطف اختيارية. احفظ القرار قبل الانتقال إلى مهمة أخرى.'])
        tasks[name] = task
    return tasks


def activate_task(state, task_id):
    """Preserve each task's search, selected relation and pagination in this session."""
    previous = state.get('_active_relationship_task')
    if previous == task_id:
        return
    keys = [key for key in list(state) if str(key).startswith('work_') or key in ('selected_edge', 'queue_mode')]
    saved = dict(state.get('_relationship_navigation', {}))
    if previous is not None:
        saved[previous] = {key: copy.deepcopy(state[key]) for key in keys}
    for key in keys:
        state.pop(key, None)
    for key, value in saved.get(task_id, {}).items():
        state[key] = copy.deepcopy(value)
    state['_relationship_navigation'] = saved
    state['_active_relationship_task'] = task_id
