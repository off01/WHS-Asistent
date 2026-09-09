import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from order_input import OrderInput


class OrderInputTests(unittest.TestCase):
    def test_same_prompt_session_is_reused_across_batches(self):
        session = Mock()
        session.prompt.side_effect = ['WHS_SO_08000006785 --r', '', '--h']
        factory = Mock(return_value=session)
        with patch('sys.stdin.isatty', return_value=True), patch('sys.stdout.isatty', return_value=True), \
             patch.dict(sys.modules, {'prompt_toolkit': SimpleNamespace(PromptSession=factory)}):
            reader = OrderInput()
            self.assertEqual(reader.read(), 'WHS_SO_08000006785 --r')
            self.assertEqual(reader.read(), '')
            self.assertEqual(reader.read(), '--h')
        factory.assert_called_once_with()

    def test_ctrl_c_propagates_to_existing_pause_handler(self):
        reader = OrderInput()
        reader.session = Mock()
        reader.session.prompt.side_effect = KeyboardInterrupt()
        with patch('sys.stdin.isatty', return_value=True), patch('sys.stdout.isatty', return_value=True):
            with self.assertRaises(KeyboardInterrupt):
                reader.read()

    def test_redirected_input_preserves_multiline_paste(self):
        with patch('sys.stdin.isatty', return_value=False), \
             patch('builtins.input', return_value='WHS_SO_08000006785\nWHS_SO_08000006786'):
            self.assertEqual(OrderInput().read(), 'WHS_SO_08000006785\nWHS_SO_08000006786')
