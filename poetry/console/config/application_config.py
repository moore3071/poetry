import logging

from cleo.config import ApplicationConfig as BaseApplicationConfig
from clikit.api.event import PRE_HANDLE
from clikit.api.event import PreHandleEvent
from clikit.api.formatter import Style
from clikit.api.io import Input
from clikit.api.io import InputStream
from clikit.api.io import Output
from clikit.api.io import OutputStream
from clikit.api.io.flags import DEBUG
from clikit.api.io.flags import VERBOSE
from clikit.api.io.flags import VERY_VERBOSE
from clikit.formatter import AnsiFormatter
from clikit.formatter import PlainFormatter
from clikit.io.input_stream import StandardInputStream
from clikit.io.output_stream import ErrorOutputStream
from clikit.io.output_stream import StandardOutputStream

from poetry.console.commands.command import Command
from poetry.console.commands.env_command import EnvCommand
from poetry.console.logging import IOFormatter
from poetry.console.logging import IOHandler


class ApplicationConfig(BaseApplicationConfig):
    def configure(self):
        super(ApplicationConfig, self).configure()

        self.add_style(Style("c1").fg("cyan"))
        self.add_style(Style("info").fg("blue"))
        self.add_style(Style("comment").fg("green"))
        self.add_style(Style("error").fg("red").bold())
        self.add_style(Style("warning").fg("yellow"))
        self.add_style(Style("debug").fg("black").bold())

        self.add_event_listener(PRE_HANDLE, self.register_command_loggers)
        self.add_event_listener(PRE_HANDLE, self.set_env)

    def register_command_loggers(
        self, event, event_name, _  # type: PreHandleEvent  # type: str
    ):  # type: (...) -> None
        command = event.command.config.handler
        if not isinstance(command, Command):
            return

        io = event.io

        loggers = ["poetry.packages.package"]

        loggers += command.loggers

        handler = IOHandler(io)
        handler.setFormatter(IOFormatter())

        for logger in loggers:
            logger = logging.getLogger(logger)

            logger.handlers = [handler]
            logger.propagate = False

            level = logging.WARNING
            if io.is_debug():
                level = logging.DEBUG
            elif io.is_very_verbose() or io.is_verbose():
                level = logging.INFO

            logger.setLevel(level)

    def set_env(self, event, event_name, _):  # type: (PreHandleEvent, str, _) -> None
        from poetry.semver import parse_constraint
        from poetry.utils.env import EnvManager

        command = event.command.config.handler  # type: EnvCommand
        if not isinstance(command, EnvCommand):
            return

        io = event.io
        poetry = command.poetry

        env_manager = EnvManager(poetry)
        env = env_manager.create_venv(io)

        if env.is_venv() and io.is_verbose():
            io.write_line("Using virtualenv: <comment>{}</>".format(env.path))

        command.set_env(env)

    def resolve_help_command(
        self, event, event_name, dispatcher
    ):  # type: (PreResolveEvent, str, EventDispatcher) -> None
        args = event.raw_args
        application = event.application

        if args.has_option_token("-h") or args.has_option_token("--help"):
            from clikit.api.resolver import ResolvedCommand

            resolved_command = self.command_resolver.resolve(args, application)
            # If the current command is the run one, skip option
            # check and interpret them as part of the executed command
            if resolved_command.command.name == "run":
                event.set_resolved_command(resolved_command)

                return event.stop_propagation()

            command = application.get_command("help")

            # Enable lenient parsing
            parsed_args = command.parse(args, True)

            event.set_resolved_command(ResolvedCommand(command, parsed_args))
            event.stop_propagation()

    def create_io(
        self,
        application,
        args,
        input_stream=None,
        output_stream=None,
        error_stream=None,
    ):  # type: (Application, RawArgs, InputStream, OutputStream, OutputStream) -> IO
        if input_stream is None:
            input_stream = StandardInputStream()

        if output_stream is None:
            output_stream = StandardOutputStream()

        if error_stream is None:
            error_stream = ErrorOutputStream()

        style_set = application.config.style_set

        if output_stream.supports_ansi():
            output_formatter = AnsiFormatter(style_set)
        else:
            output_formatter = PlainFormatter(style_set)

        if error_stream.supports_ansi():
            error_formatter = AnsiFormatter(style_set)
        else:
            error_formatter = PlainFormatter(style_set)

        io = self.io_class(
            Input(input_stream),
            Output(output_stream, output_formatter),
            Output(error_stream, error_formatter),
        )

        resolved_command = application.resolve_command(args)
        # If the current command is the run one, skip option
        # check and interpret them as part of the executed command
        if resolved_command.command.name == "run":
            return io

        if args.has_option_token("--no-ansi"):
            formatter = PlainFormatter(style_set)
            io.output.set_formatter(formatter)
            io.error_output.set_formatter(formatter)
        elif args.has_option_token("--ansi"):
            formatter = AnsiFormatter(style_set, True)
            io.output.set_formatter(formatter)
            io.error_output.set_formatter(formatter)

        if args.has_option_token("-vvv") or self.is_debug():
            io.set_verbosity(DEBUG)
        elif args.has_option_token("-vv"):
            io.set_verbosity(VERY_VERBOSE)
        elif args.has_option_token("-v"):
            io.set_verbosity(VERBOSE)

        if args.has_option_token("--quiet") or args.has_option_token("-q"):
            io.set_quiet(True)

        if args.has_option_token("--no-interaction") or args.has_option_token("-n"):
            io.set_interactive(False)

        return io
