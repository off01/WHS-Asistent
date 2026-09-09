"""HW installation and closure; unchanged headers require human verification."""
from console_style import notice
from pip_tool import Pip, OrderNotFound, SUCCESS, status_value

INSTALL_HW = 'Instalace WHS - HW'
CLOSE_ORDER = 'Objednávka úspěšně dokončena'
HW_QUESTION = 'Opravdu potvrdit, že je celý rozsah objednávky úspěšně proveden?'
EARLY_QUESTION = 'Opravdu chcete dokončit objednávku před termínem její realizace?'


def run_workflow(pip, order, execute, mode):
    if mode == 'realizace':
        result = Pip.process(pip, order, execute)
        if result in ('HOTOVO', 'JIZ_HOTOVO'):
            pip.journal.write(order, result)
            return 'REALIZACE_HOTOVO'
        return result
    try:
        pip.open_order(order)
    except OrderNotFound:
        notice(f'{order} NEDOHLEDANO – ověřte WHS objednávku ručně v systému.', 'warning')
        return 'NEDOHLEDANO'
    state = status_value(pip.status())
    if state == 'Čeká na přiřazení':
        result = Pip.process(pip, order, execute)
        if result not in ('HOTOVO', 'JIZ_HOTOVO'):
            return result
        # Resolve the socket submission marker before entering the HW phase.
        pip.journal.write(order, result)
        state = status_value(pip.status())
    if state == 'Čeká se na odpověď WHS partnera':
        notice(f'{order}: čeká na registraci CM. Po registraci zadejte stejné WHS ID znovu; proces naváže HW.', 'warning')
        return 'CEKA_NA_CM'
    hw = HardwarePip(pip.d, pip.entry, pip.journal, pip.wait._timeout)
    return hw.process(order, execute)


def confirmation_xpath(question):
    predicate = ("starts-with(@id,'weMessageDlg') and "
                 ".//div[@class='weButtonDefaultLightText' and normalize-space(.)='Ano'] and "
                 f"contains(normalize-space(.),'{question}')")
    return f'//*[{predicate} and not(.//*[{predicate}])]'


class HardwarePip(Pip):
    def require_hw_ready(self, order):
        self.identity(order)
        state = status_value(self.status())
        if state != 'Registrace CM provedena':
            raise RuntimeError(f'Instalace HW není povolena ve stavu {state}. '
                               'Pokračovat lze až po Registrace CM provedena.')
        if not self.completed(order):
            raise RuntimeError('Realizace zásuvky nebyla potvrzena. Instalace HW nebyla spuštěna.')
        if not self.read(lambda: self.by_id('stdText507_T').text.strip()):
            raise RuntimeError('MAC adresa není vyplněna. Instalace HW nebyla spuštěna.')

    def verify_manually(self, order, stage):
        self.show()
        notice(f'{order}: ověřte v PIP {stage}. Hlavička sama výsledek nepotvrzuje.', 'warning')
        while True:
            answer = input('Je tento krok prokazatelně úspěšně dokončen? [y/n]: ').strip().lower()
            if answer == 'n':
                raise RuntimeError('Výsledek nebyl potvrzen. Krok se automaticky neopakuje.')
            if answer == 'y':
                self.identity(order)
                if self.visible("//*[@id='NGMODALWINDOW_CURTAIN']"):
                    raise RuntimeError('Dialog je stále otevřený. Výsledek nebyl potvrzen.')
                self.hide()
                return

    def stage_state(self, order, stage):
        import json
        state = None
        if self.journal.path.exists():
            for line in self.journal.path.read_text(encoding='utf-8').splitlines():
                row = json.loads(line)
                if (row.get('url', '').rstrip('/') == self.entry['url'].rstrip('/')
                        and row.get('order') == order
                        and row.get('result') in (stage + '_ODESILANI', stage + '_HOTOVO')):
                    state = row['result']
        return state

    def send_once(self, order, stage, action):
        self.identity(order)
        if stage == 'HW':
            self.require_hw_ready(order)
        # Persist before clicking, including Ctrl+C and disconnected driver cases.
        self.journal.write(order, stage + '_ODESILANI')
        action()

    def modal_gone(self):
        self.wait.until(lambda _: not self.visible("//*[@id='NGMODALWINDOW_CURTAIN']"),
                        'Potvrzovací dialog se nezavřel; ověřte PIP.')

    def install_hardware(self, order):
        self.require_hw_ready(order)
        previous = self.stage_state(order, 'HW')
        if previous:
            self.verify_manually(order, 'dříve odeslanou instalaci HW')
            self.journal.write(order, 'HW_HOTOVO')
            return
        self.interact(lambda: self.by_id('stdDropDownListField519_B1'),
                      lambda e: e.click(), 'Výsledek instalace HW')
        self.interact(lambda: self.text('wxpDropDownText', SUCCESS, self.by_id('stdDropDownListField519_DD')),
                      lambda e: e.click(), SUCCESS)
        self.wait.until(lambda _: self.by_id('stdDropDownListField519_T').get_property('value') == SUCCESS)
        self.require_hw_ready(order)
        self.click_text('wxpButtonText', INSTALL_HW)
        yes = self.text('weButtonDefaultLightText', 'Ano', self.one(confirmation_xpath(HW_QUESTION)))
        self.send_once(order, 'HW', yes.click)
        self.modal_gone()
        self.verify_manually(order, 'instalaci HW')
        self.journal.write(order, 'HW_HOTOVO')

    def close_order(self, order):
        if self.stage_state(order, 'UZAVRENI'):
            self.verify_manually(order, 'dříve odeslané uzavření objednávky')
            self.journal.write(order, 'UZAVRENI_HOTOVO')
            return 'JIZ_HOTOVO'
        self.click_text('wxpPagesPageText', 'Uzavírací kódy')
        button = self.text('wxpButtonText', CLOSE_ORDER)
        self.send_once(order, 'UZAVRENI', button.click)
        # The date dialog is optional. Never repeat the close button or confirm
        # an unrelated dialog. A timeout is followed by explicit verification.
        from selenium.common.exceptions import TimeoutException
        try:
            dialog = self.wait.until(lambda _: self.visible(confirmation_xpath(EARLY_QUESTION)))
        except TimeoutException:
            dialog = []
        if dialog:
            if len(dialog) != 1:
                raise RuntimeError('Nejednoznačný dialog uzavření objednávky.')
            self.identity(order)
            self.text('weButtonDefaultLightText', 'Ano', dialog[0]).click()
        self.modal_gone()
        self.verify_manually(order, 'úplné uzavření objednávky')
        self.journal.write(order, 'UZAVRENI_HOTOVO')
        return 'HOTOVO'

    def process(self, order, execute):
        try:
            self.open_order(order)
        except OrderNotFound:
            notice(f'{order} NEDOHLEDANO – ověřte WHS objednávku ručně v systému.', 'warning')
            return 'NEDOHLEDANO'
        if self.stage_state(order, 'UZAVRENI'):
            if not execute:
                return 'VYZADUJE_OVERENI'
            return self.close_order(order)
        self.require_hw_ready(order)
        if not self.stage_state(order, 'HW'):
            self.text('wxpButtonText', INSTALL_HW)
            self.by_id('stdDropDownListField519_T')
            self.by_id('stdDropDownListField519_B1')
        if not execute:
            return 'KONTROLA_OK'
        self.install_hardware(order)
        return self.close_order(order)

    def process_with_session(self, order, execute):
        if self.logged_out():
            self.ensure_session()
        # A server write may have succeeded despite logout or a driver error.
        return self.process(order, execute)
