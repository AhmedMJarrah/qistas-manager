"""Prepare only the review tab using local secrets; never prints credentials."""
from pathlib import Path
import tomllib
from sheets_store import SheetsStore, StoreError


def main():
    path = Path(__file__).resolve().parent / '.streamlit' / 'secrets.toml'
    try:
        config = tomllib.loads(path.read_text(encoding='utf-8'))
        store = SheetsStore(config['SHEET_ID'], config.get('SHEET_NAME', 'qistas_reviews'),
                            config['gcp_service_account'])
        store.initialize()
        print('تم تجهيز تبويب المراجعات. الحسابات والبيانات السابقة لم تتغير.')
    except StoreError as exc:
        raise SystemExit(str(exc))
    except Exception:
        raise SystemExit('تعذّر التجهيز. افحص .streamlit/secrets.toml وSHEET_ID وحساب الخدمة وصلاحياته.') from None


if __name__ == '__main__':
    main()
