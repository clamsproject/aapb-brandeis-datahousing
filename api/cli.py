import json
import textwrap
import traceback
from cmd import Cmd
from pathlib import Path
import argparse
import inspect

from rich import box, prompt
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown
from rich.syntax import Syntax

from mmif.utils.cli import describe
from mmif.utils.workflow_helper import describe_single_mmif, generate_param_hash

from api.shack import ClamShack

from api.utils import load_json
from api.cli_utils import console, messages, COMMANDS, timestamp, path_as_string
from api.cli_utils import info, warning, error, dribble, get_tree


DEBUG = False


def print_command(cmd: str):
    console.print(Text(cmd, "bold dark_blue"))


def print_help(command: str, description: str):
    lines = textwrap.wrap(
        description, width=80, initial_indent='     ', subsequent_indent='     ')
    text = Text.assemble('\n ', (command, "bold dark_blue"))
    console.print(text)
    for l in lines:
        console.print(l)


def print_exception(e: Exception):
    """Print the traceback to the console. Should be called only when dabbling
    with the Python capabilities of the shell, when a user fully deserves to be
    slammed by the full Python exception handdling."""
    for l in traceback.format_exception(e):
        print(l, end='')


class Shell(Cmd):

    """Shell for command-line access to the ClamShack."""

    intro = ('\nYou entered the CLAMS shell. Type "?" for a list of commands.\n')
    prompt = None

    # Hidden commands are not advertized to the user when they type 'help'
    hidden_commands = {'s', 't', 'u', 'v', 'w', 'x', 'y', 'z', 'nl', 'echo', 'test'}

    @classmethod
    def set_prompt(cls, shack: ClamShack):
        cls.prompt = f'🐚 ({shack.name}) '

    def __init__(self, clamshack: ClamShack):
        # TODO: this may be needed for some Pythn versions
        # TODO: sometimes this works and sometimes it does not, not sure why
        # completekey = '^I' if sys.platform == 'darwin' else 'tab'
        # super().__init__(completekey=completekey)
        super().__init__()
        self.shack = clamshack
        self.set_prompt(self.shack)
        # Each time we got a couple of directories from a search we save it so we can
        # use it in the goto command.
        self.saved_directories = {}
        # The session log stores commands used and indicates when errors occurred,
        # the errors list is for errors encountered during the current session.
        self.log = []
        self.errors = []

    def __str__(self):
        return f'<Shell on "{self.shack.name}">'

    def hidden_command(self, command: str):
        if command.startswith('t_'):
            return True
        return command in self.__class__.hidden_commands

    def default(self, line):
        """This applies if no command was recognized."""
        if line == 'c':
            pass
        elif line in ("q", "EOF"):
            self.do_quit(line)
            return True
        elif line == 'h' or line.startswith('h '):
            self.do_history(f'{line[1:].strip()}')
        elif line.startswith('!'):
            # Mimicking the linux way to execute a previous command.
            n = line[1:]
            if n.isdigit():
                command = self.shack.history.index[int(n)]
                #console.print(Panel(f'{line} --> {command}'))
                print(command)
                self.cmdqueue.append(command)
        elif line == 'shack' or line.startswith('shack.'):
            # NOTE: why does this work now that the global variable is history?
            try:
                console.print(eval(f'self.{line}'))
            except Exception as e:
                print_exception(e)
        elif line == 'shell' or line.startswith('shell.'):
            try:
                line = f'self{line[5:]}'
                console.print(eval(line))
            except Exception as e:
                print_exception(e)
        elif line.startswith('p '):
            # This is not advertized but it is here to sneak in the possibility
            # to evaluate Python expressions.
            command = ' '.join(line.split()[1:])
            if command:
                try:
                    console.print(eval(command))
                except Exception as e:
                    print_exception(e)
        else:
            warning(f'Unknown command: {line.strip().split()[0]}')

    def postcmd(self, stop, line):
        """Print an empty line after a command is executed and put the command
        on the history list."""
        print()
        try:
            if not self.hidden_command(line.split()[0]):
                if not line.startswith('!'):
                    self.shack.history.add(line)
                    self.log.append(f'COMMAND: {line}')
        except IndexError:
            pass
        return stop

    def onecmd(self, line):
        """Wrapping all single commands in some error handling that deals with any
        unexpected errors. Known errors and warnings should be dealt with directly
        in the do_x() methods themselves."""
        try:
            return super().onecmd(line)
        except Exception as e:
            warning(
                'An unexpected error occured, type "show error" to see the last'
                ' error that occurred')
            current_error = {'command': line, 'stacktrace': []}
            self.log.append(f'ERROR: {line}')
            for l in traceback.format_exception(e):
                current_error['stacktrace'].append(l)
            self.errors.append(current_error)
            with open(self.shack.error_file, 'a') as fh:
                fh.write(f'\n>>> ERROR: {line}\n\n')
                for l in traceback.format_exception(e):
                    fh.write(l)

    def emptyline(self):
        """Override repeating the last command."""
        pass

    def get_commands(self) -> list:
        funs = inspect.getmembers(self.__class__, predicate=inspect.isfunction)
        names = [name[3:] for name, method in funs if name .startswith('do_')]
        names = [n for n in names if not self.hidden_command(n)]
        return names

    ## Core actions

    def do_quit(self, arg):
        """Exit the CLAM Shack"""
        print(messages['bye'])
        return True

    def do_show(self, arg):
        if arg == 'error':
            if self.errors:
                console.print(f'\n ERROR ON COMMAND: {self.errors[-1]["command"]}\n')
                for line in self.errors[-1]['stacktrace']:
                    console.print(f' {line}', end='')
        elif arg == 'errors':
            for error in self.errors:
                console.print(f'\n ERROR ON COMMAND: {error["command"]}\n')
                for line in error['stacktrace']:
                    console.print(f' {line}', end='')
        else:
            table = Table(show_header=False)
            for name, value in self.shack.get_settings():
                #console.print(f' {name:10}  =  {value}')
                if name == 'path':
                    table.add_row(name, path_as_string(Path(value)))
                else:
                    table.add_row(name, str(value))
            console.print(Panel("Shack settings and information"))
            console.print(table)

    def do_history(self, arg):
        if arg == 'reset':
            self.shack.history.reset()
            console.print('Command history was reset')
        else:
            console.print(Panel(
                'Command history for this shack, use !INT to rerun a command'))
            for n, command in self.shack.get_history():
                 print(f' {n:2d}  {command}')

    def do_search(self, arg):
        if not arg:
            warning('No search parameters given')
            return
        search_type, *args = arg.split()
        if search_type == 'assets':
            results = self.shack.search(term=args[0], mode='assets')
            console.print(Panel(f'Assets matching "{args[0]}"'))
            for r in results:
                print(f' {r.name}')
        elif search_type == 'mmif':
            results = self.shack.search(term=args[0], mode='mmif')
            console.print(Panel(f'MMIF files matching "{args[0]}"'
                                 ' and the directories where they occur'))
            for name in results:
                print(' ' + name)
                for p in results[name]:
                    print('    ', path_as_string(p.parent))
        elif search_type == 'app':
            results = self.shack.search(term=args[0], mode='app')
            console.print(Panel(f'Directories created by app matching "{args[0]}"'))
            self.saved_directories = {}
            for n, result in enumerate(results):
                self.saved_directories[n] = result
                print(f' {n:2d}: {path_as_string(result)}')
        elif search_type == 'params':
            try:
                results = self.shack.search(term=args, mode='params')
                search_params = ' & '.join(args)
                console.print(Panel(f'Directories created with parameter {search_params}'))
                self.saved_directories = {}
                for n, result in enumerate(results):
                    self.saved_directories[n] = result
                    print(f' {n:2d}: {path_as_string(result)}')
            except Exception as e:
                warning(e)
        else:
            warning(f'Cannot search for "{arg}", use "assets", "mmif" or "app"')
            return

    def do_apps(self, arg):
        app_dict = dict(enumerate(self.shack.app_names))
        if not arg:
            console.print(Panel('Registered CLAMS Apps'))
            for key in sorted(app_dict):
                console.print(f' {key}: {app_dict[key]}')
        else:
            selection = arg
            if selection.isnumeric():
                selection = app_dict.get(int(selection))
            succeeded = self.shack.select_app(selection)
            if succeeded:
                dribble(f'Selected {selection}')
            else:
                warning(f'Selection does not exist')

    def do_register(self, arg):
        self.shack.register(arg)

    def do_jobs(self, arg):
        if arg:
            try:
                job = self.shack.jobs[arg]
                console.print(Panel(job.name))
                info_table = Table('property', 'value', box=box.ROUNDED)
                for prop, val in job.info():
                    info_table.add_row(prop, val)
                console.print(info_table)
                info_guids_table = Table('guid', 'time', 'result', box=box.ROUNDED)
                for guid, t, result in job.info_guids():
                    info_guids_table.add_row(guid, t, result)
                console.print(info_guids_table)
            except KeyError:
                warning('No such job.')
                return
        else:
            console.print(Panel(
                'Jobs associated with this Shack'
                ' (listed in order of when they were started)'))
            table = Table('name', 'app', 'guids', 'status', 'time (s)', box=box.ROUNDED)
            for job in sorted(self.shack.jobs.values(), key=lambda x: x.started, reverse=False):
                status = 'done' if job.finished else 'running'
                elapsed = str(job.time_elapsed())
                table.add_row(job.name, job.app, str(len(job.guids)), status, elapsed)
            console.print(table)

    def do_params(self, arg):
        args = arg.split()
        if len(args) >= 1:
            if args[0] == 'reset':
                self.shack.params_file = None
                self.shack.params = {}
            # loading a file with "params @FILENAME"
            elif args[0].startswith('@'):
                fname = args[0][1:].strip()
                try:
                    params = load_json(fname)
                    self.shack.params = params
                    self.shack.params_file = fname
                except FileNotFoundError:
                    print(f'There is no file "{fname}"')
                except json.decoder.JSONDecodeError:
                    print(f'No valid JSON in {fname}')
            # setting a parameter with "params PARAM=VALUE"
            elif '=' in args[0]:
                param, value = args[0].split('=', 1)
                self.shack.add_parameter(param, value)
        console.print(self.shack.params)

    def do_run(self, arg):
        if not arg:
            warning('You must provide a name for the job.')
            return
        if self.shack.app is None:
            warning('You must select a CLAMS app.')
            return
        if arg in self.shack.jobs:
            warning('A job with that name already exists.')
            return
        if self.shack.cwd() != Path('.'):
            files = [Path(f.name) for f in self.shack.files() if f.suffix == '.mmif']
            if not files:
                print('Nothing to do, there are no MMIF files in the current path')
                return
        process_id = self.shack.run_job(arg)
        console.print(Panel('Started job'))
        dribble(f'  name   = {arg}')
        dribble(f'  path   = {path_as_string(self.shack.cwd())}')
        dribble(f'  app    = {self.shack.app}')
        dribble(f'  params = {self.shack.params}')
        dribble(f'  pid    = {process_id}')

    def do_index(self, arg):
        self.shack.reindex()
        print('Recreated the MMIF Index')

    def do_source(self, arg):
        """Loads a file of commands and then run them. The file of commands has to
        be in the same format as the file that is created by the "history save"
        command."""
        # TODO: check the source file so that it only has one run command
        if arg:
            script_path = Path(arg)
            if script_path.is_file():
                commands = []
                for line in script_path.read_text().split('\n'):
                    if line.strip() and not line.strip().startswith('#'):
                        commands.append(line.strip())
                for c in commands:
                    self.cmdqueue.append(f'echo {c}')
                    self.cmdqueue.append(c)
            else:
                warning(f'Script file "{arg}" does not exist')
        else:
            warning("You need to specify a script to source.")

    def do_pwd(self, arg):
        path = self.shack.cwd()
        if str(path) in ('', '.'):
            print('.')
        else:
            print('', path_as_string(path))

    def do_dirs(self, arg):
        if arg == '-s':
            if self.saved_directories:
                console.print(Panel(f'Last directories saved (using full storage path)'))
                for n, path in self.saved_directories.items():
                    print(f' {n:2d}: {path_as_string(path)}')
            else:
                print('\n No directories were saved.')
        elif arg == '-d':
            spath = self.shack.storage_path
            dirs = spath.ddir()
            p = path_as_string(self.shack.cwd())
            console.print(Panel(f'Expanded sub directories at "{p}"'))
            self.saved_directories = {}
            for n, (d1, d2) in enumerate(dirs):
                self.saved_directories[n] = d1
                print(f' {n:2d}: {path_as_string(d2)}')
        else:
            p = path_as_string(self.shack.cwd())
            console.print(Panel(f'Sub directories at "{p}"'))
            for n, d in enumerate(self.shack.subdirs()):
                print(f' {n:2d}: {str(d)}')

    def do_files(self, arg):
        console.print(Panel(f'MMIF files at "{path_as_string(self.shack.cwd())}"'))
        for n, f in enumerate(self.shack.files()):
            print(f' {n}: {str(f)}')

    def do_cd(self, arg):
        # first translate an index from the dir command into a sub directory
        subdirs = { n: str(p) for n, p in enumerate(self.shack.subdirs()) }
        if arg.isnumeric() and int(arg) in subdirs:
            arg = subdirs[int(arg)]
        try:
            new_path = self.shack.cd(arg)
            print(path_as_string(Path(new_path)))
        except ShackError as e:
            warning(e)

    def do_home(self, arg):
        self.do_cd('~')

    def do_up(self, arg):
        try:
            repetitions = int(arg) if arg else 1
            for i in range(repetitions):
                self.shack.cd('..')
            print(path_as_string(self.shack.path))
        except ValueError:
            warning('The argument can only be an integer')

    def do_tree(self, arg):
        args = arg.split()
        full = True if '-f' in args else False
        parameters = True if '-p' in args else False
        if '-v' in args:
            full = True
            parameters = True
        prefix = self.shack.mmif_dir
        t = get_tree(self.shack.mmif_dir / self.shack.path, prefix=prefix, full=full)
        console.print(Panel('MMIF File tree'))
        self.do_nl('')
        console.print(t)
        if parameters:
            parameter_file = self.shack.parameter_file()
            if parameter_file is not None:
                print()
                #console.print(Panel(path_as_string(parameter_file)))
                console.print(Panel('Parameters'))
                console.print(parameter_file.read_text())

    def do_goto(self, arg):
        try:
            self.shack.cd('~')
            directory = self.saved_directories.get(int(arg))
            if directory is None:
                warning('There is no saved directory at that index')
                return
            self.shack.cd(str(directory))
            #print(path_as_string(directory))
            self.do_tree('-p')
        except ValueError:
            warning('goto command requires an integer')

    def do_prune(self, arg):
        try:
            text = Text(
                f'\n Deleting {path_as_string(self.shack.cwd())}\n'
                + '\n This cannot be undone\n')
            text.stylize("bold red")
            console.print(text)
            answer = input(' Continue? (y/n) ')
            if answer == 'y':
                self.shack.prune()
            console.print(Panel(f' Deleted {path_as_string(self.shack.cwd())}'))
        except ShackError as e:
            warning(e)

    def do_view(self, arg):
        saved_path = self.shack.path
        if saved_path == '.':
            saved_path = '~'
        self.do_goto(arg)
        self.shack.cd('~')
        #self.do_view(arg)
        self.shack.cd(str(saved_path))
        
    def do_describe(self, arg):
        if not arg.isdigit():
            warning('The argument must be an integer')
            return
        full_path = self.shack.mmif_dir / self.shack.path
        for n, f in enumerate(self.shack.files()):
            if n == int(arg):
                if not (full_path / f).suffix == '.mmif':
                    warning('The file at that index is not a MMIF file')
                    return
                console.print(Panel(f'describe {str(f)}'))
                desc = describe_single_mmif(full_path / f)
                console.print(desc)
                return
        warning('No MMIF file at that index')

    def do_help(self, arg):
        if not arg:
            names = self.get_commands()
            console.print(Panel('Available commands'))
            for cmd in names:
                print_command(' ' + cmd)
            console.print('\n Type "help <command>" for help on a command')
        elif arg in COMMANDS:
            print_help(*COMMANDS.get(arg))
        else:
            print(f'No help available for {arg}')

    def do_help_all(self, arg):
        names = self.get_commands()
        console.print(Panel('Available commands'))
        for cmd in names:
            print_help(*COMMANDS.get(cmd,('','')))

    def do_echo(self, arg):
        """Just a utility method to use in scripts, may be deprecated."""
        print(f'>>> {arg}')

    def do_nl(self, arg):
        # Utility command for when adding multiple commands to the queue, may be
        # deprecated.
        print()

    ## Undocumented actions for debugging and development

    def do_s(self, arg):
        self.cmdqueue.append('source example-script.txt')

    def do_t(self, arg):
        self.cmdqueue.append('search app spac')
        self.cmdqueue.append('goto 0')

    def do_test(self, arg):
        if arg == 'search':
            self.cmdqueue.append('search assets f55')
            self.cmdqueue.append('search mmif f55')
            self.cmdqueue.append('search app captioner')
            self.cmdqueue.append('search params pretty=True threshold=3')
            self.cmdqueue.append('view 0')
        elif arg == 'spacy':
            self.cmdqueue.append('register http://127.0.0.1:5001')
            self.cmdqueue.append('apps 0')
            self.cmdqueue.append('cd ~')
            self.cmdqueue.append('cd swt-detection/v8.6/d41d8cd98f00b204e9800998ecf8427e/smolvlm2-captioner/v1.0/d41d8cd98f00b204e9800998ecf8427e')
            self.cmdqueue.append('params @example-params.json')
            self.cmdqueue.append('run t1')
            self.cmdqueue.append('home')
        elif arg == 'misc':
            self.cmdqueue.append('show')
            self.cmdqueue.append('tree')
            self.cmdqueue.append('jobs')
        elif arg == 'dirs':
            self.cmdqueue.append('dirs')
            self.cmdqueue.append('dirs -d')
            self.cmdqueue.append('cd swt-detection/v8.6/d41d8cd98f00b204e9800998ecf8427e')
            self.cmdqueue.append('files')

    def do_x(self, arg):
        self.cmdqueue.append('register http://127.0.0.1:5001')
        self.cmdqueue.append('apps 0')
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('cd 0')
        self.cmdqueue.append('params pretty True')
        self.cmdqueue.append('params params.json')
        self.cmdqueue.append('jobs')
        self.cmdqueue.append('show')

    def do_y(self, arg):
        self.cmdqueue.append('register 127.0.0.1:5001')
        self.cmdqueue.append('apps')

    def do_z(self, arg):
        self.cmdqueue.append('source s.txt')

    def do_w(self, arg):
        self.cmdqueue.append('source s2.txt')


def parse_arguments():
    parser = argparse.ArgumentParser()
    s_help = "Open the ClamShack in DIR or create it if the directory does not exist"
    a_help = "Add the assets in FILE to the ClamShack in DIR"
    parser.add_argument('--shack', metavar='DIR', required=True, help=s_help)
    parser.add_argument('--assets', metavar='FILE', default=None, help=a_help)
    parser.add_argument('--debug', action='store_true')
    return parser.parse_args()


if __name__ == '__main__':

    args = parse_arguments()
    if args.debug:
        DEBUG = True
    Shell(ClamShack(args.shack, args.assets)).cmdloop()
