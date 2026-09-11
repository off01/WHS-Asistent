import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, call

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import pip_tool as tool


class PauseTests(unittest.TestCase):
    def test_pause_keeps_browser_until_explicit_exit(self):
        pip = Mock()
        with patch('builtins.input', side_effect=['n', 'n']), patch.object(tool, 'close_browser') as close:
            self.assertEqual(tool.pause_batch(pip, ['next']), 'new_batch')
        pip.show.assert_called_once()
        close.assert_not_called()
        pip.d.quit.assert_not_called()

    def test_second_ctrl_c_does_not_close_browser(self):
        pip = Mock()
        with patch('builtins.input', side_effect=[KeyboardInterrupt(), 'n']):
            self.assertEqual(tool.pause_batch(pip, []), 'new_batch')
        pip.d.quit.assert_not_called()

    def test_resume_verifies_overview(self):
        pip = Mock()
        with patch('builtins.input', side_effect=['y', '']):
            self.assertEqual(tool.pause_batch(pip, ['next']), 'continue')
        pip.ready_overview.assert_called_once()

    def test_interrupted_order_is_skipped_without_closing_session(self):
        pip = Mock()
        pip.process_with_session.side_effect = [KeyboardInterrupt(), 'HOTOVO']
        journal = Mock()
        def pause(*args):
            close.assert_not_called()
            return 'continue'
        with patch.object(sys, 'argv', ['pip_tool.py', '--instance', 'test', '--execute']), \
             patch.object(tool, 'read_config', return_value={'instances': {'test': {'url': 'https://example.com/'}}}), \
             patch.object(tool, 'open_browser'), patch.object(tool, 'Pip', return_value=pip), \
             patch.object(tool, 'Journal', return_value=journal), \
             patch.object(tool, 'close_browser') as close, \
             patch.object(tool, 'pause_batch', side_effect=pause), \
             patch('builtins.input', side_effect=['WHS_SO_00000000001', 'WHS_SO_00000000002', '', 'y', '', '..', '0']):
            tool.main()
        self.assertEqual(pip.process_with_session.call_args_list, [call('WHS_SO_00000000001', True), call('WHS_SO_00000000002', True)])
        journal.write.assert_any_call('WHS_SO_00000000001', 'PRERUSENO')
        close.assert_called_once()
