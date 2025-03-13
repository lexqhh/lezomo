from flask import Flask, render_template, jsonify, send_file, url_for
import sqlite3
import pandas as pd
import os
import datetime
import pytz

# --- ICI C'EST LE FICHIER WEBSITE - ENLEVER "app." devant data_manager pour que ça fonctionne ---
from app.data_manager import DB_PATH, get_player_aggregates, get_global_stats, update_players, get_player_main_role, get_top_3_champions, is_player_in_game


app = Flask(__name__, static_folder=os.path.join(os.getcwd(), "static"))
last_update = None  # Variable globale pour stocker la dernière date de mise à jour
TZ = pytz.timezone("Europe/Paris")

rank_value = {
    "CHALLENGER": 1, 
    "GRANDMASTER": 2,
    "MASTER": 3,
    "DIAMOND": 4,
    "PLATINUM": 5,
    "GOLD": 6,
    "SILVER": 7,
    "BRONZE": 8,
    "IRON": 9,
    "UNRANKED": 10
}

def get_rank_score(player):
    # Ex: player["rank"] = "PLATINUM", player["tier"] = "IV"
    # On combine rank_value + tier
    base = rank_value.get(player["rank"], 10)  # par défaut 10 => UNRANKED
    # Si le rank est PLATINUM et tier = "IV", on peut rajouter un offset
    # ex: "I" = +0, "II" = +0.25, "III" = +0.5, "IV" = +0.75
    tier_offset = {
        "I": 0.0,
        "II": 0.25,
        "III": 0.50,
        "IV": 0.75
    }
    offset = tier_offset.get(player["tier"], 0)
    return base + offset

@app.route("/update-db", methods=["GET"])
def update_db():
    update_players()  # Exécute la mise à jour
    # On stocke l'heure actuelle dans la variable globale
    global last_update
    last_update = datetime.datetime.now(TZ)
    return jsonify({"message": "Base de données mise à jour !"}), 200

@app.route("/download-db", methods=["GET"])
def download_db():
    # Récupère le chemin absolu du fichier DB
    base_dir = os.path.dirname(os.path.abspath(__file__)) 
    # remonte d'un cran si "data" est au même niveau que le dossier "app"
    db_path = os.path.join(base_dir, "..", "data", "lol_data.db")

    return send_file(
        db_path,
        as_attachment=True,
        download_name="lol_data.db"
    )

def get_all_players():
    """Charge la table players en DataFrame Pandas."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM players", conn)
    conn.close()
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
    # 1) Stats globales
    stats_global = get_global_stats()
    stats_global["formatted_time"] = format_duration(stats_global["total_time"])

    # 2) Charger tous les joueurs
    df_players = get_all_players()

    # 3) Construire un DataFrame (df_all) en combinant aggregator + table players
    rows = []
    for _, rowp in df_players.iterrows():
        player_id = rowp["player_id"]
        agg = get_player_aggregates(player_id)  # kills, deaths, total_games, etc.
        simulate_mode = False  # Changez cette variable pour tester
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

    # 3) KILLS / DEATHS / ASSISTS
    top_kills = df_all.sort_values("kills", ascending=False).head(6).to_dict(orient="records")
    top_deaths = df_all.sort_values("deaths", ascending=False).head(6).to_dict(orient="records")
    top_assists = df_all.sort_values("assists", ascending=False).head(6).to_dict(orient="records")

    # BEST KDA
    df_all["kda"] = (df_all["kills"] + df_all["assists"]) / df_all["deaths"].replace(0, 1)
    best_kda = df_all.sort_values("kda", ascending=False).head(6).to_dict(orient="records")

    # 4) Nouveaux classements
    # Best Winrate (desc)
    best_winrate = df_all.sort_values("winrate", ascending=False).head(6).to_dict(orient="records")
    # Lowest Average Game Length (asc : on veut le plus petit en haut)
    lowest_avg_time = df_all.sort_values("avg_time", ascending=True).head(6).to_dict(orient="records")
    # Total Time Played (desc : plus grand en haut)
    best_total_time = df_all.sort_values("time_hours", ascending=False).head(6).to_dict(orient="records")

    # 1) Unique Champions
    most_champions = df_all.sort_values("unique_champions", ascending=False).head(6).to_dict(orient="records")

    #Rank score
    df_all["rank_score"] = df_all.apply(lambda row: get_rank_score(row), axis=1)
    # Tri du plus petit rank_score au plus grand => le plus haut rang
    best_rank = df_all.sort_values("rank_score", ascending=True).head(6).to_dict(orient="records")

    # On formate la date si elle existe
    if last_update is not None:
        last_update_str = last_update.strftime("%d/%m/%Y %H:%M")
    else:
        last_update_str = "Pas encore mise à jour"


    return render_template(
        "rankings.html",
        last_update=last_update_str,
        stats=stats_global,
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
