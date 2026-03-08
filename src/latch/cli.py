import sys

import questionary
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import audit, policy, totp
from .config import auto_detect_gateway, config_dir, load, save

console = Console()

BRAND = "[bold red]🔐 Latch[/bold red]"


def _header(title: str) -> None:
    console.print(Panel(Text(title, justify="center", style="bold"), border_style="red", padding=(0, 4)))


# ── setup ──────────────────────────────────────────────────────────────────────

def cmd_setup() -> None:
    _header("Latch Setup")
    console.print()

    cfg = load()

    # Auto-detect OpenClaw gateway
    url, token = auto_detect_gateway()
    console.print(f"  Gateway URL:   [cyan]{url}[/cyan]")

    if token:
        console.print(f"  Gateway token: [green]detected[/green]")
    else:
        console.print(f"  Gateway token: [red]not found[/red]")
        token = questionary.password("Enter OpenClaw gateway token:").ask()
        if token is None:
            return

    account = questionary.text(
        "Your identifier (shown in Passwords app):",
        default=cfg.get("totp_account", "user"),
    ).ask()
    if account is None:
        return

    cfg.update({
        "openclaw_webhook_url": url,
        "openclaw_webhook_token": token,
        "totp_account": account,
    })
    save(cfg)

    console.print()
    with console.status("[bold red]Generating TOTP secret...[/bold red]"):
        secret = totp.generate_secret()

    uri = totp.get_provisioning_uri(secret, account)
    _show_qr(uri, secret)

    console.print()
    code = questionary.text("Enter the 6-digit code from your Passwords app to verify:").ask()
    if code is None:
        return

    if totp.verify(code, secret=secret):
        totp.enroll(secret)
        console.print()
        console.print("[bold green]✓ TOTP verified! Setup complete.[/bold green]")
        console.print()
        console.print(Panel(
            "[bold]Next steps:[/bold]\n\n"
            "Start the server:\n"
            "  [cyan]latch run[/cyan]\n\n"
            "Run [cyan]latch policy[/cyan] to configure approval rules.",
            border_style="green",
        ))
    else:
        console.print("[bold red]✗ Code incorrect. Run [cyan]latch setup[/cyan] again.[/bold red]")


def _show_qr(uri: str, secret: str) -> None:
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(uri)
        qr.make(fit=True)
        console.print()
        console.print(Panel(
            "[bold]Scan with iPhone Passwords app[/bold]\n"
            "Settings → Passwords → + → Set Up Verification Code → Scan QR Code",
            border_style="yellow",
        ))
        qr.print_ascii(invert=True)
    except ImportError:
        pass

    console.print(f"\n[dim]Or enter manually:[/dim] [bold cyan]{secret}[/bold cyan]\n")


# ── policy ─────────────────────────────────────────────────────────────────────

def cmd_policy() -> None:
    _header("Policy Editor")
    console.print()

    while True:
        pol = policy.load()
        rules = pol.get("rules", [])
        default = pol.get("defaultAction", "allow")

        table = Table(show_header=True, header_style="bold red")
        table.add_column("#", style="dim", width=3)
        table.add_column("Tool Pattern")
        table.add_column("Action", style="bold")
        for i, r in enumerate(rules):
            action = r["action"]
            color = {"allow": "green", "deny": "red", "approve": "yellow", "ask": "cyan"}.get(action, "white")
            table.add_row(str(i + 1), r["match"]["tool"], f"[{color}]{action}[/{color}]")
        table.add_row("*", "(everything else)", f"[dim]{default}[/dim]")
        console.print(table)
        console.print()

        choice = questionary.select("What would you like to do?", choices=[
            "Add rule", "Remove rule", "Change default action", "View YAML", "Done",
        ]).ask()

        if choice is None or choice == "Done":
            break

        elif choice == "Add rule":
            pattern = questionary.text("Tool pattern (regex):").ask()
            if not pattern:
                continue
            action = questionary.select("Action:", choices=["approve", "allow", "deny", "ask"]).ask()
            if not action:
                continue
            rules.append({"match": {"tool": pattern}, "action": action})
            pol["rules"] = rules
            policy.save(pol)

        elif choice == "Remove rule":
            if not rules:
                console.print("[dim]No rules to remove.[/dim]")
                continue
            options = [f"{i+1}. {r['match']['tool']} → {r['action']}" for i, r in enumerate(rules)]
            sel = questionary.select("Remove which rule?", choices=options + ["Cancel"]).ask()
            if sel and sel != "Cancel":
                idx = int(sel.split(".")[0]) - 1
                rules.pop(idx)
                pol["rules"] = rules
                policy.save(pol)

        elif choice == "Change default action":
            new_default = questionary.select("Default action:", choices=["allow", "deny", "approve"]).ask()
            if new_default:
                pol["defaultAction"] = new_default
                policy.save(pol)

        elif choice == "View YAML":
            console.print(Panel(yaml.dump(pol), title="policy.yaml", border_style="dim"))


# ── audit ──────────────────────────────────────────────────────────────────────

def cmd_audit() -> None:
    _header("Audit Log")
    console.print()
    entries = audit.read(limit=20)
    if not entries:
        console.print("[dim]No audit entries yet.[/dim]")
        return
    table = Table(show_header=True, header_style="bold red")
    table.add_column("Time", style="dim")
    table.add_column("Tool")
    table.add_column("Action")
    table.add_column("Decision", style="bold")
    table.add_column("Reason", style="dim")
    for e in reversed(entries):
        decision = e.get("decision", "")
        color = "green" if decision == "allow" else "red"
        table.add_row(
            e.get("ts", "")[:19],
            e.get("tool", ""),
            e.get("action", ""),
            f"[{color}]{decision}[/{color}]",
            e.get("reason", "")[:60],
        )
    console.print(table)


# ── status ─────────────────────────────────────────────────────────────────────

def cmd_status() -> None:
    _header("Latch Status")
    console.print()
    cfg = load()
    enrolled = totp.is_enrolled()
    pol = policy.load()
    entries = audit.read(limit=5)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", width=24)
    table.add_column()
    table.add_row("Config dir", str(config_dir()))
    gw_url, gw_token = auto_detect_gateway()
    table.add_row("OpenClaw gateway", gw_url)
    table.add_row("Gateway token", "[green]detected[/green]" if gw_token else "[red]not found[/red]")
    table.add_row("TOTP enrolled", "[green]yes[/green]" if enrolled else "[red]no — run latch setup[/red]")
    table.add_row("Policy rules", str(len(pol.get("rules", []))))
    table.add_row("Default action", pol.get("defaultAction", "allow"))
    console.print(table)

    if entries:
        console.print()
        console.print("[dim]Recent approvals:[/dim]")
        for e in reversed(entries):
            decision = e.get("decision", "")
            color = "green" if decision == "allow" else "red"
            console.print(f"  [{color}]{decision:5}[/{color}]  {e.get('tool', '')}  [dim]{e.get('ts', '')[:19]}[/dim]")


# ── reset ──────────────────────────────────────────────────────────────────────

def cmd_reset() -> None:
    confirmed = questionary.confirm(
        "This will delete your current TOTP secret and require re-enrolling. Continue?"
    ).ask()
    if confirmed:
        (config_dir() / "totp_secret.key").unlink(missing_ok=True)
        console.print("[yellow]TOTP secret deleted. Run [cyan]latch setup[/cyan] to re-enroll.[/yellow]")


# ── run ───────────────────────────────────────────────────────────────────────

def cmd_run() -> None:
    from .server import main as server_main
    server_main()


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    commands = {
        "setup": cmd_setup,
        "run": cmd_run,
        "policy": cmd_policy,
        "audit": cmd_audit,
        "status": cmd_status,
        "reset": cmd_reset,
    }

    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        console.print(f"\n{BRAND} — secure your AI agent\n")
        console.print("Commands:")
        for name in commands:
            console.print(f"  [cyan]latch {name}[/cyan]")
        console.print()
        sys.exit(0 if len(sys.argv) < 2 else 1)

    commands[sys.argv[1]]()
