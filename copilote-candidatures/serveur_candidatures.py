"""Serveur MCP : suivi de candidatures (SQLite) pour un agent Dust.

Installation :  pip install "mcp[cli]"
Test local   :  mcp dev serveur_candidatures.py
Lancement    :  python serveur_candidatures.py   (HTTP sur http://localhost:8000/mcp)
"""

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DB_PATH = Path(__file__).with_name("candidatures.db")
STATUTS = ["a_postuler", "envoyee", "entretien", "offre", "refus"]

# host/port utilisés par le transport HTTP
mcp = FastMCP("candidatures", host="0.0.0.0", port=8000)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS candidatures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entreprise TEXT NOT NULL,
            poste TEXT NOT NULL,
            url TEXT,
            statut TEXT NOT NULL DEFAULT 'envoyee',
            notes TEXT,
            date_candidature TEXT NOT NULL,
            derniere_maj TEXT NOT NULL
        )"""
    )
    return conn


@mcp.tool()
def ajouter_candidature(
    entreprise: str, poste: str, url: str = "", statut: str = "envoyee", notes: str = ""
) -> dict:
    """Enregistre une nouvelle candidature. Statuts possibles :
    a_postuler, envoyee, entretien, offre, refus."""
    if statut not in STATUTS:
        return {"erreur": f"Statut invalide. Valeurs possibles : {STATUTS}"}
    aujourd_hui = date.today().isoformat()
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO candidatures (entreprise, poste, url, statut, notes, "
            "date_candidature, derniere_maj) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entreprise, poste, url, statut, notes, aujourd_hui, aujourd_hui),
        )
        return {"id": cur.lastrowid, "message": "Candidature enregistrée"}


@mcp.tool()
def lister_candidatures(statut: str = "") -> list[dict]:
    """Liste les candidatures, éventuellement filtrées par statut."""
    with get_db() as db:
        if statut:
            rows = db.execute(
                "SELECT * FROM candidatures WHERE statut = ? ORDER BY derniere_maj DESC",
                (statut,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM candidatures ORDER BY derniere_maj DESC"
            ).fetchall()
        return [dict(r) for r in rows]


@mcp.tool()
def maj_statut(id: int, statut: str, notes: str = "") -> dict:
    """Met à jour le statut d'une candidature (et ajoute des notes si fournies)."""
    if statut not in STATUTS:
        return {"erreur": f"Statut invalide. Valeurs possibles : {STATUTS}"}
    with get_db() as db:
        cur = db.execute(
            "UPDATE candidatures SET statut = ?, "
            "notes = CASE WHEN ? != '' THEN ? ELSE notes END, derniere_maj = ? "
            "WHERE id = ?",
            (statut, notes, notes, date.today().isoformat(), id),
        )
        if cur.rowcount == 0:
            return {"erreur": f"Aucune candidature avec l'id {id}"}
        return {"message": "Statut mis à jour"}


@mcp.tool()
def relances_a_faire(jours: int = 7) -> list[dict]:
    """Candidatures envoyées sans nouvelle depuis au moins N jours."""
    limite = (date.today() - timedelta(days=jours)).isoformat()
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM candidatures WHERE statut = 'envoyee' "
            "AND derniere_maj <= ? ORDER BY derniere_maj",
            (limite,),
        ).fetchall()
        return [dict(r) for r in rows]


@mcp.resource("stats://candidatures")
def stats() -> dict:
    """Nombre de candidatures par statut."""
    with get_db() as db:
        rows = db.execute(
            "SELECT statut, COUNT(*) AS n FROM candidatures GROUP BY statut"
        ).fetchall()
        return {r["statut"]: r["n"] for r in rows}


if __name__ == "__main__":
    # Transport HTTP : nécessaire pour qu'un service distant comme Dust puisse s'y connecter
    mcp.run(transport="streamable-http")