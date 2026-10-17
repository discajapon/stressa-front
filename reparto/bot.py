"""Bot de Discord con /cambiar <url>: cambia el repo del proyecto activo. Solo el dueño del servidor."""
import asyncio
import os

import discord
from discord import app_commands

from . import config, db
from .github import GitHub
from .servicio import anunciar_cambio, cambiar


def _cambiar(cfg, url, por):
    # Conexión propia: corre en un hilo aparte y SQLite no comparte conexiones entre hilos.
    con = db.abrir(cfg.db)
    try:
        repo, cerrados = cambiar(cfg, GitHub(cfg.github_token), con, url, por)
        anunciar_cambio(cfg, con, repo, cerrados, por)
        return repo
    finally:
        con.close()


def crear(cfg):
    # Solo el intent de servidores (no privilegiado): hace falta para saber quién es el dueño.
    cliente = discord.Client(intents=discord.Intents(guilds=True))
    arbol = app_commands.CommandTree(cliente)

    @arbol.command(name="cambiar", description="Cambia el repositorio del proyecto activo (desde hoy)")
    @app_commands.describe(repo="URL del repositorio de GitHub")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def cambiar_cmd(interaccion: discord.Interaction, repo: str):
        if interaccion.user.id != interaccion.guild.owner_id:
            await interaccion.response.send_message("Solo el dueño del servidor puede cambiar el repo.", ephemeral=True)
            return
        await interaccion.response.defer(ephemeral=True, thinking=True)
        try:
            nuevo = await asyncio.to_thread(_cambiar, cfg, repo, interaccion.user.name)
        except ValueError as e:
            await interaccion.followup.send(f"❌ {e}", ephemeral=True)
            return
        await interaccion.followup.send(f"✅ Proyecto activo: {nuevo}. Lo anuncié en el canal.", ephemeral=True)

    async def registrar(servidor):
        # Registro por servidor: el comando aparece al instante (el global tarda hasta una hora).
        arbol.copy_global_to(guild=servidor)
        await arbol.sync(guild=servidor)

    @cliente.event
    async def on_ready():
        for servidor in cliente.guilds:
            await registrar(servidor)
        print(f"Bot listo como {cliente.user}; /cambiar en {len(cliente.guilds)} servidor(es)", flush=True)

    @cliente.event
    async def on_guild_join(servidor):
        await registrar(servidor)
        print(f"/cambiar registrado en {servidor.name}", flush=True)

    return cliente


def main():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("Falta DISCORD_BOT_TOKEN en el entorno")
    crear(config.cargar()).run(token, log_handler=None)
