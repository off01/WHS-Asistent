import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import pip_tool as tool


class StatusTests(unittest.TestCase):
    def test_both_types_share_expected_states(self):
        for prefix in tool.ORDER_PREFIXES:
            self.assertEqual(tool.status_value(prefix + 'Čeká na přiřazení'), tool.status_value(tool.SOURCE))
            self.assertEqual(tool.status_value(prefix + 'Čeká se na odpověď WHS partnera'), tool.status_value(tool.TARGET))

    def cm_order(self, value=tool.SUCCESS, button_visible=False):
        pip = object.__new__(tool.Pip)
        pip.read = lambda action: action()
        pip.identity = Mock()
        pip.status = Mock(return_value='WHS HFC Instalace - Registrace CM provedena')
        pip.visible = Mock(return_value=[Mock()] if button_visible else [])
        pip.by_id = Mock()
        pip.by_id.return_value.get_property.return_value = value
        return pip

    def test_cm_registration_with_success_and_no_button_is_completed(self):
        self.assertTrue(self.cm_order().completed('WHS_SO_00000000001'))

    def test_cm_registration_needs_success_selection(self):
        self.assertFalse(self.cm_order(value='Prosím vyberte hodnotu').completed('WHS_SO_00000000001'))

    def test_cm_registration_with_button_is_not_completed(self):
        self.assertFalse(self.cm_order(button_visible=True).completed('WHS_SO_00000000001'))

    def test_completed_cm_order_is_skipped_and_included_in_report(self):
        pip = self.cm_order()
        pip.open_order = Mock()
        pip.text = Mock()
        self.assertEqual(pip.process('WHS_SO_00000000001', True), 'JIZ_HOTOVO')
        pip.text.assert_not_called()
        self.assertEqual(tool.teams_text([('WHS_SO_00000000001', 'JIZ_HOTOVO')], True), 'WHS_SO_00000000001 dokončeno')

    def test_cm_registration_never_triggers_installation(self):
        pip = object.__new__(tool.Pip)
        pip.open_order = Mock()
        pip.completed = Mock(return_value=False)
        pip.journal = Mock()
        pip.journal.uncertain.return_value = False
        pip.status = Mock(return_value='WHS HFC Instalace - Registrace CM provedena')
        pip.text = Mock()
        with self.assertRaisesRegex(RuntimeError, 'Registrace CM provedena'):
            pip.process('WHS_SO_00000000001', True)
        pip.text.assert_not_called()

    def test_unknown_type_is_rejected(self):
        with self.assertRaises(ValueError):
            tool.status_value('Jiny typ - Čeká na přiřazení')
