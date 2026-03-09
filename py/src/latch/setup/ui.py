from __future__ import annotations

from contextlib import contextmanager
from io import StringIO

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

ACCENT = "#C78A3B"
SURFACE = "#1A1D21"
TEXT = "#E9E6DF"
MUTED = "#A8A39A"
SUCCESS = "#6E9B6D"
WARN = "#B08A3C"
ERROR = "#B45A4D"


def header(step: int, total: int, title: str) -> None:
    label = Text(f" STEP {step}/{total} · {title.upper()} ", style=f"bold {TEXT} on {SURFACE}")
    console.print()
    console.rule(label, style=ACCENT)


def section(title: str, body: str) -> None:
    console.print(
        Panel(
            body,
            title=f"[bold {ACCENT}]{title}[/]",
            border_style=ACCENT,
            box=box.ROUNDED,
            padding=(0, 1),
        )
    )


def success(msg: str) -> None:
    console.print(f"[{SUCCESS}]✓ {msg}[/]")


def warn(msg: str) -> None:
    console.print(f"[{WARN}]! {msg}[/]")


def error(msg: str) -> None:
    console.print(f"[{ERROR}]x {msg}[/]")


def dim(msg: str) -> None:
    console.print(f"[{MUTED}]{msg}[/]")


def ask_text(prompt: str, default: str | None = None, interactive: bool = True) -> str:
    if not interactive:
        return default or ""
    import questionary

    value = questionary.text(prompt, default=default).ask()
    return value if value is not None else (default or "")


def ask_confirm(
    prompt: str,
    default: bool = True,
    interactive: bool = True,
    assume_yes: bool = False,
) -> bool:
    if not interactive:
        return True if assume_yes else default
    import questionary

    value = questionary.confirm(prompt, default=default).ask()
    return default if value is None else bool(value)


def ask_select(
    prompt: str,
    choices: list[str],
    default: str | None = None,
    interactive: bool = True,
) -> str:
    if not choices:
        raise ValueError("choices must not be empty")
    if not interactive:
        if default and default in choices:
            return default
        return choices[0]
    import questionary

    value = questionary.select(prompt, choices=choices, default=default).ask()
    if value is None:
        return default if default in choices else choices[0]
    return value


def show_yaml(content: str, title: str = "YAML Preview") -> None:
    from rich.syntax import Syntax

    syntax = Syntax(content.rstrip() + "\n", "yaml", theme="ansi_dark", line_numbers=False)
    console.print(Panel(syntax, title=title, border_style=ACCENT, box=box.ROUNDED))


def show_rules_table(rows: list[tuple[str, str]], title: str = "Policy Rules") -> None:
    table = Table(title=title, box=box.SIMPLE_HEAVY, border_style=ACCENT, header_style=f"bold {TEXT}")
    table.add_column("Tool Pattern", style=TEXT)
    table.add_column("Action", style=ACCENT)
    for pattern, action in rows:
        table.add_row(pattern, action)
    console.print(table)


def show_qr(url: str) -> None:
    import qrcode

    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    buf = StringIO()
    qr.print_ascii(out=buf, invert=True)
    body = f"{buf.getvalue().rstrip()}\n\n[{MUTED}]Open:[/] [bold]{url}[/]"
    console.print(Panel(body, title=f"[bold {ACCENT}]Scan To Enroll[/]", border_style=ACCENT, box=box.ROUNDED))


@contextmanager
def spinner(message: str):
    with console.status(f"[{ACCENT}]{message}[/]"):
        yield
