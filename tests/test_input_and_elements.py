import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import StaleElementReferenceException, ElementNotInteractableException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import pip_tool as tool


class InputElementTests(unittest.TestCase):
    def test_window_errors_do_not_escape_error_recovery(self):
        from selenium.common.exceptions import WebDriverException
        pip = self.pip()
        pip.d = Mock()
        pip.d.maximize_window.side_effect = WebDriverException("failed to change window state")
        pip.d.minimize_window.side_effect = WebDriverException("failed to change window state")
        with patch.object(tool, 'notice') as notice:
            pip.show()
            pip.hide()
        self.assertEqual(notice.call_count, 2)
        pip.d.quit.assert_not_called()

    def test_exact_length_and_deduplication(self):
        self.assertEqual(tool.extract_ids('Zpráva: WHS_SO_08000006785, WHS_SO_08000006785\nWHS_SO_08000006786'),
                         ['WHS_SO_08000006785', 'WHS_SO_08000006786'])

    def test_invalid_ids_reject_whole_batch_without_truncation(self):
        for bad in ('WHS_SO_0800006785', 'WHS_SO_008000006785', 'WHS_SO_08000006785x', 'WHS_SO_'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tool.extract_ids('WHS_SO_08000006786 ' + bad)

    def pip(self):
        pip = object.__new__(tool.Pip)
        pip.wait = WebDriverWait(Mock(), .2, poll_frequency=.001,
                                 ignored_exceptions=(StaleElementReferenceException,))
        return pip

    def test_stale_click_relocates_element(self):
        pip = self.pip()
        old, fresh = Mock(), Mock()
        old.click.side_effect = StaleElementReferenceException()
        locate = Mock(side_effect=[old, fresh])
        pip.interact(locate, lambda e: e.click(), 'test')
        fresh.click.assert_called_once()
        self.assertEqual(locate.call_count, 2)

    def test_noninteractable_retried_without_skipping_order(self):
        pip = self.pip()
        element = Mock()
        element.send_keys.side_effect = [ElementNotInteractableException(), None]
        pip.interact(lambda: element, lambda e: e.send_keys('value'), 'test')
        self.assertEqual(element.send_keys.call_count, 2)

    def test_stale_read_retried(self):
        pip = self.pip()
        action = Mock(side_effect=[StaleElementReferenceException(), False])
        self.assertIs(pip.read(action), False)

    def test_overview_waits_for_modal_and_enabled_field(self):
        pip = self.pip()
        pip.check_origin = Mock()
        field = Mock()
        field.get_property.return_value = False
        field.is_enabled.side_effect = [False, True]
        modal_checks = iter([[Mock()], [], []])
        pip.visible = lambda xpath: next(modal_checks) if 'CURTAIN' in xpath else [field]
        self.assertIs(pip.ready_overview(), field)
