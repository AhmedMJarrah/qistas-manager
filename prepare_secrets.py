"""Prepare Cloud Secrets with safe, specific diagnostics. No credential values logged."""
import argparse
import json
from pathlib import Path
import re
import tomllib


class SetupError(Exception):
    pass


def read_private_file(path, label):
    if not path.is_file():
        raise SetupError(f'{label} غير موجود في هذا المسار:\n{path}\nصحّح المسار أو اسم الملف، ثم أعد الأمر.')
    try:
        return path.read_text(encoding='utf-8-sig')
    except UnicodeError:
        raise SetupError(f'{label} ليس بتنسيق UTF-8. افتحه واحفظه بتنسيق UTF-8 ثم أعد الأمر.') from None
    except OSError:
        raise SetupError(f'تعذّرت قراءة {label}. افحص صلاحية الوصول والمسار:\n{path}') from None


def load_accounts(path):
    raw = read_private_file(path, 'ملف الحسابات')
    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError:
        raise SetupError('ملف الحسابات ليس TOML صالحاً. استخدم secrets.toml الأصلي الذي أنشأه setup_reviewers.py؛ لا ترسل محتواه.') from None
    accounts = data.get('reviewers', {})
    if not isinstance(accounts, dict) or not accounts:
        raise SetupError('ملف الحسابات لا يحتوي أقسام [reviewers]. استخدم ملف حسابات المتطوعين الأصلي.')
    for account in accounts.values():
        if not isinstance(account, dict):
            raise SetupError('أحد أقسام reviewers ليس حساباً صالحاً.')
        salt, digest = account.get('salt'), account.get('password_hash')
        if not isinstance(salt, str) or not re.fullmatch(r'[0-9a-fA-F]{32,}', salt) or len(salt)%2:
            raise SetupError('أحد الحسابات يحتوي salt غير صالح. استخدم نسخة الحسابات الأصلية دون تعديلها.')
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
            raise SetupError('أحد الحسابات يحتوي password_hash غير صالح. استخدم نسخة الحسابات الأصلية دون تعديلها.')
    return accounts


def load_google_key(path):
    raw = read_private_file(path, 'ملف مفتاح Google')
    try:
        key = json.loads(raw)
    except json.JSONDecodeError:
        raise SetupError('ملف مفتاح Google ليس JSON صالحاً. استخدم ملف JSON الذي نزّلته من Service Account → Keys.') from None
    if not isinstance(key, dict) or key.get('type') != 'service_account':
        raise SetupError('هذا ليس مفتاح Service Account. نزّل المفتاح بصيغة JSON من حساب الخدمة؛ ملف OAuth أو API Key لا يصلح هنا.')
    for field in ('project_id', 'private_key', 'client_email', 'token_uri'):
        if not isinstance(key.get(field), str) or not key[field].strip():
            raise SetupError('ملف مفتاح Google ناقص. الحقل المطلوب: '+field+'. نزّل مفتاح Service Account الصحيح.')
    private_key = key['private_key']
    if '-----BEGIN PRIVATE KEY-----' not in private_key or '-----END PRIVATE KEY-----' not in private_key or '\n' not in private_key:
        raise SetupError('صيغة private_key غير صحيحة. استخدم JSON الأصلي الذي نزّلته من Google دون نسخ المفتاح يدوياً.')
    return key


def normalize_sheet_id(value):
    match = re.search(r'/spreadsheets/d/([A-Za-z0-9_-]+)', value.strip())
    result = match.group(1) if match else value.strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,}', result):
        raise SetupError('رابط أو معرّف Google Sheets غير صالح.')
    return result


def render_secrets(accounts, key, sheet_id):
    quote = lambda value: json.dumps(str(value), ensure_ascii=False)
    lines = ['# PRIVATE: never commit this file.', 'SHEET_ID = '+quote(sheet_id),
             'SHEET_NAME = "qistas_reviews"', '', '[gcp_service_account]']
    for name, value in key.items():
        if isinstance(value, str):
            lines.append(quote(name)+' = '+quote(value))
    for name, account in accounts.items():
        lines.extend(['', '[reviewers.'+quote(name)+']'])
        for field in ('display_name', 'salt', 'password_hash'):
            lines.append(field+' = '+quote(account.get(field, name)))
    result = '\n'.join(lines)+'\n'
    tomllib.loads(result)
    return result


def write_secrets(destination, result):
    if destination.exists():
        try:
            old = tomllib.loads(destination.read_text(encoding='utf-8-sig'))
            new = tomllib.loads(result)
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            old, new = None, None
        if old is not None and all(old.get(key)==new[key] for key in new):
            print('ملف Secrets الموجود يطابق الإعدادات والحسابات المطلوبة؛ لم نعدّله.')
            return
        raise SetupError('ملف Secrets موجود بإعدادات مختلفة ولم يُعدّل:\n'+str(destination)+
                         '\nاستخدم --output ".streamlit\\secrets_ready.toml" لتوليد نسخة منفصلة، ثم احتفظ بنسخة سرية من الملف القديم قبل استبداله.')
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('x', encoding='utf-8') as stream:
            stream.write(result)
        try:
            destination.chmod(0o600)
        except OSError:
            pass
    except OSError:
        raise SetupError('تعذّرت كتابة ملف Secrets. افحص صلاحيات مجلد الوجهة:\n'+str(destination.parent)) from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--accounts', required=True, type=Path)
    parser.add_argument('--google-key', required=True, type=Path)
    parser.add_argument('--sheet-id', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--check', action='store_true', help='Validate local files without writing or network access')
    args = parser.parse_args()
    destination = args.output or Path(__file__).resolve().parent/'.streamlit'/'secrets.toml'
    try:
        accounts = load_accounts(args.accounts)
        print(f'OK: ملف الحسابات صالح — {len(accounts)} حسابات.')
        key = load_google_key(args.google_key)
        print('OK: ملف Google موجود وبنية Service Account مكتملة.')
        sheet_id = normalize_sheet_id(args.sheet_id)
        print('OK: صيغة معرّف الشيت صالحة.')
        result = render_secrets(accounts, key, sheet_id)
        if args.check:
            print('انتهى فحص الملفات المحلية؛ لم يُكتب ملف ولم يُختبر الاتصال بالشيت بعد.')
            return
        write_secrets(destination, result)
        print('جاهز: '+str(destination))
        print('كلمات المرور والحسابات كما هي. الصق الملف في Streamlit Cloud Secrets فقط.')
    except SetupError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == '__main__':
    main()
