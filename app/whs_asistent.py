import getpass
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from console_style import notice

DATA = Path(__file__).resolve().parent.parent / 'data'
DEFAULT_INSTANCES = {
    'sys2': 'https://pip-sys2.vodafone.cz/',
    'int': 'https://pip-test.vodafone.cz/',
    'pre': 'https://pip-pre.vodafone.cz/',
}


def common_credentials(instances):
    pairs = {(entry.get('login'), entry.get('password'))
             for entry in instances.values() if isinstance(entry, dict)
             and isinstance(entry.get('login'), str) and entry.get('login')
             and isinstance(entry.get('password'), str) and entry.get('password')}
    return next(iter(pairs)) if len(pairs) == 1 else None


def add_presets(config, credentials):
    login, password = credentials
    for name, url in DEFAULT_INSTANCES.items():
        config['instances'].setdefault(name, dict(url=url, login=login, password=password))



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
    credentials = common_credentials(result['instances'])
    if credentials:
        add_presets(result, credentials)
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
    config = read_config()
    credentials = common_credentials(config['instances'])
    if credentials:
        print('Pouziji jiz ulozene prihlasovaci udaje.')
    else:
        while True:
            login = ask('Login pro sys2, int a pre')
            if not login:
                continue
            password = getpass.getpass('Heslo: ')
            if not password or password != getpass.getpass('Heslo znovu: '):
                notice('Prazdne heslo nebo hesla nesouhlasi. Nic nebylo ulozeno.', 'warning')
                continue
            credentials = (login, password)
            break
    add_presets(config, credentials)
    for name in DEFAULT_INSTANCES:
        print(f"Instance: {name} – {config['instances'][name]['url']}")
    print('Existujici instance a jejich prihlasovaci udaje zustanou zachovany.')
    if ask('Ulozit? [y/n]').lower() == 'y':
        save_config(config)
        notice('Ulozeno.', 'success')


if __name__ == '__main__':
    try:
        wizard()
    except (KeyboardInterrupt, EOFError):
        print('\nPreruseno.')
    except (OSError, ValueError):
        notice('Nastaveni nelze nacist nebo ulozit. Overte konfiguraci a prava ke slozce.', 'error')
        raise SystemExit(1)
