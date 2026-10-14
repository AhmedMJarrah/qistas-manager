"""Append-only Google Sheets review events. No local or PostgreSQL fallback."""
from datetime import datetime, timezone
import json
import re
import threading
from urllib.parse import urlparse
import gspread

HEADERS = ['event_id', 'dataset', 'dataset_version', 'edge_id', 'reviewer',
           'verdict', 'note', 'evidence_url', 'evidence_text', 'created_at',
           'parent_id', 'parent_name', 'parent_type', 'child_id', 'child_name',
           'child_type', 'source_status']
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


class StoreError(Exception):
    pass


class SaveUncertain(StoreError):
    pass


def validate_event(event):
    if not re.fullmatch(r'[0-9a-f-]{36}', str(event.get('event_id', ''))):
        raise ValueError('معرّف الحفظ غير صالح.')
    if event.get('verdict') not in ('CONFIRM', 'REJECT', 'NEEDS_REVIEW'):
        raise ValueError('اختر قرار المراجعة أولاً.')
    if not event.get('reviewer') or not event.get('edge_id') or not event.get('dataset_version'):
        raise ValueError('بيانات المراجع أو الرابط ناقصة.')
    note = event.get('note', '').strip()
    url = event.get('evidence_url', '').strip()
    text = event.get('evidence_text', '').strip()
    if len(note) > 4000:
        raise ValueError('سبب القرار يتجاوز 4000 حرف.')
    if len(url) > 2000 or len(text) > 12000:
        raise ValueError('الدليل يتجاوز الحد المسموح.')
    if url and (urlparse(url).scheme not in ('http', 'https') or not urlparse(url).netloc):
        raise ValueError('رابط الدليل يجب أن يكون عنوان http أو https صحيحاً.')


def make_event(event_id, graph, edge, reviewer, verdict, note, url, text):
    parent, child = graph['nodes'][edge['parent']], graph['nodes'][edge['child']]
    event = dict(event_id=event_id, dataset='EXTRACTED', dataset_version=graph['version'],
                 edge_id=edge['id'], reviewer=reviewer, verdict=verdict,
                 note=note.strip(), evidence_url=url.strip(), evidence_text=text.strip(),
                 created_at=datetime.now(timezone.utc).isoformat(timespec='microseconds'),
                 parent_id=parent['id'], parent_name=parent['name'], parent_type=parent['kind'],
                 child_id=child['id'], child_name=child['name'], child_type=child['kind'],
                 source_status=edge['status'])
    validate_event(event)
    return event


class SheetsStore:
    def __init__(self, sheet_id, worksheet_name, credentials):
        if not re.fullmatch(r'[A-Za-z0-9_-]{20,}', str(sheet_id)):
            raise StoreError('ضع SHEET_ID الصحيح من رابط Google Sheets في Secrets.')
        self.sheet_id = sheet_id
        self.worksheet_name = worksheet_name
        self._lock = threading.RLock()
        try:
            if isinstance(credentials, str):
                credentials = json.loads(credentials)
            if not credentials or credentials.get('type') != 'service_account':
                raise ValueError('Service account required')
            self._client = gspread.service_account_from_dict(dict(credentials), scopes=SCOPES)
            self._client.set_timeout(20)
            self._sheet = self._client.open_by_key(sheet_id)
            self._worksheet = None
        except Exception:
            raise StoreError('تعذّر فتح Google Sheets. افحص حساب الخدمة وSHEET_ID ومشاركة الملف معه كمحرّر.') from None

    def initialize(self):
        """Run once before launch; never overwrite an existing sheet's header/data."""
        with self._lock:
            try:
                ws = self._sheet.worksheet(self.worksheet_name)
            except gspread.WorksheetNotFound:
                ws = self._sheet.add_worksheet(title=self.worksheet_name, rows=1000, cols=len(HEADERS))
            first = ws.row_values(1)
            if not first:
                ws.update(values=[HEADERS], range_name='A1:Q1', value_input_option='RAW')
                ws.freeze(rows=1)
                ws.format('A1:Q1', {'textFormat': {'bold': True}})
            elif first != HEADERS:
                raise StoreError('عناوين تبويب المراجعات مختلفة؛ لم تُعدّل أي بيانات. اختر تبويباً جديداً فارغاً.')
            self._worksheet = ws
            return ws

    def _ws(self):
        if self._worksheet is None:
            try:
                self._worksheet = self._sheet.worksheet(self.worksheet_name)
            except gspread.WorksheetNotFound:
                raise StoreError('شغّل setup_google_sheet.py مرة واحدة لتجهيز تبويب المراجعات.') from None
        return self._worksheet

    def _read(self):
        values = self._ws().get_values('A:Q')
        if not values or values[0] != HEADERS:
            raise StoreError('عناوين جدول المراجعات غير صحيحة. تواصل مع مسؤول المشروع.')
        rows, seen = [], set()
        for cells in values[1:]:
            if not any(cells):
                continue
            if len(cells) > len(HEADERS):
                raise StoreError('يوجد صف غير صالح في سجل المراجعات.')
            row = dict(zip(HEADERS, cells + [''] * (len(HEADERS) - len(cells))))
            if not row['event_id'] or not row['edge_id'] or not row['reviewer'] or row['verdict'] not in ('CONFIRM', 'REJECT', 'NEEDS_REVIEW'):
                raise StoreError('يوجد صف مراجعة ناقص أو غير صالح؛ يلزم فحصه قبل المتابعة.')
            if row['event_id'] in seen:
                continue
            seen.add(row['event_id'])
            rows.append(row)
        return rows

    def read(self, dataset, version):
        with self._lock:
            try:
                versions = {version} if isinstance(version, str) else set(version)
                return [r for r in self._read() if r['dataset'] == dataset and r['dataset_version'] in versions]
            except StoreError:
                raise
            except Exception:
                raise StoreError('تعذّرت قراءة سجل Google Sheets. حاول التحديث بعد قليل.') from None

    def save(self, event):
        validate_event(event)
        with self._lock:
            # Reuse event_id on retries; append is not automatically retried.
            try:
                existing = self._read()
            except StoreError:
                raise
            except Exception:
                raise StoreError('تعذّر التحقق من سجل الحفظ؛ لم نرسل قرارك. حاول مجدداً.') from None
            for row in existing:
                if row['event_id'] == event['event_id']:
                    if any(row.get(k, '') != str(event.get(k, '')) for k in HEADERS):
                        raise StoreError('معرّف الحفظ موجود ببيانات مختلفة؛ تواصل مع المسؤول.')
                    return event['event_id']
            try:
                self._ws().append_row([str(event.get(k, '')) for k in HEADERS],
                                      value_input_option='RAW', insert_data_option='INSERT_ROWS',
                                      table_range='A:Q')
            except Exception:
                # A timeout may occur after Google committed the row.
                try:
                    if any(r['event_id'] == event['event_id'] for r in self._read()):
                        return event['event_id']
                except Exception:
                    pass
                raise SaveUncertain('لم نتمكن من تأكيد الحفظ. احتفظ بالنص واضغط حفظ مجدداً؛ سيُفحص معرّف المحاولة نفسه أولاً.') from None
            return event['event_id']
