import datetime
import fnmatch
import io
import itertools
import os
import re
import sublime
import sublime_plugin
import sublime
import sys
import threading
import timeit
import subprocess


cmd_name = "go-find-references"
go_reference_result_tag = "go_reference_result"
view_name = "Golang Find Reference Result"


class GolangFindReferenceCommand(sublime_plugin.WindowCommand):
    """
    find reference command
    """

    def run(self):
        view = self.window.active_view()
        filename = view.file_name()
        select = view.sel()[0]
        select_begin = select.begin()
        select_before = sublime.Region(0, select_begin)
        string_before = view.substr(select_before)
        string_before.encode("utf-8")
        buffer_before = bytearray(string_before, encoding="utf-8")
        offset = len(buffer_before)
        print("[Debug] offset: %d file: %s" % (offset, filename))
        thread = Thread(filename, offset, view)
        thread.start()

    def is_enabled(self):
        view = self.window.active_view()
        filename = view.file_name()
        ss = os.path.splitext(filename)
        if len(ss) != 2:
            return False
        return ss[1] == ".go"


class GolangFindReferenceRenderCommand(sublime_plugin.TextCommand):
    """docstring for GolangFindReferenceRenderCommander"""

    def run(self, edit, **args):
        self.result = args.get("result")
        self.edit = edit
        self.window = sublime.active_window()
        self.rview = self.get_view()

        lines = self.result.strip().splitlines()
        print("[Debug]: render ", lines)
        i = 0
        for line in lines:
            print("[Debug]: line ", line)
            self.rview.insert(self.edit, self.rview.size(), line + "\n")
            i = i + 1
            if i % 2 == 0:
                self.rview.insert(self.edit, self.rview.size(), "\n")
        self.window.focus_view(self.rview)

    def get_view(self):
        print("[Debug]: view count: ", len(self.window.views()))
        rview = None
        for view in self.window.views():
            if view.settings().get(go_reference_result_tag, False):
                print("[Debug]: erase view.")
                view.erase(self.edit, sublime.Region(0, view.size()))
                rview = view
                break

        if rview is None:
            rview = self.window.new_file()
        rview.set_name(view_name)
        rview.set_scratch(True)
        rview.settings().set(go_reference_result_tag, True)

        return rview


class GolangFindReferenceEvent(sublime_plugin.EventListener):
    """
    double click to open result file
    """

    def on_selection_modified(self, view):
        self.settings = view.settings()

        if not self.settings.get(go_reference_result_tag):
            return

        sel = view.sel()[0]
        if sel.end() - sel.begin() > 0:
            view.run_command("golang_find_reference_results")


class GolangFindReferenceResultsCommand(sublime_plugin.TextCommand):
    """
    open file
    """

    def run(self, edit, **args):
        self.settings = self.view.settings()
        if not self.settings.get(go_reference_result_tag):
            return

        line = self.view.substr(self.view.line(self.view.sel()[0]))
        location = line.rstrip().rsplit(":", 2)
        if len(location) != 3:
            return

        win = sublime.active_window()
        fview = win.open_file(line, sublime.ENCODED_POSITION)
        win.focus_view(fview)


class Thread(threading.Thread):

    def __init__(self, f, offset, view):
        self.offset = offset
        self.file = f
        self.view = view
        threading.Thread.__init__(self)

    def run(self):
        if sys.version_info < (3, 0, 0):
            sublime.set_timeout(self.thread, 1)
        else:
            self.thread()

    def get_cmd_path(self):
        # load gopath from settings
        settings = sublime.load_settings(
            "GoFindReference.sublime-settings")
        gopath = settings.get("gopath", os.getenv('GOPATH'))
        if not gopath:
            print("[Debug]:gopath not found.")
            return ""
        gopaths = gopath.split(os.pathsep)
        for p in gopaths:
            fullpath = p + "/bin/" + cmd_name
            if os.name == "nt":
                fullpath = p + "\\bin\\" + cmd_name + ".exe"
            if os.path.exists(fullpath):
                return fullpath
        return ""

    def thread(self):
        all_lines = ""
        folders = sublime.active_window().folders()
        cmd_path = self.get_cmd_path()
        if len(cmd_path) <= 0:
            print(
                "[Debug]: go-find-references command not found in your path.")
            return

        for d in folders:
            args = [cmd_path, "-file", self.file, "-offset",
                    str(self.offset), "-root", d]
            print("[Debug]: ", args)
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            p = subprocess.Popen(args, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 startupinfo=startupinfo)
            output, stderr = p.communicate()
            if stderr:
                print("[Debug]ERROR: find reference error: %s" %
                      str(stderr))
                continue

            result = output.decode("utf-8")
            # lines = result.strip().splitlines()
            all_lines += result
            print("[Debug] result: ", all_lines, len(all_lines))

        if len(all_lines) <= 0:
            return
        self.view.run_command(
            'golang_find_reference_render', {"result": all_lines})
