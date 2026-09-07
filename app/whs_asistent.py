import getpass
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from console_style import notice

DATA = Path(__file__).resolve().parent.parent / 'data'


def read_config():
    path = DATA / 'config.json'
    if not path.exists():
        return {'instances': {}}
    try:
        result = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        raise ValueError('Konfiguraci nelze nacist; nebyla prepsana.') from None
    if not isinstance(result, dict) or not isinstance(result.get('instances'), dict):
        raise ValueError('Neplatny format konfigurace.')
    return result


def valid_url(value):
    try:
        p = urlsplit(value)
        p.port
        return bool(p.scheme == 'https' and p.hostname and not p.username and not p.password and not p.query and not p.fragment)
    except (ValueError, TypeError):
        return False


def save_config(config):
    DATA.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=DATA, delete=False) as f:
            temp = Path(f.name)
            json.dump(config, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, DATA / 'config.json')
    finally:
        if temp and temp.exists():
            temp.unlink()


def ask(label, default=''):
    return input(label + (f' [{default}]' if default else '') + ': ').strip() or default


def wizard():
    notice('WHS ASISTENT - nastaveni')
    print('Heslo se pri psani nezobrazuje. V lokalnim config.json bude ulozene jako text; soubor nesdilejte.')
    while True:
        config = read_config()
        print('Instance:', ', '.join(config['instances']) or 'zadne')
        name = ask('Nazev instance (napr. sys2)')
        if not name:
            continue
        old = config['instances'].get(name, {})
        if not isinstance(old, dict):
            raise ValueError('Neplatna existujici instance.')
        url = ask('HTTPS adresa PIP', old.get('url', 'https://pip-sys2.vodafone.cz/' if name == 'sys2' else ''))
        if not valid_url(url):
            notice('Neplatna HTTPS adresa.', 'error')
            continue
        login = ask('Login', old.get('login', ''))
        if not login:
            continue
        keep = old.get('url') == url and old.get('login') == login and bool(old.get('password'))
        password = getpass.getpass('Heslo' + (' (Enter ponecha ulozene)' if keep else '') + ': ')
        if not password and keep:
            password = old['password']
        elif not password or password != getpass.getpass('Heslo znovu: '):
            notice('Prazdne heslo nebo hesla nesouhlasi. Nic nebylo ulozeno.', 'warning')
            continue
        print(f'Instance: {name}\nAdresa: {url}\nLogin: {login}')
        if ask('Ulozit? [y/n]').lower() == 'y':
            config['instances'][name] = dict(old, url=url, login=login, password=password)
            save_config(config)
            notice('Ulozeno.', 'success')
        if ask('Nastavit dalsi instanci? [y/n]').lower() != 'y':
            return


if __name__ == '__main__':
    try:
        wizard()
    except (KeyboardInterrupt, EOFError):
        print('\nPreruseno.')
    except (OSError, ValueError):
        notice('Nastaveni nelze nacist nebo ulozit. Overte konfiguraci a prava ke slozce.', 'error')
        raise SystemExit(1)
