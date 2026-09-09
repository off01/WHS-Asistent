"""History is limited to WHS input and lives only for this processing session."""
import sys


class OrderInput:
    def __init__(self):
        self.session = None

    def read(self):
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return input()
        if self.session is None:
            from prompt_toolkit import PromptSession
            self.session = PromptSession()
        return self.session.prompt('')
