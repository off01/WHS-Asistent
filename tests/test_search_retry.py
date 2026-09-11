import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import pip_tool as tool
from selenium.common.exceptions import TimeoutException


class RetryTests(unittest.TestCase):
    def pip(self):
        return object.__new__(tool.Pip)

    def test_five_retries_then_not_found(self):
        pip = self.pip()
        pip.search_once = Mock(side_effect=tool.OrderNotFound('WHS_SO_00000000001'))
        with patch.object(tool.time, 'sleep') as sleep, patch.object(tool, 'notice') as notice:
            with self.assertRaises(tool.OrderNotFound):
                pip.find_order('WHS_SO_00000000001')
        self.assertEqual(pip.search_once.call_count, 6)
        self.assertEqual(sleep.call_args_list, [call(60)] * 5)
        self.assertEqual([args.args[0].split(': ')[-1] for args in notice.call_args_list],
                         ['5.', '4.', '3.', '2.', '1.', '0.'])

    def test_later_success_stops_retrying(self):
        pip = self.pip()
        row = object()
        pip.search_once = Mock(side_effect=[tool.OrderNotFound(), row])
        with patch.object(tool.time, 'sleep') as sleep, patch.object(tool, 'notice'):
            self.assertIs(pip.find_order('WHS_SO_00000000001'), row)
        sleep.assert_called_once_with(60)
        self.assertEqual(pip.search_once.call_count, 2)

    def test_other_errors_are_not_retried(self):
        pip = self.pip()
        pip.search_once = Mock(side_effect=RuntimeError('multiple results'))
        with patch.object(tool.time, 'sleep') as sleep:
            with self.assertRaises(RuntimeError):
                pip.find_order('WHS_SO_00000000001')
        sleep.assert_not_called()

    def test_ctrl_c_interrupts_delay(self):
        pip = self.pip()
        pip.search_once = Mock(side_effect=tool.OrderNotFound())
        with patch.object(tool.time, 'sleep', side_effect=KeyboardInterrupt), patch.object(tool, 'notice'):
            with self.assertRaises(KeyboardInterrupt):
                pip.find_order('WHS_SO_00000000001')
        pip.search_once.assert_called_once()

    def search_pip(self, rows, logged_out=False):
        pip = self.pip()
        pip.d = Mock()
        pip.overview = Mock()
        pip.interact = Mock()
        pip.click_text = Mock()
        pip.read = lambda action: action()
        pip.check_origin = Mock()
        pip.by_id = Mock()
        pip.by_id.return_value.get_property.return_value = 'WHS_SO_00000000001'
        pip.text = Mock()
        pip.visible = Mock(return_value=rows)
        pip.result_rows = Mock(return_value=rows)
        pip.result_table = Mock()
        pip.logged_out = Mock(return_value=logged_out)
        pip.wait = Mock()
        pip.wait.until.side_effect = TimeoutException()
        return pip

    def test_empty_table_classified_as_not_found(self):
        with self.assertRaises(tool.OrderNotFound):
            self.search_pip([]).search_once('WHS_SO_00000000001')

    def test_changed_table_id_is_accepted(self):
        from selenium.webdriver.support.ui import WebDriverWait
        pip = self.pip()
        pip.wait = WebDriverWait(Mock(), 0)
        table = Mock()
        pip.visible = Mock(return_value=[table])
        self.assertIs(pip.result_table(), table)
        self.assertNotIn('stdList157', pip.visible.call_args.args[0])

    def test_ambiguous_tables_are_rejected(self):
        from selenium.webdriver.support.ui import WebDriverWait
        pip = self.pip()
        pip.wait = WebDriverWait(Mock(), 0)
        pip.visible = Mock(return_value=[Mock(), Mock()])
        with self.assertRaisesRegex(RuntimeError, 'více tabulek'):
            pip.result_table()

    def test_missing_table_is_not_an_empty_search(self):
        pip = self.search_pip([])
        pip.result_table.side_effect = TimeoutException('missing table')
        with self.assertRaises(TimeoutException):
            pip.search_once('WHS_SO_00000000001')

    def test_logout_not_classified_as_not_found(self):
        with self.assertRaisesRegex(RuntimeError, 'Prihlaseni vyprselo'):
            self.search_pip([], logged_out=True).search_once('WHS_SO_00000000001')

    def test_multiple_results_not_classified_as_not_found(self):
        with self.assertRaisesRegex(RuntimeError, 'vice vysledku'):
            self.search_pip([Mock(), Mock()]).search_once('WHS_SO_00000000001')

    def test_missing_result_never_reaches_mutation(self):
        pip = self.pip()
        pip.open_order = Mock(side_effect=tool.OrderNotFound())
        pip.completed = Mock()
        with patch.object(tool, 'notice'):
            self.assertEqual(pip.process('WHS_SO_00000000001', True), 'NEDOHLEDANO')
        pip.completed.assert_not_called()
        self.assertEqual(tool.teams_text([('WHS_SO_00000000001', 'NEDOHLEDANO')], True), '')

    def test_batch_continues_and_journals_missing_order(self):
        pip = Mock()
        pip.process_with_session.side_effect = ['NEDOHLEDANO', 'HOTOVO']
        journal = Mock()
        driver = Mock()
        answers = ['WHS_SO_00000000001', '--h', 'WHS_SO_00000000002', '', 'y', '', '..', '0']
        with patch.object(sys, 'argv', ['pip_tool.py', '--instance', 'test', '--execute']), \
             patch.object(tool, 'read_config', return_value={'instances': {'test': {'url': 'https://example.com/'}}}), \
             patch.object(tool, 'open_browser', return_value=driver), \
             patch.object(tool, 'Pip', return_value=pip), \
             patch.object(tool, 'Journal', return_value=journal), \
             patch.object(tool, 'close_browser') as close, \
             patch('builtins.input', side_effect=answers):
            tool.main()
        self.assertEqual(pip.process_with_session.call_args_list,
                         [call('WHS_SO_00000000001', True), call('WHS_SO_00000000002', True)])
        self.assertEqual(journal.write.call_args_list,
                         [call('WHS_SO_00000000001', 'NEDOHLEDANO'), call('WHS_SO_00000000002', 'HOTOVO')])
        pip.show.assert_not_called()
        close.assert_called_once_with(driver)


if __name__ == '__main__':
    unittest.main()
