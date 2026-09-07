import argparse
import json
import os
import re
import signal
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlsplit
from whs_asistent import DATA, read_config, valid_url
from console_style import notice, accent

SUCCESS = 'Úspěšně provedena'
TARGET = 'WHS Instalace - Čeká se na odpověď WHS partnera'
SOURCE = 'WHS Instalace - Čeká na přiřazení'
INSTALL = 'Instalace WHS - Zásuvka'


def extract_ids(text):
    return list(dict.fromkeys(re.findall(r'(?<!\w)WHS_SO_[0-9]+(?!\w)', text.replace('\\_', '_'))))


def teams_text(results, execute):
    if not execute:
        return ''
    completed = dict.fromkeys(order for order, result in results if result in ('HOTOVO', 'JIZ_HOTOVO'))
    return '\n'.join(f'{order} dokončeno' for order in completed)


def print_teams(results, execute):
    text = teams_text(results, execute)
    if text:
        notice('\nZprávy o dokončení')
        print(text)
        print()


def origin(url):
    p = urlsplit(url)
    return p.scheme, p.hostname, p.port or 443


def close_browser(driver):
    previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        print(accent('Ukončuje se… zavírám prohlížeč.', 'warning'), flush=True)
        driver.quit()
    except Exception:
        raise RuntimeError('Zavreni Edge se nepodarilo potvrdit. Zavrete okno WHS Asistenta rucne.') from None
    finally:
        signal.signal(signal.SIGINT, previous)


def dialog_xpath():
    predicate = ("starts-with(@id,'weMessageDlg') and "
                 ".//div[@class='weButtonDefaultLightText' and normalize-space(.)='Ano'] and "
                 "contains(normalize-space(.),'Opravdu potvrdit, že je instalace zásuvky úspěšně provedena?')")
    return f'//*[{predicate} and not(.//*[{predicate}])]'


class Journal:
    def __init__(self, name, url):
        self.name, self.url = name, url
        self.path = DATA / 'vysledky.jsonl'

    def write(self, order, result):
        DATA.mkdir(parents=True, exist_ok=True)
        with self.path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(), instance=self.name,
                                   url=self.url, order=order, result=result), ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())

    def uncertain(self, order):
        state = None
        if self.path.exists():
            for line in self.path.read_text(encoding='utf-8').splitlines():
                row = json.loads(line)
                if row.get('url', 'https://pip-sys2.vodafone.cz/').rstrip('/') != self.url.rstrip('/') or row['order'] != order:
                    continue
                if row['result'] in ('ODESILANI', 'NEJISTE', 'HOTOVO', 'JIZ_HOTOVO'):
                    state = row['result']
        return state in ('ODESILANI', 'NEJISTE')


class Pip:
    def __init__(self, driver, entry, journal, timeout=30):
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.common.exceptions import StaleElementReferenceException
        self.d, self.entry, self.journal = driver, entry, journal
        self.wait = WebDriverWait(driver, timeout, poll_frequency=.3, ignored_exceptions=(StaleElementReferenceException,))

    def visible(self, xpath, scope=None):
        return [e for e in (scope or self.d).find_elements('xpath', xpath) if e.is_displayed()]

    def one(self, xpath, scope=None):
        def find(_):
            found = self.visible(xpath, scope)
            if len(found) > 1:
                raise RuntimeError('Nejednoznacny prvek: ' + xpath)
            return found[0] if found else False
        return self.wait.until(find, 'Prvek nenalezen: ' + xpath)

    def by_id(self, identifier):
        return self.one(f"//*[@id='{identifier}']")

    def text(self, cls, label, scope=None):
        return self.one(f".//div[@class='{cls}' and normalize-space(.)='{label}']", scope)

    def show(self):
        self.d.maximize_window()

    def hide(self):
        self.d.minimize_window()

    def check_origin(self):
        if origin(self.d.current_url) != origin(self.entry['url']):
            raise RuntimeError('Stranka nepatri zvolene instanci.')

    def logged_out(self):
        return bool(self.visible("//input[@type='password']"))

    def session_state(self):
        if self.logged_out():
            return 'login'
        if origin(self.d.current_url) == origin(self.entry['url']) and self.visible("//*[@id='stdEditField84_T']"):
            return 'ready'
        return False

    def login(self):
        if not self.entry.get('login') or not self.entry.get('password'):
            return
        def unique(css):
            def find(_):
                found = [e for e in self.d.find_elements('css selector', css) if e.is_displayed() and e.is_enabled()]
                if len(found) > 1:
                    raise RuntimeError('Nejednoznacny login.')
                return found[0] if found else False
            return self.wait.until(find)
        try:
            selectors = self.entry.get('login_selectors', {})
            username = unique(selectors.get('username', "input[type='text'], input[type='email']"))
            password = unique(selectors.get('password', "input[type='password']"))
            self.check_origin()
            username.clear()
            username.send_keys(self.entry['login'])
            self.check_origin()
            password.clear()
            password.send_keys(self.entry['password'])
            submit = unique(selectors['submit']) if 'submit' in selectors else self.text('weButtonDarkText', 'Přihlásit')
            self.check_origin()
            submit.click()
        except Exception:
            notice('Automaticke prihlaseni se nepodarilo dokoncit. Dokoncete je rucne v Edge.', 'warning')

    def ensure_session(self):
        # Preserve the running application's DOM and session. A page refresh
        # can rebuild generated control IDs. Detect logout in the current UI;
        # process_with_session also handles logout on the next server operation.
        state = self.wait.until(lambda _: self.session_state(), 'Nelze rozpoznat prihlaseni ani prehled.')
        if state == 'login':
            self.show()
            self.login()
            notice('Dokoncete prihlaseni / SMS v Edge. Prehled se rozpozna automaticky, Enter neni potreba.', 'warning')
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.common.exceptions import StaleElementReferenceException
            WebDriverWait(self.d, 600, poll_frequency=1, ignored_exceptions=(StaleElementReferenceException,)).until(
                lambda _: self.session_state() == 'ready', 'Prihlaseni nebylo dokonceno do 10 minut.')
        self.hide()

    def overview(self):
        if not self.visible("//*[@id='stdEditField84_T']"):
            self.by_id('weAppButton284_I').click()
            self.by_id('stdEditField84_T')

    def identity(self, order):
        self.check_origin()
        if self.by_id('stdText332_T').text.strip() != order:
            raise RuntimeError('Detail neodpovida zadanemu WHS ID.')

    def status(self):
        prefix = "starts-with(normalize-space(.),'WHS Instalace - ')"
        return ' '.join(self.one(f'//*[{prefix} and not(.//*[{prefix}])]').text.split())

    def completed(self, order):
        self.identity(order)
        return self.status() == TARGET and not self.visible(f"//div[@class='wxpButtonText' and normalize-space(.)='{INSTALL}']")

    def open_order(self, order):
        from selenium.webdriver.common.keys import Keys
        self.overview()
        self.check_origin()
        field = self.by_id('stdEditField84_T')
        field.send_keys(Keys.CONTROL, 'a')
        field.send_keys(order)
        field.send_keys(Keys.TAB)
        if field.get_property('value') != order:
            raise RuntimeError('Vyhledavaci pole neodpovida zadani.')
        self.text('wxpButtonText', 'Hledat').click()
        def result(_):
            rows = self.visible("//*[@id='stdList157_TB']/tbody/tr[contains(@class,'wxpListBoxRow')]")
            return rows[0] if len(rows) == 1 else False
        row = self.wait.until(result, 'Nenalezen prave jeden vysledek.')
        cells = self.visible(".//div[@class='wxpListBoxText']", row)
        if not cells:
            raise RuntimeError('Chybi bunka vysledku.')
        cells[0].click()
        self.identity(order)  # Never modify a stale search result.
        self.text('wxpPagesPageText', 'Registrace HW').click()
        self.by_id('stdDropDownListField512_T')

    def process(self, order, execute):
        self.open_order(order)
        if self.completed(order):
            return 'JIZ_HOTOVO'
        if self.journal.uncertain(order):
            raise RuntimeError('Predchozi odeslani je nejiste; overte WHS objednavku rucne. Opakovani blokovano.')
        if self.status() != SOURCE:
            raise RuntimeError('Neocekavany vychozi stav: ' + self.status())
        self.text('wxpButtonText', INSTALL)
        if not execute:
            self.by_id('stdDropDownListField512_B1')
            return 'KONTROLA_OK'
        self.by_id('stdDropDownListField512_B1').click()
        self.text('wxpDropDownText', SUCCESS, self.by_id('stdDropDownListField512_DD')).click()
        self.wait.until(lambda _: self.by_id('stdDropDownListField512_T').get_property('value') == SUCCESS)
        self.identity(order)
        if self.status() != SOURCE:
            raise RuntimeError('Vychozi stav se zmenil.')
        self.text('wxpButtonText', INSTALL).click()
        yes = self.text('weButtonDefaultLightText', 'Ano', self.one(dialog_xpath()))
        self.identity(order)
        self.journal.write(order, 'ODESILANI')
        try:
            yes.click()
            self.wait.until(lambda _: self.completed(order), 'Cilovy stav nebyl potvrzen.')
        except Exception:
            self.journal.write(order, 'NEJISTE')
            raise RuntimeError('Nejisty vysledek po Ano. Davka zastavena; overte PIP.') from None
        return 'HOTOVO'

    def process_with_session(self, order, execute):
        try:
            if self.logged_out():
                self.ensure_session()
            return self.process(order, execute)
        except Exception:
            if self.journal.uncertain(order) or not self.logged_out():
                raise
            self.ensure_session()
            return self.process(order, execute)


def main():
    parser = argparse.ArgumentParser(description='WHS Asistent')
    parser.add_argument('--instance')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--driver')
    parser.add_argument('--timeout', type=int, default=30)
    args = parser.parse_args()
    instances = read_config()['instances']
    if not instances:
        print('Chybi instance. Doplnte data/config.json nebo spustte znovu WHS Asistenta.')
        return
    while args.instance not in instances:
        print('Dostupne instance:', ', '.join(instances))
        args.instance = input('Nazev instance: ').strip()
    entry = instances[args.instance]
    if not isinstance(entry, dict) or not valid_url(entry.get('url')):
        raise ValueError('Neplatna konfigurace instance.')
    from selenium import webdriver
    from selenium.webdriver.edge.service import Service
    options = webdriver.EdgeOptions()
    options.add_argument('--start-maximized')
    # Keep console Ctrl+C from killing EdgeDriver before it can close Edge.
    service_options = {'popen_kw': {'creation_flags': subprocess.CREATE_NEW_PROCESS_GROUP}} if os.name == 'nt' else {}
    if args.driver:
        service_options['executable_path'] = args.driver
    driver = webdriver.Edge(options=options, service=Service(**service_options))
    journal = Journal(args.instance, entry['url'])
    pip = Pip(driver, entry, journal, args.timeout)
    try:
        print('INSTANCE:', args.instance, entry['url'])
        notice('ZPRACOVANI' if args.execute else 'REZIM: KONTROLA BEZ ZMEN')
        driver.get(entry['url'])
        pip.ensure_session()
        while True:
            print('Vlozte WHS order. Prazdny radek spusti davku. Ctrl+C ukonci zpracovani.')
            lines = []
            while True:
                line = input()
                if not line.strip():
                    break
                lines.append(line)
            orders = extract_ids('\n'.join(lines))
            if not orders:
                notice('Nenalezena WHS ID.', 'warning')
                continue
            print('Instance:', args.instance, entry['url'], 'WHS objednávky:', ', '.join(orders))
            if args.execute and input('Potvrdit davku? [y/n]: ').strip().lower() != 'y':
                continue
            try:
                pip.ensure_session()
            except Exception as error:
                pip.show()
                notice('Prihlaseni nelze overit. Davka nebyla spustena. Overte Edge a zadejte davku znovu.', 'error')
                print('Duvod:', str(error).splitlines()[0] if str(error) else type(error).__name__)
                continue
            results = []
            for index, order in enumerate(orders):
                try:
                    print(order, 'ZPRACOVAVAM')
                    result = pip.process_with_session(order, args.execute)
                    journal.write(order, result)
                    results.append((order, result))
                    print(order, accent(result, 'success'))
                    pip.overview()
                except KeyboardInterrupt:
                    print_teams(results, args.execute)
                    raise
                except Exception as error:
                    message = str(error).splitlines()[0] if str(error) else type(error).__name__
                    journal.write(order, 'CHYBA: ' + message)
                    pip.show()
                    print(order, accent('CHYBA:', 'error'), message)
                    print('Nezpracovany zbytek davky:', ', '.join(orders[index + 1:]) or 'zadny')
                    print_teams(results, args.execute)
                    results.clear()
                    input('Overte aktualni WHS objednavku v Edge, zavrete modal a vratte se na prehled. Pak Enter: ')
                    pip.by_id('stdEditField84_T')
                    pip.hide()
                    break
            print_teams(results, args.execute)
            if teams_text(results, args.execute):
                input()
    finally:
        close_browser(driver)


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nUkonceno.')
    except Exception as error:
        print(accent('Beh selhal:', 'error'), str(error).splitlines()[0] if str(error) else type(error).__name__)
        raise SystemExit(1)
