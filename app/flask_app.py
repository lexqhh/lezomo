from flask import Flask, render_template, jsonify, send_file, url_for, redirect
import pandas as pd
import os
import datetime
import pytz
import subprocess
import tempfile
from dotenv import load_dotenv

# Charger les variables du fichier .env
load_dotenv()

print("Current working directory:", os.getcwd())


# --- ICI C'EST LE FICHIER WEBSITE - AJOUTER "app." devant data_manager pour que ça fonctionne ---
from app.data_manager import engine, SessionLocal, Base, Player, Match, get_global_stats, update_players, get_player_main_role, get_top_3_champions, is_player_in_game, get_player_aggregates

app = Flask(__name__, static_folder=os.path.join(os.getcwd(), "static"))
last_update = None  # Variable globale pour stocker la dernière date de mise à jour
TZ = pytz.timezone("Europe/Paris")

# Définition de l'ordre pour le tier (du meilleur au moins bon)
tier_order = {
    "CHALLENGER": 1,
    "GRANDMASTER": 2,
    "MASTER": 3,
    "DIAMOND": 4,
    "EMERALD": 5,
    "PLATINUM": 6,
    "GOLD": 7,
    "SILVER": 8,
    "BRONZE": 9,
    "IRON": 10,
    "UNRANKED": 11
}

# Définition de l'ordre pour la division (I est meilleur que II, etc.)
division_order = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4
}

@app.route("/update-db", methods=["GET"])
def update_db():
    global last_update
    last_update = datetime.datetime.now(TZ)  # ✅ Mise à jour AVANT l'appel API
    print(f"🕒 Timer mis à jour immédiatement : {last_update}")

    try:
        update_players()  # ✅ Mise à jour des joueurs
        print(f"✅ Base de données mise à jour avec succès à {last_update}")
    except Exception as e:
        print(f"❌ Erreur dans /update-db : {e}")
        return render_template("update_result.html", error=True, last_update=last_update.strftime("%d/%m/%Y %H:%M"))

    return render_template("update_result.html", error=False, last_update=last_update.strftime("%d/%m/%Y %H:%M"))

@app.route("/download-db", methods=["GET"])
def download_db():
    # Pour compatibilité : télécharge le fichier SQLite (si toujours utilisé)
    base_dir = os.path.dirname(os.path.abspath(__file__)) 
    db_path = os.path.join(base_dir, "..", "data", "lol_data.db")
    return send_file(db_path, as_attachment=True, download_name="lol_data.db")

@app.route("/get-last-update", methods=["GET"])
def get_last_update():
    global last_update
    return jsonify({"last_update": last_update.strftime("%d/%m/%Y %H:%M") if last_update else "Aucune mise à jour"}), 200


@app.route("/download-db-backup", methods=["GET"])
def download_db_backup():
    """
    Génère une sauvegarde de la base PostgreSQL via pg_dump et renvoie le fichier SQL.
    Attention : pg_dump doit être installé et accessible dans le PATH, sinon utilisez son chemin absolu.
    """
    DB_HOST = os.getenv("host")
    DB_PORT = os.getenv("port")
    DB_USER = os.getenv("user")
    DB_NAME = os.getenv("dbname")
    DB_PASSWORD = os.getenv("password")
    
    # Définir la variable d'environnement pour le mot de passe
    os.environ["PGPASSWORD"] = DB_PASSWORD

    # Créer un fichier temporaire pour la sauvegarde
    temp_file = tempfile.NamedTemporaryFile(suffix=".sql", delete=False)
    backup_file = temp_file.name
    temp_file.close()

    # Construire la commande pg_dump
    # Si pg_dump n'est pas dans le PATH, remplacez "pg_dump" par le chemin complet (ex: "C:\\Program Files\\PostgreSQL\\14\\bin\\pg_dump.exe")
    command = f"pg_dump -h {DB_HOST} -p {DB_PORT} -U {DB_USER} -d {DB_NAME} -F p -f {backup_file}"
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        return f"Erreur lors de la sauvegarde : {e}", 500

    return send_file(backup_file, as_attachment=True, download_name="backup.sql")

def get_all_players():
    # Utilisation de SQLAlchemy pour charger la table players
    df = pd.read_sql_table("players", con=engine)
    return df

def format_duration(seconds):
    """Convertit un nombre de secondes en 'Xd Yh Zm'."""
    days = seconds // 86400
    remain = seconds % 86400
    hours = remain // 3600
    remain %= 3600
    minutes = remain // 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append("0m")
    return " ".join(parts)

@app.route("/")
def index():
    session = SessionLocal()
    
    # 1️⃣ Récupérer les stats globales
    stats_global = get_global_stats()
    stats_global["formatted_time"] = format_duration(stats_global["total_time"])

    # 2️⃣ Calculer le % de premier dragon pris en ignorant les NULL
    total_matches_dragon = session.query(Match).filter(Match.first_dragon_taken.isnot(None)).count()
    first_dragon_taken_count = session.query(Match).filter(Match.first_dragon_taken == True).count()

    first_dragon_rate = (first_dragon_taken_count / total_matches_dragon) * 100 if total_matches_dragon > 0 else None

    # 3️⃣ Calculer le % de premier Void Grubs pris en ignorant les NULL
    total_matches_void_grubs = session.query(Match).filter(Match.first_void_grubs_taken.isnot(None)).count()
    first_void_grubs_taken_count = session.query(Match).filter(Match.first_void_grubs_taken == True).count()

    first_void_grubs_rate = (first_void_grubs_taken_count / total_matches_void_grubs) * 100 if total_matches_void_grubs > 0 else None

    # 4️⃣ Charger tous les joueurs depuis PostgreSQL
    df_players = get_all_players()

    # 5️⃣ Combiner les données des joueurs et leurs agrégats
    rows = []
    for _, rowp in df_players.iterrows():
        player_id = rowp["player_id"]
        agg = get_player_aggregates(player_id)
        simulate_mode = False  
        in_game = is_player_in_game(rowp["puuid"], simulate_mode)

        rows.append({
            "player_id": player_id,
            "game_name": rowp["game_name"],
            "tag_line": rowp["tag_line"],
            "rank": rowp["rank"],
            "tier": rowp["tier"],
            "lp": rowp["league_points"],
            "winrate": agg.get("winrate", 0),
            "total_games": agg.get("total_games", 0),
            "kills": agg.get("kills", 0),
            "deaths": agg.get("deaths", 0),
            "assists": agg.get("assists", 0),
            "kda": (agg.get("kills", 0) + agg.get("assists", 0)) / (agg.get("deaths", 1) if agg.get("deaths", 1) != 0 else 1),
            "role": get_player_main_role(player_id)[0],
            "role_percentage": round(get_player_main_role(player_id)[1], 1),
            "champions": get_top_3_champions(player_id),
            "avg_time": agg.get("avg_time", 0),
            "time_hours": agg.get("time_hours", 0),
            "unique_champions": agg.get("unique_champions", 0),
            "in_game": in_game
        })

    df_all = pd.DataFrame(rows)

    # 6️⃣ Classements secondaires
    top_kills = df_all.sort_values("kills", ascending=False).head(6).to_dict(orient="records")
    top_deaths = df_all.sort_values("deaths", ascending=False).head(6).to_dict(orient="records")
    top_assists = df_all.sort_values("assists", ascending=False).head(6).to_dict(orient="records")
    df_all["kda"] = (df_all["kills"] + df_all["assists"]) / df_all["deaths"].replace(0, 1)
    best_kda = df_all.sort_values("kda", ascending=False).head(6).to_dict(orient="records")
    best_winrate = df_all.sort_values("winrate", ascending=False).head(6).to_dict(orient="records")
    lowest_avg_time = df_all.sort_values("avg_time", ascending=True).head(6).to_dict(orient="records")
    best_total_time = df_all.sort_values("time_hours", ascending=False).head(6).to_dict(orient="records")
    most_champions = df_all.sort_values("unique_champions", ascending=False).head(6).to_dict(orient="records")

    # 7️⃣ Classement par rang (tri multi-critères)
    df_all["tier_norm"] = df_all["tier"].str.strip().str.upper().map(tier_order)
    df_all["division_norm"] = df_all["rank"].str.strip().str.upper().map(division_order)
    df_all["tier_norm"] = df_all["tier_norm"].fillna(tier_order["UNRANKED"])
    df_all["division_norm"] = df_all["division_norm"].fillna(max(division_order.values()) + 1)

    best_rank = df_all.sort_values(
        by=["tier_norm", "division_norm", "lp"],
        ascending=[True, True, False]
    ).head(6).to_dict(orient="records")

    # 8️⃣ Formatage de la date de mise à jour
    if last_update is not None:
        last_update_str = last_update.strftime("%d/%m/%Y %H:%M")
    else:
        last_update_str = "Pas encore mise à jour"

    print(f"📅 Envoi de la dernière mise à jour à la page : {last_update}")

    # ✅ Fermer la session
    session.close()

    return render_template(
        "rankings.html",
        last_update=last_update_str,
        stats=stats_global,
        first_dragon_rate=first_dragon_rate,  # ✅ Ajout du pourcentage de premier dragon
        first_void_grubs_rate=first_void_grubs_rate,  # ✅ Ajout du pourcentage de premier Void Grubs
        most_kills_list=top_kills,
        most_deaths_list=top_deaths,
        most_assists_list=top_assists,
        best_kda_list=best_kda,
        best_winrate_list=best_winrate,
        lowest_avg_time_list=lowest_avg_time,
        best_total_time_list=best_total_time,
        most_champions_list=most_champions,
        best_rank_list=best_rank
    )

if __name__ == "__main__":
    app.run(debug=True)
