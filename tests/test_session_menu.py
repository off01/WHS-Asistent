import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch, call

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import pip_tool as tool

A = 'WHS_SO_08000006785'
B = 'WHS_SO_08000006786'


class SessionMenuTests(unittest.TestCase):
    def test_back_and_ctrl_c_switch_modes_in_same_browser(self):
        for back in ('..', KeyboardInterrupt()):
            with self.subTest(back=back):
                pip = Mock()
                pip.process_with_session.return_value = 'KONTROLA_OK'
                reader = Mock()
                reader.read.side_effect = [A, back, '', B, '..', '', '..']
                with patch.object(sys, 'argv', ['pip_tool.py', '--instance', 'int', '--execute']), \
                     patch.object(tool, 'read_config', return_value={'instances': {'int': {'url': 'https://example.com/'}}}), \
                     patch.object(tool, 'open_browser') as browser, \
                     patch.object(tool, 'Pip', return_value=pip), \
                     patch.object(tool, 'Journal'), \
                     patch.object(tool, 'OrderInput', return_value=reader) as history, \
                     patch.object(tool, 'close_browser') as close, \
                     patch('builtins.input') as menu_input, redirect_stdout(io.StringIO()):
                    answers = iter(['2', '1', 'y', '0'])
                    def answer(prompt):
                        close.assert_not_called()
                        return next(answers)
                    menu_input.side_effect = answer
                    tool.main()
                self.assertEqual(pip.process_with_session.call_args_list, [call(A, False), call(B, True)])
                browser.assert_called_once()
                close.assert_called_once_with(browser.return_value)
                history.assert_called_once()
                self.assertEqual(sum('Potvrdit' in c.args[0] for c in menu_input.call_args_list), 1)

    def test_menu_requires_explicit_exit_and_accepts_help(self):
        with patch('builtins.input', side_effect=[KeyboardInterrupt(), '..', '--h', '0']), redirect_stdout(io.StringIO()):
            self.assertIsNone(tool.session_menu())
