import sqlite3
import requests
import os
import pandas as pd
from dotenv import load_dotenv



load_dotenv()
API_KEY = os.getenv("RIOT_API_KEY")

DB_PATH = "data/lol_data.db"
PLAYERS_FILE = "data/players.txt"

REGION = "euw1"
ACCOUNT_REGION = "europe"
BASE_LOL_URL = f"https://{REGION}.api.riotgames.com"
BASE_ACCOUNT_URL = f"https://{ACCOUNT_REGION}.api.riotgames.com"

def create_database():
    """Crée la base de données et les tables si elles n'existent pas."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            player_id TEXT PRIMARY KEY,
            game_name TEXT,
            tag_line TEXT,
            puuid TEXT,
            summoner_id TEXT,
            summoner_level INTEGER,
            rank TEXT,
            tier TEXT,
            league_points INTEGER,
            wins INTEGER,
            losses INTEGER,
            winrate REAL,
            total_ranked_games INTEGER
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            match_id TEXT PRIMARY KEY,
            player_id TEXT,
            champion TEXT,
            role TEXT,
            kills INTEGER,
            deaths INTEGER,
            assists INTEGER,
            game_duration INTEGER,
            win BOOLEAN,
            FOREIGN KEY (player_id) REFERENCES players(player_id)
        )
    ''')

    conn.commit()
    conn.close()

def get_puuid(game_name, tag_line):
    """Récupère le PUUID d'un joueur via son Riot ID."""
    url = f"{BASE_ACCOUNT_URL}/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    headers = {"X-Riot-Token": API_KEY}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["puuid"]
    else:
        print(f"❌ Erreur API Riot pour {game_name}#{tag_line} : {response.status_code}")
        return None

def get_summoner_info(puuid):
    """Récupère les informations du joueur via son PUUID."""
    url = f"{BASE_LOL_URL}/lol/summoner/v4/summoners/by-puuid/{puuid}"
    headers = {"X-Riot-Token": API_KEY}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ Erreur API Summoner : {response.status_code}")
        return None

def get_ranked_stats(summoner_id):
    """Récupère les stats classées du joueur (Solo/Duo)."""
    url = f"{BASE_LOL_URL}/lol/league/v4/entries/by-summoner/{summoner_id}"
    headers = {"X-Riot-Token": API_KEY}
    response = requests.get(url, headers=headers)
    if response.status_code == 200 and response.json():
        return response.json()[0]
    else:
        print(f"❌ Erreur API Ranked : {response.status_code}")
        return None

def update_recent_matches(puuid, player_id, conn, cursor):
    """Récupère les 20 dernières parties d'un joueur et stocke uniquement les matchs classés solo."""
    match_ids_url = f"https://europe.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count=20"
    headers = {"X-Riot-Token": API_KEY}

    response = requests.get(match_ids_url, headers=headers)
    if response.status_code != 200:
        print(f"❌ Erreur récupération matchs : {response.status_code}")
        return

    match_ids = response.json()

    for match_id in match_ids:
        match_url = f"https://europe.api.riotgames.com/lol/match/v5/matches/{match_id}"
        match_response = requests.get(match_url, headers=headers)
        if match_response.status_code != 200:
            continue

        match_data = match_response.json()
        
        # Filtrer par queueId = 420 (RANKED_SOLO_5x5)
        if match_data['info']['queueId'] != 420:
            continue

        # Insérer la partie
        for participant in match_data['info']['participants']:
            if participant['puuid'] == puuid:
                cursor.execute('''
                    INSERT INTO matches (match_id, player_id, champion, role, kills, deaths, assists, game_duration, win)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(match_id) DO NOTHING
                ''', (match_id,
                      player_id,
                      participant['championName'],
                      participant['teamPosition'],
                      participant['kills'],
                      participant['deaths'],
                      participant['assists'],
                      match_data['info']['gameDuration'],
                      participant['win']))
                break

def get_global_stats():
    """
    Calcule les stats globales (toutes les parties de la table `matches`):
      - total_games : nombre de parties totales
      - total_wins  : nombre de parties gagnées
      - total_losses: total_games - total_wins
      - global_winrate: (total_wins / total_games)*100
      - total_time: somme des durations
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1) total_games = COUNT(*)
    cursor.execute("SELECT COUNT(*) FROM matches")
    row = cursor.fetchone()
    total_games = row[0] if row and row[0] else 0

    # 2) total_wins = nombre de parties où `win`=1
    cursor.execute("SELECT COUNT(*) FROM matches WHERE win=1")
    row2 = cursor.fetchone()
    total_wins = row2[0] if row2 and row2[0] else 0

    total_losses = total_games - total_wins

    # 3) total_time = SUM(game_duration)
    cursor.execute("SELECT SUM(game_duration) FROM matches")
    row3 = cursor.fetchone()
    total_time = row3[0] if row3 and row3[0] else 0

    conn.close()

    if total_games > 0:
        global_winrate = (total_wins / total_games) * 100
    else:
        global_winrate = 0

    return {
        "total_games": total_games,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "global_winrate": global_winrate,
        "total_time": total_time
    }

def update_players():
    """Récupère les infos des joueurs et met à jour la base de données (table players + matches)."""
    create_database()

    with open(PLAYERS_FILE, "r") as file:
        players = [line.strip().split("#") for line in file.readlines()]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for game_name, tag_line in players:
        print(f"🔍 Récupération des infos de {game_name}#{tag_line}...")

        puuid = get_puuid(game_name, tag_line)
        if not puuid:
            continue

        summoner_info = get_summoner_info(puuid)
        if not summoner_info:
            continue

        ranked_stats = get_ranked_stats(summoner_info["id"])
        if not ranked_stats:
            ranked_stats = {"tier": "Unranked", "rank": "", "leaguePoints": 0, "wins": 0, "losses": 0}

        winrate = (ranked_stats["wins"] / (ranked_stats["wins"] + ranked_stats["losses"]) * 100) if ranked_stats["losses"] > 0 else 0
        total_games = ranked_stats["wins"] + ranked_stats["losses"]

        # Insertion/Update dans table players
        cursor.execute('''
            INSERT INTO players (player_id, game_name, tag_line, puuid, summoner_id, summoner_level, rank, tier, league_points, wins, losses, winrate, total_ranked_games)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
            summoner_level=excluded.summoner_level,
            rank=excluded.rank,
            tier=excluded.tier,
            league_points=excluded.league_points,
            wins=excluded.wins,
            losses=excluded.losses,
            winrate=excluded.winrate,
            total_ranked_games=excluded.total_ranked_games
        ''', (
            f"{game_name}#{tag_line}",
            game_name,
            tag_line,
            puuid,
            summoner_info["id"],
            summoner_info["summonerLevel"],
            ranked_stats["rank"],
            ranked_stats["tier"],
            ranked_stats["leaguePoints"],
            ranked_stats["wins"],
            ranked_stats["losses"],
            winrate,
            total_games
        ))

        # On insère également les dernières parties du joueur
        update_recent_matches(puuid, f"{game_name}#{tag_line}", conn, cursor)

        print(f"✅ {game_name}#{tag_line} mis à jour avec succès.")

    conn.commit()
    conn.close()

def get_player_aggregates(player_id):
    """
    Calcule toutes les stats pour un joueur uniquement depuis `matches`.
      - total_games       : COUNT(*)
      - total_wins        : COUNT(*) WHERE win=1
      - total_losses      : total_games - total_wins
      - winrate           : (total_wins / total_games)*100
      - kills, deaths, assists, game_time, match_count (déjà fait)
      - avg_time, time_hours
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # total_games pour ce joueur
    cursor.execute("SELECT COUNT(*) FROM matches WHERE player_id=?",(player_id,))
    row_games = cursor.fetchone()
    total_games = row_games[0] if row_games else 0

    # total_wins
    cursor.execute("SELECT COUNT(*) FROM matches WHERE player_id=? AND win=1",(player_id,))
    row_wins = cursor.fetchone()
    total_wins = row_wins[0] if row_wins else 0

    total_losses = total_games - total_wins

    # kills, deaths, assists, game_duration, ...
    cursor.execute('''
        SELECT 
            SUM(kills),
            SUM(deaths),
            SUM(assists),
            SUM(game_duration),
            COUNT(DISTINCT champion),
            COUNT(*)
        FROM matches
        WHERE player_id = ?
    ''',(player_id,))
    row = cursor.fetchone()

    if not row or all(val is None for val in row):
        # Aucune partie
        data = {
            "total_games": 0,
            "total_wins": 0,
            "total_losses": 0,
            "winrate": 0,
            "kills": 0,
            "deaths": 0,
            "assists": 0,
            "game_time": 0,
            "unique_champions": 0,
            "match_count": 0,
            "avg_time": 0,
            "time_hours": 0
        }
        conn.close()
        return data

    sum_kills, sum_deaths, sum_assists, sum_time, uniq_champs, match_count = row
    conn.close()

    sum_kills = sum_kills or 0
    sum_deaths = sum_deaths or 0
    sum_assists = sum_assists or 0
    sum_time = sum_time or 0
    uniq_champs = uniq_champs or 0
    match_count = match_count or 0

    if total_games > 0:
        local_winrate = (total_wins / total_games)*100
    else:
        local_winrate = 0

    avg_time = sum_time/match_count if match_count>0 else 0
    time_hours = sum_time/3600

    data = {
        "total_games": total_games,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "winrate": local_winrate,
        "kills": sum_kills,
        "deaths": sum_deaths,
        "assists": sum_assists,
        "game_time": sum_time,
        "unique_champions": uniq_champs,
        "match_count": match_count,
        "avg_time": avg_time,
        "time_hours": time_hours
    }
    return data


if __name__ == "__main__":
    update_players()
