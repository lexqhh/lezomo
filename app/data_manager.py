import requests
import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Integer, Boolean, Float, ForeignKey, func
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

Base = declarative_base()

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# Récupérer les variables
USER = os.getenv("user")
PASSWORD = os.getenv("password")
HOST = os.getenv("host")
PORT = os.getenv("port")
DBNAME = os.getenv("dbname")

# Construire la chaîne de connexion SQLAlchemy avec sslmode=require
DATABASE_URL = f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{PORT}/{DBNAME}?sslmode=require"

# Créer l'engine SQLAlchemy
engine = create_engine(DATABASE_URL, poolclass=NullPool)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Player(Base):
    __tablename__ = 'players'
    player_id = Column(String, primary_key=True, index=True)
    game_name = Column(String)
    tag_line = Column(String)
    puuid = Column(String)
    summoner_id = Column(String)
    summoner_level = Column(Integer)
    rank = Column(String)
    tier = Column(String)
    league_points = Column(Integer)
    wins = Column(Integer)
    losses = Column(Integer)
    winrate = Column(Float)
    total_ranked_games = Column(Integer)

class Match(Base):
    __tablename__ = 'matches'
    match_id = Column(String, primary_key=True)
    player_id = Column(String, ForeignKey('players.player_id'), primary_key=True)
    champion = Column(String)
    role = Column(String)
    kills = Column(Integer)
    deaths = Column(Integer)
    assists = Column(Integer)
    game_duration = Column(Integer)
    win = Column(Boolean)

API_KEY = os.getenv("RIOT_API_KEY")

DB_PATH = "data/lol_data.db"
PLAYERS_FILE = "data/players.txt"

REGION = "euw1"
ACCOUNT_REGION = "europe"
BASE_LOL_URL = f"https://{REGION}.api.riotgames.com"
BASE_ACCOUNT_URL = f"https://{ACCOUNT_REGION}.api.riotgames.com"

def is_player_in_game(encrypted_puuid, simulate=False):
    """
    Laisser sur False ici
    Uniquement changer dans flask_app.py - simulate_mode = False  # True = Simulation, False = API
    """
    if simulate:
        return True
    url = f"{BASE_LOL_URL}/lol/spectator/v5/active-games/by-summoner/{encrypted_puuid}"
    headers = {"X-Riot-Token": API_KEY}
    response = requests.get(url, headers=headers)
    return response.status_code == 200

def get_player_main_role(player_id):
    """Détermine le rôle principal joué par un joueur en utilisant SQLAlchemy."""
    session = SessionLocal()
    try:
        # Récupérer le nombre total de parties pour le joueur
        total_games = session.query(func.count(Match.match_id)).filter(Match.player_id == player_id).scalar()
        
        if not total_games or total_games == 0:
            return "UNKNOWN", 0

        # Récupérer le rôle le plus joué par le joueur
        result = session.query(Match.role, func.count(Match.role).label("role_count")) \
                        .filter(Match.player_id == player_id) \
                        .group_by(Match.role) \
                        .order_by(func.count(Match.role).desc()) \
                        .first()
                        
        if result:
            main_role, count = result
            percentage = (count / total_games) * 100
            return main_role, percentage
        else:
            return "UNKNOWN", 0
    finally:
        session.close()

    # Ensuite, on récupère le rôle le plus joué
    cursor.execute('''
        SELECT role, COUNT(*) as count
        FROM matches
        WHERE player_id = ?
        GROUP BY role
        ORDER BY count DESC
        LIMIT 1
    ''', (player_id,))
    
    row = cursor.fetchone()
    conn.close()

    if row:
        return row[0], (row[1] / total_games) * 100  # Pourcentage basé sur le nombre total de parties
    return "UNKNOWN", 0

def get_top_3_champions(player_id):
    """Retourne les 3 champions les plus joués en utilisant SQLAlchemy."""
    session = SessionLocal()
    try:
        results = session.query(
            Match.champion,
            func.count(Match.champion).label("count")
        ).filter(
            Match.player_id == player_id
        ).group_by(
            Match.champion
        ).order_by(
            func.count(Match.champion).desc()
        ).limit(3).all()
        
        champions = [row.champion for row in results]
    finally:
        session.close()

    # Si moins de 3 champions, on complète avec "Unknown"
    while len(champions) < 3:
        champions.append("Unknown")
    
    return champions


def create_database():
    # Crée les tables dans PostgreSQL si elles n'existent pas déjà
    Base.metadata.create_all(bind=engine)


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

def update_recent_matches(puuid, player_id, session):
    with open(PLAYERS_FILE, "r") as file:
        allowed_players = {line.strip().split("#")[0] + "#" + line.strip().split("#")[1] for line in file.readlines()}

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
        if match_data['info']['queueId'] != 420:
            continue

        for participant in match_data['info']['participants']:
            match_player_id = f"{participant['riotIdGameName']}#{participant['riotIdTagline']}"
            if match_player_id in allowed_players:
                # Vérifier si le match existe déjà
                exist = session.query(Match).filter_by(match_id=match_id, player_id=match_player_id).first()
                if exist:
                    print(f"⚠️ Match {match_id} déjà enregistré pour {match_player_id}, on saute l'insertion.")
                    continue  # Passer si déjà présent
                new_match = Match(
                    match_id=match_id,
                    player_id=match_player_id,
                    champion=participant['championName'],
                    role=participant['teamPosition'],
                    kills=participant['kills'],
                    deaths=participant['deaths'],
                    assists=participant['assists'],
                    game_duration=match_data['info']['gameDuration'],
                    win=participant['win']
                )
                session.add(new_match)



def get_global_stats():
    session = SessionLocal()
    total_games = session.query(Match).count()
    total_wins = session.query(Match).filter(Match.win == True).count()
    total_losses = total_games - total_wins
    total_time = session.query(func.sum(Match.game_duration)).scalar() or 0
    session.close()
    global_winrate = (total_wins / total_games)*100 if total_games > 0 else 0
    return {
        "total_games": total_games,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "global_winrate": global_winrate,
        "total_time": total_time
    }

def update_players():
    create_database()  # Assurez-vous que les tables PostgreSQL existent

    with open(PLAYERS_FILE, "r") as file:
        players_list = [line.strip().split("#") for line in file.readlines()]

    session = SessionLocal()

    for game_name, tag_line in players_list:
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
        
        total_games = ranked_stats["wins"] + ranked_stats["losses"]
        winrate = (ranked_stats["wins"] / total_games * 100) if total_games > 0 else 0

        # Créer ou mettre à jour le joueur
        player_obj = session.query(Player).filter_by(player_id=f"{game_name}#{tag_line}").first()
        if not player_obj:
            player_obj = Player(player_id=f"{game_name}#{tag_line}")
        player_obj.game_name = game_name
        player_obj.tag_line = tag_line
        player_obj.puuid = puuid
        player_obj.summoner_id = summoner_info["id"]
        player_obj.summoner_level = summoner_info["summonerLevel"]
        player_obj.rank = ranked_stats["rank"]
        player_obj.tier = ranked_stats["tier"]
        player_obj.league_points = ranked_stats["leaguePoints"]
        player_obj.wins = ranked_stats["wins"]
        player_obj.losses = ranked_stats["losses"]
        player_obj.winrate = winrate
        player_obj.total_ranked_games = total_games

        session.merge(player_obj)  # merge effectue l'insert ou update

        # Insérer les matchs récents
        update_recent_matches(puuid, f"{game_name}#{tag_line}", session)

        print(f"✅ {game_name}#{tag_line} mis à jour avec succès.")

    session.commit()
    session.close()

def get_player_aggregates(player_id):
    session = SessionLocal()
    total_games = session.query(Match).filter(Match.player_id == player_id).count()
    total_wins = session.query(Match).filter(Match.player_id == player_id, Match.win == True).count()
    total_losses = total_games - total_wins

    # Calculer les agrégats
    aggregates = session.query(
        func.sum(Match.kills),
        func.sum(Match.deaths),
        func.sum(Match.assists),
        func.sum(Match.game_duration),
        func.count(func.distinct(Match.champion)),
        func.count(Match.match_id)
    ).filter(Match.player_id == player_id).one()
    session.close()

    if not aggregates or all(val is None for val in aggregates):
        return {
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

    sum_kills, sum_deaths, sum_assists, sum_time, uniq_champs, match_count = aggregates
    local_winrate = (total_wins / total_games)*100 if total_games > 0 else 0
    avg_time = sum_time / match_count if match_count > 0 else 0
    time_hours = sum_time / 3600

    return {
        "total_games": total_games,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "winrate": local_winrate,
        "kills": sum_kills or 0,
        "deaths": sum_deaths or 0,
        "assists": sum_assists or 0,
        "game_time": sum_time or 0,
        "unique_champions": uniq_champs or 0,
        "match_count": match_count or 0,
        "avg_time": avg_time,
        "time_hours": time_hours
    }


if __name__ == "__main__":
    update_players()


__all__ = ["engine", "SessionLocal", "Base", "Player", "Match", 
           "is_player_in_game", "get_player_main_role", "get_top_3_champions", 
           "create_database", "get_puuid", "get_summoner_info", "get_ranked_stats", 
           "update_recent_matches", "get_global_stats", "update_players", "get_player_aggregates"]
