import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import browser
import pip_tool
from selenium import webdriver


class BrowserTests(unittest.TestCase):
    def test_each_run_opens_a_fresh_browser_without_persistent_options(self):
        options = webdriver.EdgeOptions()
        options.add_argument('--start-maximized')
        first, second = Mock(), Mock()
        with patch.object(webdriver, 'Edge', side_effect=[first, second]) as edge:
            self.assertIs(browser.open_browser('https://example.com/', options, Mock()), first)
            self.assertIs(browser.open_browser('https://example.com/', options, Mock()), second)
        self.assertEqual(edge.call_count, 2)
        caps = options.to_capabilities()['ms:edgeOptions']
        self.assertNotIn('debuggerAddress', caps)
        self.assertNotIn('detach', caps)
        self.assertFalse(any('user-data-dir' in arg for arg in caps['args']))
        first.get.assert_called_once_with('https://example.com/')

    def test_failed_navigation_closes_new_browser(self):
        driver = Mock()
        driver.get.side_effect = RuntimeError('navigation failed')
        with patch.object(webdriver, 'Edge', return_value=driver):
            with self.assertRaisesRegex(RuntimeError, 'navigation failed'):
                browser.open_browser('https://example.com/', Mock(), Mock())
        driver.quit.assert_called_once()

    def test_shutdown_does_not_ask_to_keep_session(self):
        driver = Mock()
        with patch('builtins.input') as prompt:
            pip_tool.close_browser(driver)
        prompt.assert_not_called()
        driver.quit.assert_called_once()
