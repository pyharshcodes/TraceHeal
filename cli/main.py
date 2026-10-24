"""TraceHeal Production CLI.

Autonomous Incident Investigation & Shadow-Verified Self-Healing Platform.
"""

import asyncio
import json
import sys
import click

from backend.app.core.config import settings
from backend.app.db.session import async_session_factory, init_db


@click.group()
@click.version_option(version=settings.app_version, prog_name="traceheal")
def cli():
    """TraceHeal: Autonomous SRE & Self-Healing Platform for Microservices."""
    pass


@cli.command("version")
def version_cmd():
    """Display TraceHeal release and build information."""
    click.secho("+--------------------------------------------------------------+", fg="cyan")
    click.secho(f"| TraceHeal Core Engine v{settings.app_version:<38} |", fg="cyan", bold=True)
    click.secho("| Autonomous Incident Investigation & Shadow Self-Healing      |", fg="cyan")
    click.secho("+--------------------------------------------------------------+", fg="cyan")
    click.echo(f"Environment : {settings.env}")
    click.echo(f"Database    : {settings.database_url}")
    click.echo(f"Log Level   : {settings.log_level}")


@cli.command("start")
@click.option("--host", default=settings.host, help="Bind host address.")
@click.option("--port", default=settings.port, type=int, help="Port to listen on.")
@click.option("--reload/--no-reload", default=False, help="Enable auto-reload on code change.")
def start_cmd(host: str, port: int, reload: bool):
    """Start the TraceHeal Core API and SRE Command Center server."""
    click.secho(f"[*] Starting TraceHeal Core API on http://{host}:{port}...", fg="green", bold=True)
    click.secho(f"[*] SRE Command Center UI available at http://{host}:{port}/ui", fg="cyan")
    import uvicorn
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=reload)


@cli.command("auto-heal")
@click.option("--scenario", default="DB_POOL_EXHAUSTION", help="Chaos failure scenario (e.g. DB_POOL_EXHAUSTION, LATENCY_SPIKE)")
@click.option("--target-service", default="payment-service", help="Target microservice name")
@click.option("--trace-count", default=3, type=int, help="Number of telemetry error traces to evaluate")
@click.option("--live-cluster/--simulated", default=False, help="Run live cluster HTTP verification if microservices are running")
def auto_heal_cmd(scenario: str, target_service: str, trace_count: int, live_cluster: bool):
    """Run the complete end-to-end autonomous closed-loop self-healing sequence."""
    async def _run():
        await init_db()
        from backend.app.orchestrator.lifecycle import AutonomousLifecycleOrchestrator

        click.secho("\n+----------------------------------------------------------------------+", fg="cyan", bold=True)
        click.secho("|        TRACEHEAL AUTONOMOUS CLOSED-LOOP SELF-HEALING ENGINE          |", fg="cyan", bold=True)
        click.secho("+----------------------------------------------------------------------+\n", fg="cyan", bold=True)

        click.secho(f"[*] Scenario        : {scenario}", fg="white")
        click.secho(f"[*] Target Service  : {target_service}", fg="white")
        click.secho(f"[*] Mode            : {'Live Cluster Mesh' if live_cluster else 'Shadow Verified Simulation'}\n", fg="white")

        click.secho("[1/7] Ingesting distributed traces & detecting incident...", fg="yellow")
        click.secho("[2/7] Running autonomous RCA diagnostic agent...", fg="yellow")
        click.secho("[3/7] Reproducing fault in isolated process sandbox...", fg="yellow")
        click.secho("[4/7] Synthesizing AST patch & verifying 5 safety policies...", fg="yellow")
        click.secho("[5/7] Deploying canary rollout (10% traffic weight)...", fg="yellow")
        click.secho("[6/7] Validating baseline recovery...", fg="yellow")
        click.secho("[7/7] Generating Post-Incident Review (PIR) and Git Pull Request...\n", fg="yellow")

        orchestrator = AutonomousLifecycleOrchestrator()
        async with async_session_factory() as db:
            manifest = await orchestrator.run_full_autonomous_cycle(
                db=db,
                scenario=scenario,
                target_service=target_service,
                trace_count=trace_count,
                live_cluster=live_cluster,
            )

        click.secho("[SUCCESS] AUTONOMOUS SELF-HEALING CYCLE COMPLETED!", fg="green", bold=True)
        click.secho("----------------------------------------------------------------------", fg="cyan")
        click.secho(f"Incident ID        : {manifest['incident_id']}", fg="white", bold=True)
        click.secho(f"Title              : {manifest['title']}", fg="white")
        click.secho(f"Severity           : {manifest['severity']}", fg="red" if manifest['severity'] == "CRITICAL" else "yellow")
        click.secho(f"Final State        : {manifest['final_status']}", fg="green", bold=True)
        click.secho(f"MTTD               : {manifest['mttd_seconds']}s", fg="cyan")
        click.secho(f"MTTR               : {manifest['mttr_seconds']}s", fg="cyan")
        click.secho(f"Total Run Time     : {manifest['total_execution_seconds']}s", fg="cyan")
        click.secho(f"Git PR Branch      : {manifest['pull_request']['branch_name']}", fg="green")
        click.secho(f"Exported Patch     : {manifest['pull_request'].get('patch_file', 'patches/')}", fg="green")
        click.secho(f"Lifecycle Steps    : {' -> '.join(manifest['lifecycle_progression'])}", fg="magenta")
        click.secho("----------------------------------------------------------------------\n", fg="cyan")

    asyncio.run(_run())


@cli.command("demo")
@click.pass_context
def demo_cmd(ctx):
    """Alias for 'traceheal auto-heal' running the full demonstration."""
    ctx.invoke(auto_heal_cmd)


@cli.group("incident")
def incident_group():
    """Query and inspect TraceHeal incident records."""
    pass


@incident_group.command("list")
@click.option("--limit", default=10, type=int, help="Maximum number of incidents to list")
def list_incidents_cmd(limit: int):
    """List recent incidents tracked in the database."""
    async def _run():
        await init_db()
        from backend.app.incidents.service import list_incidents
        async with async_session_factory() as db:
            incs = await list_incidents(db, limit=limit)

        if not incs:
            click.echo("No incidents recorded in database.")
            return

        click.secho(f"\n{'ID':<38} {'STATUS':<15} {'SEVERITY':<10} {'SERVICE':<18} {'TITLE'}", fg="cyan", bold=True)
        click.secho("-" * 105, fg="cyan")
        for i in incs:
            stat_color = "green" if i.status in ["RESOLVED", "CLOSED"] else "yellow"
            click.secho(f"{i.id:<38} ", nl=False)
            click.secho(f"{i.status:<15} ", fg=stat_color, nl=False)
            click.secho(f"{i.severity:<10} ", fg="red" if i.severity == "CRITICAL" else "white", nl=False)
            click.secho(f"{i.suspect_service or 'unknown':<18} ", nl=False)
            click.secho(f"{i.title}")
        click.echo()

    asyncio.run(_run())


@incident_group.command("inspect")
@click.argument("incident_id")
def inspect_incident_cmd(incident_id: str):
    """Inspect full details of a specific incident by ID."""
    async def _run():
        await init_db()
        from backend.app.incidents.service import get_incident
        async with async_session_factory() as db:
            inc = await get_incident(db, incident_id)

        if not inc:
            click.secho(f"Error: Incident '{incident_id}' not found.", fg="red")
            sys.exit(1)

        click.secho(f"\nIncident: {inc.id}", fg="cyan", bold=True)
        click.echo(f"Title          : {inc.title}")
        click.echo(f"Status         : {inc.status}")
        click.echo(f"Severity       : {inc.severity}")
        click.echo(f"Suspect Service: {inc.suspect_service}")
        click.echo(f"Created At     : {inc.created_at}")
        click.echo(f"Resolved At    : {inc.resolved_at}")
        click.echo(f"Closed At      : {inc.closed_at}")
        click.echo(f"Audit Events   : {len(inc.audit_events)}")
        click.echo(f"Hypotheses     : {len(inc.hypotheses)}")
        click.echo(f"Remediations   : {len(inc.remediations)}\n")

    asyncio.run(_run())


@cli.command("postmortem")
@click.argument("incident_id")
def postmortem_cmd(incident_id: str):
    """Display Post-Incident Review dossier and Git Pull Request details."""
    async def _run():
        await init_db()
        from backend.app.postmortem.generator import PostmortemGenerator
        from backend.app.postmortem.pr_generator import PullRequestGenerator
        async with async_session_factory() as db:
            p_gen = PostmortemGenerator()
            pr_gen = PullRequestGenerator()
            try:
                pm = await p_gen.generate_postmortem(db, incident_id)
                pr = await pr_gen.generate_pull_request(db, incident_id)
                click.secho(f"\n# Postmortem Dossier for {incident_id}", fg="cyan", bold=True)
                click.echo(pm.markdown)
                click.secho("\n# Generated Git Pull Request", fg="green", bold=True)
                click.echo(f"Branch : {pr.branch_name}")
                click.echo(f"Title  : {pr.title}")
                click.echo(f"Patch  : patches/{pr.branch_name.replace('/', '_')}.patch\n")
            except Exception as e:
                click.secho(f"Error generating postmortem: {e}", fg="red")

    asyncio.run(_run())


@cli.group("cluster")
def cluster_group():
    """Inspect and manage target microservices cluster."""
    pass


@cluster_group.command("status")
def cluster_status_cmd():
    """Query health status of the 4 microservices."""
    async def _run():
        from target_services.chaos import ChaosEngine
        engine = ChaosEngine()
        status = await engine.get_cluster_status()
        click.secho("\nTarget Microservices Cluster Status:", fg="cyan", bold=True)
        for svc, info in status.items():
            is_up = info.get("status") == "UP"
            click.secho(f"  * {svc:<22}: ", nl=False)
            click.secho(f"{info.get('status', 'DOWN')}", fg="green" if is_up else "red")
        click.echo()

    asyncio.run(_run())


if __name__ == "__main__":
    cli()
