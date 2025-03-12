from flask import Flask, render_template, jsonify, send_file, url_for
import sqlite3
import pandas as pd
import os

from app.data_manager import DB_PATH, get_player_aggregates, get_global_stats, update_players

app = Flask(__name__, static_folder=os.path.join(os.getcwd(), "static"))

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

        rows.append({
            "player_id": player_id,
            "game_name": rowp["game_name"],
            "tag_line": rowp["tag_line"],   # ✅ On récupère le tag_line

            "rank": rowp["rank"],
            "tier": rowp["tier"],

            # Valeurs agrégées
            "kills": agg["kills"],
            "deaths": agg["deaths"],
            "assists": agg["assists"],
            "winrate": agg["winrate"],
            "total_games": agg["total_games"],
            "avg_time": agg["avg_time"],
            "time_hours": agg["time_hours"],
            "unique_champions": agg["unique_champions"]
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


    return render_template(
        "rankings.html",
        stats=stats_global,

        # Existing:
        most_kills_list=top_kills,
        most_deaths_list=top_deaths,
        most_assists_list=top_assists,
        best_kda_list=best_kda,

        # New triple
        best_winrate_list=best_winrate,
        lowest_avg_time_list=lowest_avg_time,
        best_total_time_list=best_total_time,

        # "MOST CHAMPIONS"
        most_champions_list=most_champions,

        #RANKS
        best_rank_list=best_rank,
)


if __name__ == "__main__":
    app.run(debug=True)
