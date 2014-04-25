# Copyright 2014 Florian Bruhin (The Compiler) <mail@qutebrowser.org>
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""Module containing command managers (SearchManager and CommandManager)."""

from PyQt5.QtCore import pyqtSlot, pyqtSignal, QObject
from PyQt5.QtWebKitWidgets import QWebPage

import qutebrowser.config.config as config
import qutebrowser.commands.utils as cmdutils
import qutebrowser.utils.message as message
from qutebrowser.commands._exceptions import (
    ArgumentCountError, NoSuchCommandError, InvalidModeError)


def split_cmdline(text):
    """Convenience function to split a commandline into it's logical parts.

    Args:
        text: The string to split.

    Return:
        A list of strings.
    """
    manager = CommandManager()
    try:
        parts = manager.parse(text)
    except NoSuchCommandError:
        parts = text.split(' ')
    if text.endswith(' '):
        parts.append('')
    return parts


class SearchManager(QObject):

    """Manage qutebrowser searches.

    Attributes:
        _text: The text from the last search.
        _flags: The flags from the last search.

    Signals:
        do_search: Emitted when a search should be started.
                   arg 1: Search string.
                   arg 2: Flags to use.
    """

    do_search = pyqtSignal(str, 'QWebPage::FindFlags')

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = None
        self._flags = 0

    def _search(self, text, rev=False):
        """Search for a text on the current page.

        Args:
            text: The text to search for.
            rev: Search direction, True if reverse, else False.

        Emit:
            do_search: If a search should be started.
        """
        if self._text is not None and self._text != text:
            self.do_search.emit('', 0)
        self._text = text
        self._flags = 0
        if config.get('general', 'ignorecase'):
            self._flags |= QWebPage.FindCaseSensitively
        if config.get('general', 'wrapsearch'):
            self._flags |= QWebPage.FindWrapsAroundDocument
        if rev:
            self._flags |= QWebPage.FindBackward
        self.do_search.emit(self._text, self._flags)

    @pyqtSlot(str)
    def search(self, text):
        """Search for a text on a website.

        Args:
            text: The text to search for.
        """
        self._search(text)

    @pyqtSlot(str)
    def search_rev(self, text):
        """Search for a text on a website in reverse direction.

        Args:
            text: The text to search for.
        """
        self._search(text, rev=True)

    @cmdutils.register(instance='searchmanager', hide=True)
    def nextsearch(self, count=1):
        """Continue the search to the ([count]th) next term.

        Args:
            count: How many elements to ignore.

        Emit:
            do_search: If a search should be started.
        """
        if self._text is not None:
            for _ in range(count):
                self.do_search.emit(self._text, self._flags)


class CommandManager:

    """Manage qutebrowser commandline commands.

    Attributes:
        _cmd: The command which was parsed.
        _args: The arguments which were parsed.
    """

    def __init__(self):
        self._cmd = None
        self._args = []

    def parse(self, text, aliases=True):
        """Split the commandline text into command and arguments.

        Args:
            text: Text to parse.
            aliases: Whether to handle aliases.

        Raise:
            NoSuchCommandError if a command wasn't found.

        Return:
            A split string commandline, e.g ['open', 'www.google.com']
        """
        parts = text.strip().split(maxsplit=1)
        if not parts:
            raise NoSuchCommandError("No command given")
        cmdstr = parts[0]
        if aliases:
            try:
                alias = config.get('aliases', cmdstr)
            except (config.NoOptionError, config.NoSectionError):
                pass
            else:
                return self.parse(alias, aliases=False)
        try:
            cmd = cmdutils.cmd_dict[cmdstr]
        except KeyError:
            raise NoSuchCommandError(cmdstr)

        if len(parts) == 1:
            args = []
        else:
            args = parts[1].split(maxsplit=cmd.maxsplit)
        self._cmd = cmd
        self._args = args
        return [cmdstr] + args

    def _check(self):
        """Check if the argument count for the command is correct."""
        self._cmd.check(self._args)

    def _run(self, count=None):
        """Run a command with an optional count.

        Args:
            count: Count to pass to the command.
        """
        if count is not None:
            self._cmd.run(self._args, count=count)
        else:
            self._cmd.run(self._args)

    @pyqtSlot(str, int, bool)
    def run(self, text, count=None, ignore_exc=True):
        """Parse a command from a line of text.

        If ignore_exc is True, ignore exceptions and return True/False.

        Args:
            text: The text to parse.
            count: The count to pass to the command.
            ignore_exc: Ignore exceptions and return False instead.

        Raise:
            NoSuchCommandError: if a command wasn't found.
            ArgumentCountError: if a command was called with the wrong count of
                                arguments.
            InvalidModeError: if a command can't be called in this mode.

        Return:
            True if command was called (handler returnstatus is ignored!).
            False if command wasn't called (there was an ignored exception).
        """
        if ';;' in text:
            retvals = []
            for sub in text.split(';;'):
                retvals.append(self.run(sub, count, ignore_exc))
            return all(retvals)
        try:
            self.parse(text)
            self._check()
        except NoSuchCommandError as e:
            if ignore_exc:
                message.error("{}: no such command".format(e))
                return False
            else:
                raise
        except ArgumentCountError as e:
            if ignore_exc:
                message.error("{}: invalid argument count - {}".format(
                    self._cmd.name, e))
                return False
            else:
                raise
        except InvalidModeError as e:
            if ignore_exc:
                message.error("{}: {}".format(self._cmd.name, e))
                return False
            else:
                raise
        self._run(count=count)
        return True