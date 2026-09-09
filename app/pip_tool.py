import argparse
import json
import os
import re
import signal
import subprocess
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit
from whs_asistent import DATA, read_config, valid_url
from console_style import notice, accent
from browser import open_browser
from cli_help import USAGE, show_help
from order_input import OrderInput

SUCCESS = 'Úspěšně provedena'
TARGET = 'WHS Instalace - Čeká se na odpověď WHS partnera'
SOURCE = 'WHS Instalace - Čeká na přiřazení'
INSTALL = 'Instalace WHS - Zásuvka'
SEARCH_RETRIES = 5
SEARCH_RETRY_DELAY = 60
ORDER_PREFIXES = ('WHS Instalace - ', 'WHS HFC Instalace - ')


def status_xpath():
    matches = ' or '.join(f"starts-with(normalize-space(.),'{prefix}')" for prefix in ORDER_PREFIXES)
    return f'//*[({matches}) and not(.//*[{matches}])]'


def status_value(header):
    header = ' '.join(header.split())
    for prefix in ORDER_PREFIXES:
        if header.startswith(prefix):
            return header[len(prefix):]
    raise ValueError('Nepodporovany typ WHS objednavky: ' + header)


class OrderNotFound(RuntimeError):
    """The search completed without a visible result."""


def extract_ids(text):
    candidates = list(dict.fromkeys(re.findall(r'(?<!\w)WHS_SO_\w*', text.replace('\\_', '_'))))
    invalid = [value for value in candidates if not re.fullmatch(r'WHS_SO_[0-9]{11}', value)]
    if invalid:
        raise ValueError('Neplatný WHS order: ' + ', '.join(invalid) +
                         '. Očekávám WHS_SO_ a přesně 11 číslic (např. WHS_SO_08000006785). Dávka nebyla spuštěna.')
    return candidates


def extract_orders(text):
    text = text.replace('\\_', '_')
    ids = extract_ids(text)
    orders = {}
    consumed = []
    for match in re.finditer(r'(?<!\w)(WHS_SO_[0-9]{11})(?!\w)([ \t]+--(?:realizace|r)(?=$|\s|[,;]))?', text):
        order, flag = match.groups()
        mode = 'realizace' if flag else 'all'
        if order in orders and orders[order] != mode:
            raise ValueError(f'{order} má dva různé režimy. Uveďte jej pouze v jednom režimu.')
        orders[order] = mode
        if flag:
            consumed.append((match.start(2), match.end(2)))
    remainder = text
    for start, end in reversed(consumed):
        remainder = remainder[:start] + remainder[end:]
    if re.search(r'--\S+', remainder):
        raise ValueError('Neplatný parametr. Použijte WHS_SO_08000006785 --r pro samotnou realizaci. Nápověda: --help.')
    return {order: orders[order] for order in ids}


def teams_text(results, execute):
    if not execute:
        return ''
    completed = dict.fromkeys(order for order, result in results if result in ('HOTOVO', 'JIZ_HOTOVO'))
    lines = [f'{order} dokončeno' for order in completed]
    lines.extend(f'{order} realizace dokončena' for order in dict.fromkeys(
        order for order, result in results if result == 'REALIZACE_HOTOVO') if order not in completed)
    return '\n'.join(lines)


def print_teams(results, execute):
    text = teams_text(results, execute)
    if text:
        notice('\nZprávy o dokončení')
        print(text)
        print()


def recover_batch(pip, remaining):
    proceed = False
    if remaining:
        while True:
            answer = input('Přeskočit tuto WHS objednávku a pokračovat dalšími? [y/n]: ').strip().lower()
            if answer in ('y', 'n'):
                proceed = answer == 'y'
                break
    input('Ověřte aktuální WHS objednávku v Edge, zavřete případný modál a vraťte se na přehled. Pak Enter: ')
    try:
        pip.check_origin()
        pip.ready_overview()
        pip.hide()
    except Exception:
        notice('Přehled se nepodařilo ověřit. Zbytek dávky nebyl spuštěn.', 'error')
        return False
    return proceed


def pause_batch(pip, remaining):
    notice('\nZpracování přerušeno. Prohlížeč zůstává otevřený.', 'warning')
    pip.show()
    print('Aktuální WHS objednávku ověřte ručně; nebude automaticky opakována.')
    print('Zbývající WHS objednávky:', ', '.join(remaining) or 'žádné')
    while True:
        try:
            if remaining:
                answer = input('Přeskočit aktuální WHS objednávku a pokračovat dalšími? [y/n]: ').strip().lower()
                if answer not in ('y', 'n'):
                    continue
                if answer == 'y':
                    input('Zavřete případný modál a vraťte se na přehled v Edge. Pak Enter: ')
                    try:
                        pip.check_origin()
                        pip.ready_overview()
                        pip.hide()
                    except Exception:
                        notice('Přehled nelze ověřit. Zpracování zůstává přerušené.', 'warning')
                        continue
                    return 'continue'
            answer = input('Ukončit zpracování a zavřít prohlížeč? [y/n]: ').strip().lower()
            if answer == 'y':
                return 'exit'
            if answer == 'n':
                return 'new_batch'
        except KeyboardInterrupt:
            notice('Zpracování je přerušené. Prohlížeč zůstává otevřený.', 'warning')


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

    def interact(self, locate, action, label):
        from selenium.common.exceptions import (StaleElementReferenceException,
                                                ElementNotInteractableException,
                                                ElementClickInterceptedException)
        def attempt(_):
            try:
                element = locate()
                if not element or not element.is_displayed() or not element.is_enabled():
                    return False
                action(element)
                return True
            except (StaleElementReferenceException, ElementNotInteractableException, ElementClickInterceptedException):
                return False
        self.wait.until(attempt, 'Prvek není připraven: ' + label)

    def read(self, action):
        # A tuple preserves false/empty results while retrying stale reads.
        return self.wait.until(lambda _: (action(),))[0]

    def click_text(self, cls, label):
        self.interact(lambda: self.text(cls, label), lambda e: e.click(), label)

    def ready_overview(self):
        def ready(_):
            self.check_origin()
            if self.visible("//*[@id='NGMODALWINDOW_CURTAIN']"):
                return False
            fields = self.visible("//*[@id='stdEditField84_T']")
            if len(fields) != 1:
                return False
            field = fields[0]
            return field if field.is_enabled() and not field.get_property('readOnly') else False
        return self.wait.until(ready, 'Vyhledávací pole na přehledu není připravené.')

    def show(self):
        from selenium.common.exceptions import WebDriverException
        try:
            self.d.maximize_window()
        except WebDriverException:
            notice('Edge nelze automaticky zobrazit. Otevřete jeho okno ručně přes hlavní panel.', 'warning')

    def hide(self):
        from selenium.common.exceptions import WebDriverException
        try:
            self.d.minimize_window()
        except WebDriverException:
            notice('Edge nelze minimalizovat. Zpracování pokračuje s otevřeným oknem.', 'warning')

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
            self.interact(lambda: self.by_id('weAppButton284_I'), lambda e: e.click(), 'Zpět na přehled')
        self.ready_overview()

    def identity(self, order):
        self.check_origin()
        if self.read(lambda: self.by_id('stdText332_T').text.strip()) != order:
            raise RuntimeError('Detail neodpovida zadanemu WHS ID.')

    def status(self):
        return self.read(lambda: ' '.join(self.one(status_xpath()).text.split()))

    def completed(self, order):
        self.identity(order)
        state = status_value(self.status())
        if state not in (status_value(TARGET), 'Registrace CM provedena'):
            return False
        if self.read(lambda: self.visible(f"//div[@class='wxpButtonText' and normalize-space(.)='{INSTALL}']")):
            return False
        if state == 'Registrace CM provedena':
            return self.read(lambda: self.by_id('stdDropDownListField512_T').get_property('value')) == SUCCESS
        return True

    def result_table(self):
        # Locate the smallest section containing the order-list headings. The
        # generated numeric control ID can change when PIP rebuilds its page.
        headings = (".//*[starts-with(normalize-space(.),'Objednávka') and not(*)] and "
                    ".//*[normalize-space(.)='Typ' and not(*)] and "
                    ".//*[normalize-space(.)='Stav' and not(*)]")
        sections = f"//*[{headings} and not(.//*[{headings}])]"
        xpath = (f"({sections})/descendant-or-self::table["
                 "substring(@id,string-length(@id)-2)='_TB']")
        def find(_):
            tables = self.visible(xpath)
            if not tables:
                tables = self.visible("//*[@id='stdList157_TB']")
            if len(tables) > 1:
                raise RuntimeError('Nalezeno více tabulek WHS objednávek. Ověřte přehled v PIP.')
            return tables[0] if tables else False
        return self.wait.until(find, 'Tabulku WHS objednávek nelze rozpoznat. Ověřte přehled v PIP.')

    def result_rows(self):
        return self.visible("./tbody/tr[contains(@class,'wxpListBoxRow')]", self.result_table())

    def search_once(self, order):
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.common.keys import Keys
        self.overview()
        self.check_origin()
        def fill(field):
            field.send_keys(Keys.CONTROL, 'a')
            field.send_keys(order)
            field.send_keys(Keys.TAB)
        self.interact(self.ready_overview, fill, 'WHS order')
        if self.read(lambda: self.by_id('stdEditField84_T').get_property('value')) != order:
            raise RuntimeError('Vyhledavaci pole neodpovida zadani.')
        self.click_text('wxpButtonText', 'Hledat')
        def result(_):
            rows = self.result_rows()
            if len(rows) > 1:
                raise RuntimeError('Nalezeno vice vysledku. Overte WHS objednavku rucne.')
            return rows[0] if len(rows) == 1 else False
        try:
            return self.wait.until(result, 'WHS objednavka nebyla nalezena.')
        except TimeoutException:
            # Do not treat logout, a missing table or another page as zero results.
            self.check_origin()
            if self.logged_out():
                raise RuntimeError('Prihlaseni vyprselo behem hledani.') from None
            self.result_table()
            row = result(self.d)
            if row:
                return row
            raise OrderNotFound(order) from None

    def find_order(self, order):
        for attempt in range(SEARCH_RETRIES + 1):
            try:
                return self.search_once(order)
            except OrderNotFound:
                remaining = SEARCH_RETRIES - attempt
                notice(f'{order} se nepodařilo najít. Zbývá opakování: {remaining}.', 'warning')
                if not remaining:
                    raise
                print(f'Další hledání za {SEARCH_RETRY_DELAY} sekund.', flush=True)
                time.sleep(SEARCH_RETRY_DELAY)

    def open_order(self, order):
        self.find_order(order)
        def current_cell():
            rows = self.result_rows()
            if len(rows) > 1:
                raise RuntimeError('Nalezeno vice vysledku. Overte WHS objednavku rucne.')
            if not rows:
                return None
            cells = self.visible(".//div[@class='wxpListBoxText']", rows[0])
            return cells[0] if cells else None
        self.interact(current_cell, lambda e: e.click(), 'Otevření WHS objednávky')
        self.identity(order)  # Never modify a stale search result.
        self.click_text('wxpPagesPageText', 'Registrace HW')
        self.by_id('stdDropDownListField512_T')

    def process(self, order, execute):
        try:
            self.open_order(order)
        except OrderNotFound:
            notice(f'{order} NEDOHLEDANO – ověřte WHS objednávku ručně v systému.', 'warning')
            return 'NEDOHLEDANO'
        if self.completed(order):
            return 'JIZ_HOTOVO'
        if self.journal.uncertain(order):
            raise RuntimeError('Predchozi odeslani je nejiste; overte WHS objednavku rucne. Opakovani blokovano.')
        if status_value(self.status()) != status_value(SOURCE):
            raise RuntimeError('Neocekavany vychozi stav: ' + self.status())
        self.text('wxpButtonText', INSTALL)
        if not execute:
            self.by_id('stdDropDownListField512_B1')
            return 'KONTROLA_OK'
        self.interact(lambda: self.by_id('stdDropDownListField512_B1'), lambda e: e.click(), 'Výsledek instalace zásuvky')
        self.interact(lambda: self.text('wxpDropDownText', SUCCESS, self.by_id('stdDropDownListField512_DD')),
                      lambda e: e.click(), SUCCESS)
        self.wait.until(lambda _: self.by_id('stdDropDownListField512_T').get_property('value') == SUCCESS)
        self.identity(order)
        if status_value(self.status()) != status_value(SOURCE):
            raise RuntimeError('Vychozi stav se zmenil.')
        self.click_text('wxpButtonText', INSTALL)
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
        if getattr(self, 'workflow', 'realizace') == 'all':
            from hw_workflow import run_workflow
            if self.logged_out():
                self.ensure_session()
            return run_workflow(self, order, execute, self.order_modes.get(order, 'all'))
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
    parser = argparse.ArgumentParser(description='WHS Asistent', add_help=False,
                                     allow_abbrev=False, epilog=USAGE,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-h', '--help', '--h', action='help', help='Zobrazit nápovědu a použití.')
    parser.add_argument('--instance')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--workflow', choices=('all', 'realizace', 'hw'), default='all', help=argparse.SUPPRESS)
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
    driver = open_browser(entry['url'], options, Service(**service_options))
    journal = Journal(args.instance, entry['url'])
    if args.workflow == 'hw':
        from hw_workflow import HardwarePip
        pip = HardwarePip(driver, entry, journal, args.timeout)
    else:
        pip = Pip(driver, entry, journal, args.timeout)
    pip.workflow = args.workflow
    try:
        print('INSTANCE:', args.instance, entry['url'])
        notice('ZPRACOVANI' if args.execute else 'REZIM: KONTROLA BEZ ZMEN')
        if args.workflow == 'all':
            print('WHS order = celý postup; WHS order --r = pouze realizace zásuvky. Nápověda: --help / --h.')
            print('Celý postup zahrnuje HW až po registraci CM a uzavření i před termínem.')
        if args.workflow == 'hw':
            notice('INSTALACE HW A UZAVŘENÍ WHS OBJEDNÁVKY')
            print('Potvrzení dávky zahrnuje i dokončení před termínem realizace.')
        pip.ensure_session()
        order_input = OrderInput()
        while True:
            print('Vlozte WHS order. Prazdny radek spusti davku. Ctrl+C během dávky přeruší automat; při zadávání ukončí zpracování.')
            lines = []
            while True:
                line = order_input.read()
                if show_help(line):
                    continue
                if not line.strip():
                    break
                lines.append(line)
            try:
                pip.order_modes = extract_orders('\n'.join(lines))
                orders = list(pip.order_modes)
            except ValueError as error:
                notice(str(error), 'warning')
                continue
            if not orders:
                notice('Nenalezena WHS ID.', 'warning')
                continue
            print('Instance:', args.instance, entry['url'], 'WHS objednávky:', ', '.join(orders))
            if args.workflow == 'all':
                for order in orders:
                    print(order, '– pouze realizace' if pip.order_modes[order] == 'realizace' else '– celý postup')
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
                    if result != 'NEDOHLEDANO':
                        print(order, accent(result, 'warning' if result in ('VYZADUJE_OVERENI', 'CEKA_NA_CM') else 'success'))
                    pip.overview()
                except KeyboardInterrupt:
                    journal.write(order, 'PRERUSENO')
                    action = pause_batch(pip, orders[index + 1:])
                    if action == 'continue':
                        continue
                    if action == 'exit':
                        driver.__dict__['_whs_force_close'] = True
                        print_teams(results, args.execute)
                        return
                    break
                except Exception as error:
                    message = str(error).splitlines()[0] if str(error) else type(error).__name__
                    journal.write(order, 'CHYBA: ' + message)
                    pip.show()
                    print(order, accent('CHYBA:', 'error'), message)
                    print('Nezpracovany zbytek davky:', ', '.join(orders[index + 1:]) or 'zadny')
                    try:
                        proceed = recover_batch(pip, orders[index + 1:])
                    except KeyboardInterrupt:
                        action = pause_batch(pip, orders[index + 1:])
                        if action == 'continue':
                            continue
                        if action == 'exit':
                            driver.__dict__['_whs_force_close'] = True
                            print_teams(results, args.execute)
                            return
                        break
                    except EOFError:
                        print_teams(results, args.execute)
                        raise
                    if proceed:
                        continue
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
