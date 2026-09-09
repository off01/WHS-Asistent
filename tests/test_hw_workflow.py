import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from hw_workflow import HardwarePip, EARLY_QUESTION, HW_QUESTION, confirmation_xpath
from pip_tool import teams_text
from selenium.common.exceptions import TimeoutException

ORDER = 'WHS_SO_08000006786'


class HardwareTests(unittest.TestCase):
    def pip(self):
        pip = object.__new__(HardwarePip)
        for name in ('identity', 'show', 'hide', 'open_order', 'text', 'by_id',
                     'click_text', 'interact', 'one', 'modal_gone', 'verify_manually'):
            setattr(pip, name, Mock())
        pip.journal = Mock()
        pip.wait = Mock()
        pip.read = lambda action: action()
        pip.by_id.return_value.text = '84-A6-AB-94-E8-B9'
        pip.stage_state = Mock(return_value=None)
        pip.completed = Mock(return_value=True)
        pip.status = Mock(return_value='WHS HFC Instalace - Registrace CM provedena')
        return pip

    def test_empty_mac_blocks_hardware_before_any_action(self):
        for value in ('', '   ', '\n\t', '\u00a0'):
            with self.subTest(value=value):
                pip = self.pip()
                pip.by_id.return_value.text = value
                with self.assertRaisesRegex(RuntimeError, 'MAC adresa není vyplněna'):
                    pip.install_hardware(ORDER)
                pip.interact.assert_not_called()
                pip.journal.write.assert_not_called()

    def test_mac_formats_are_not_validated(self):
        for value in ('84-A6-AB-94-E8-B9', '84:a6:ab:94:e8:b9', '84A6AB94E8B9',
                      '84a6.ab94.e8b9', ' jiný údaj '):
            with self.subTest(value=value):
                pip = self.pip()
                pip.by_id.return_value.text = value
                pip.require_hw_ready(ORDER)
                pip.by_id.assert_called_with('stdText507_T')

    def test_mac_disappearing_before_confirmation_blocks_send(self):
        pip = self.pip()
        pip.by_id.return_value.text = ''
        action = Mock()
        with self.assertRaisesRegex(RuntimeError, 'MAC adresa není vyplněna'):
            pip.send_once(ORDER, 'HW', action)
        action.assert_not_called()
        pip.journal.write.assert_not_called()

    def test_dry_run_does_not_install_or_close(self):
        pip = self.pip()
        pip.install_hardware = Mock()
        pip.close_order = Mock()
        self.assertEqual(pip.process(ORDER, False), 'KONTROLA_OK')
        pip.install_hardware.assert_not_called()
        pip.close_order.assert_not_called()
        pip.journal.write.assert_not_called()

    def test_earlier_states_never_install_hardware_even_when_resuming(self):
        for state in ('Čeká na přiřazení', 'Čeká se na odpověď WHS partnera'):
            for previous in (None, 'HW_ODESILANI', 'HW_HOTOVO'):
                with self.subTest(state=state, previous=previous):
                    pip = self.pip()
                    pip.status.return_value = 'WHS HFC Instalace - ' + state
                    pip.stage_state.return_value = previous
                    with self.assertRaisesRegex(RuntimeError, 'až po Registrace CM provedena'):
                        pip.install_hardware(ORDER)
                    pip.interact.assert_not_called()
                    pip.click_text.assert_not_called()
                    pip.journal.write.assert_not_called()

    def test_state_change_before_confirmation_blocks_submission(self):
        pip = self.pip()
        pip.status.return_value = 'WHS HFC Instalace - Čeká se na odpověď WHS partnera'
        action = Mock()
        with self.assertRaises(RuntimeError):
            pip.send_once(ORDER, 'HW', action)
        action.assert_not_called()
        pip.journal.write.assert_not_called()

    def test_unchanged_header_does_not_count_as_closed(self):
        pip = self.pip()
        pip.install_hardware = Mock()
        pip.close_order = Mock(return_value='HOTOVO')
        self.assertEqual(pip.process(ORDER, True), 'HOTOVO')
        pip.install_hardware.assert_called_once_with(ORDER)
        pip.close_order.assert_called_once_with(ORDER)

    def test_pending_hardware_is_verified_not_replayed(self):
        pip = self.pip()
        pip.stage_state.return_value = 'HW_ODESILANI'
        pip.install_hardware(ORDER)
        pip.verify_manually.assert_called_once()
        pip.click_text.assert_not_called()
        pip.interact.assert_not_called()
        pip.journal.write.assert_called_once_with(ORDER, 'HW_HOTOVO')

    def test_interrupt_leaves_pending_marker(self):
        pip = self.pip()
        def interrupted():
            pip.journal.write.assert_called_once_with(ORDER, 'HW_ODESILANI')
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            pip.send_once(ORDER, 'HW', interrupted)

    def test_early_dialog_confirmed_once_then_verified(self):
        pip = self.pip()
        pip.wait.until.return_value = [Mock()]
        self.assertEqual(pip.close_order(ORDER), 'HOTOVO')
        self.assertEqual(pip.text.return_value.click.call_count, 2)
        pip.verify_manually.assert_called_once_with(ORDER, 'úplné uzavření objednávky')
        self.assertEqual(pip.journal.write.call_args_list[-1].args, (ORDER, 'UZAVRENI_HOTOVO'))

    def test_no_date_dialog_does_not_click_yes(self):
        pip = self.pip()
        pip.wait.until.side_effect = TimeoutException()
        self.assertEqual(pip.close_order(ORDER), 'HOTOVO')
        pip.text.return_value.click.assert_called_once()
        self.assertEqual(pip.text.call_count, 1)

    def test_verification_failure_does_not_report_success(self):
        pip = self.pip()
        pip.wait.until.side_effect = TimeoutException()
        pip.verify_manually.side_effect = RuntimeError('Not confirmed')
        with self.assertRaises(RuntimeError):
            pip.close_order(ORDER)
        pip.journal.write.assert_called_once_with(ORDER, 'UZAVRENI_ODESILANI')
        self.assertEqual(teams_text([(ORDER, 'VYZADUJE_OVERENI')], True), '')

    def test_journal_isolated_by_order_origin_and_stage(self):
        pip = self.pip()
        del pip.stage_state
        pip.entry = {'url': 'https://pip-test.vodafone.cz/'}
        with tempfile.TemporaryDirectory() as folder:
            pip.journal.path = Path(folder) / 'journal.jsonl'
            rows = [dict(url=pip.entry['url'], order=ORDER, result=result)
                    for result in ('HW_ODESILANI', 'HOTOVO', 'UZAVRENI_HOTOVO')]
            rows.append(dict(url='https://other.example/', order=ORDER, result='HW_HOTOVO'))
            pip.journal.path.write_text('\n'.join(map(json.dumps, rows)), encoding='utf-8')
            self.assertEqual(pip.stage_state(ORDER, 'HW'), 'HW_ODESILANI')
            self.assertEqual(pip.stage_state(ORDER, 'UZAVRENI'), 'UZAVRENI_HOTOVO')

    def test_manual_rejection_cannot_be_success(self):
        pip = self.pip()
        del pip.verify_manually
        with patch('builtins.input', return_value='n'):
            with self.assertRaises(RuntimeError):
                pip.verify_manually(ORDER, 'uzavření')
        pip.hide.assert_not_called()

    def test_confirmations_are_scoped_to_specific_questions(self):
        self.assertIn(HW_QUESTION, confirmation_xpath(HW_QUESTION))
        self.assertIn(EARLY_QUESTION, confirmation_xpath(EARLY_QUESTION))
        self.assertIn('not(.//*', confirmation_xpath(HW_QUESTION))
