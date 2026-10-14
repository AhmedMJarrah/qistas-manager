"""Deterministic work allocation; does not alter legal source records."""
import hashlib
import copy
import json
from pathlib import Path

DEFAULT_STEPS = [
    'اقرأ اسم التشريع الأب والابن، وتأكد من الرقم والسنة والنسخة في المصدر.',
    'افتح عبارة الإصدار والدليل المتاح، وحدد المادة المشار إليها إن وُجدت.',
    'تحقق أن الدليل يربط هذين التشريعين بالاتجاه المعروض، وليس مجرد ذكر أو إحالة.',
    'اختر تأكيداً بالدليل، أو رفضاً بالدليل، أو مراجعة إضافية إذا لم تكفِ المعلومات.',
    'اكتب سبباً واضحاً؛ للتأكيد أو الرفض أضف رابط المصدر أو مقتطف الدليل.',
    'احفظ وانتقل للحالة التالية. لا تخمّن الهوية أو الأساس القانوني عند غياب الدليل.',
]


def load_tasks(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema_version') != 1:
        raise ValueError('نسخة ملف المهام غير مدعومة.')
    tasks = data.get('reviewers', {})
    for name, task in tasks.items():
        parts, part = task.get('partitions', 1), task.get('partition', 0)
        if isinstance(parts, bool) or isinstance(part, bool) or not isinstance(parts, int) or not isinstance(part, int) or parts < 1 or not 0 <= part < parts:
            raise ValueError('توزيع مهام غير صالح للحساب: ' + name)
        if not isinstance(task.get('target', 0), int) or task.get('target', 0) < 0:
            raise ValueError('هدف إنجاز غير صالح للحساب: ' + name)
        for field in ('parent_types', 'child_types', 'statuses', 'edge_ids', 'exclude_edge_ids', 'restore_edge_ids'):
            if not isinstance(task.get(field, []), list):
                raise ValueError('حقل المهام يجب أن يكون قائمة: ' + field)
    return tasks


def assigned_edges(graph, task):
    if not task:
        return []
    result = []
    included = set(task.get('edge_ids', []))
    excluded = set(task.get('exclude_edge_ids', []))
    restored = set(task.get('restore_edge_ids', []))
    if task.get('dataset_versions') and graph['version'] not in task['dataset_versions']:
        raise ValueError('نسخة الشبكة لا تطابق توزيع المهام؛ احتفظ بملف legislation_graph.json الحالي.')
    for edge in graph['edges']:
        if edge['id'] in excluded:
            continue
        if task.get('parent_types') and graph['nodes'][edge['parent']]['kind'] not in task['parent_types']:
            continue
        if task.get('child_types') and graph['nodes'][edge['child']]['kind'] not in task['child_types']:
            continue
        if task.get('statuses') and edge['status'] not in task['statuses']:
            continue
        if (task.get('explicit_edge_ids') or included) and edge['id'] not in included and edge['id'] not in restored:
            continue
        bucket = int(hashlib.sha256(edge['id'].encode()).hexdigest(), 16) % task.get('partitions', 1)
        if edge['id'] in restored or bucket == task.get('partition', 0):
            result.append(edge)
    return result


def resolve_handoffs(tasks, rows):
    """Keep newly discovered previous-owner decisions with their original owner.

    No writes to the event log. Static transfer IDs keep allocations stable after
    the recipient starts work. A stale donor session can still append an event;
    both histories remain available and the dashboard flags conflicting verdicts.
    """
    result = copy.deepcopy(tasks)
    touched = {(r['reviewer'], r['edge_id']) for r in rows}
    for recipient, task in result.items():
        blocked = set(task.get('exclude_edge_ids', []))
        for transfer in task.get('incoming_transfers', []):
            donor = transfer['from']
            for eid in transfer['edge_ids']:
                if any((name, eid) in touched for name in result if name != recipient):
                    blocked.add(eid)
                    original = result[donor]
                    original['exclude_edge_ids'] = [x for x in original.get('exclude_edge_ids', []) if x != eid]
                    original.setdefault('restore_edge_ids', []).append(eid)
        task['exclude_edge_ids'] = sorted(blocked)
    return result


def summarize(edges, rows, reviewer):
    ids = {edge['id'] for edge in edges}
    latest = {}
    for row in rows:
        if row['reviewer'] == reviewer and row['edge_id'] in ids:
            latest[row['edge_id']] = row
    done = {eid for eid, row in latest.items() if row['verdict'] in ('CONFIRM', 'REJECT')}
    pending = {eid for eid, row in latest.items() if row['verdict'] == 'NEEDS_REVIEW'}
    return {'latest': latest, 'done': done, 'pending': pending,
            'unreviewed': ids - set(latest), 'total': len(ids)}
