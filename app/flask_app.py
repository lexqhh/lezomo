from flask import Flask, render_template
import sqlite3
import pandas as pd

from app.data_manager import DB_PATH, get_player_aggregates, get_global_stats

app = Flask(__name__)

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
    """
    Page principale :
      - Stats globales (top)
      - 3 classements (Kills/Deaths/Assists)
      - BEST KDA
      - 3 classements (Winrate, AvgTime, TotalTime) en dessous
    """
    # 1) Stats globales
    stats_global = get_global_stats()
    stats_global["formatted_time"] = format_duration(stats_global["total_time"])

    # 2) Récupérer les joueurs de la table `players`
    df_players = get_all_players()

    # Construire un DataFrame pour kills/deaths/assists (comme déjà fait)
    rows = []
    for _, rowp in df_players.iterrows():
        player_id = rowp["player_id"]
        agg = get_player_aggregates(player_id)  # Renvoie kills, deaths, assists, avg_time, time_hours, etc.

        rows.append({
            "player_id": player_id,
            "game_name": rowp["game_name"],

            "kills": agg["kills"],
            "deaths": agg["deaths"],
            "assists": agg["assists"],

            # Info sur parties
            "winrate": agg["winrate"],
            "total_games": agg["total_games"],
            "avg_time": agg["avg_time"],
            "time_hours": agg["time_hours"],

            # Nombre de champions uniques
            "unique_champions": agg["unique_champions"],
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
        most_champions_list=most_champions

    )


if __name__ == "__main__":
    app.run(debug=True)
