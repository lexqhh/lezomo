import requests
import os
from dotenv import load_dotenv

# Charger la clé API Riot depuis .env
load_dotenv()
API_KEY = os.getenv("RIOT_API_KEY")

# Match ID et PUUID du joueur à tester (remplace par un vrai match ID et PUUID)
TEST_MATCH_ID = "EUW1_7335263176"  # 🔴 MET TON VRAI MATCH ID ICI
TEST_PLAYER_PUUID = "-nHTOcvqb6tSttfhjsI-aVgaVwN7lf8GhYHc8elGOTgR7v6aEyeNe6Wx4LJKEPrX0OSSx-9jUJ4v7w"  # 🔴 MET TON VRAI PUUID ICI

# URL de l'API pour récupérer les infos du match
MATCH_URL = f"https://europe.api.riotgames.com/lol/match/v5/matches/{TEST_MATCH_ID}"
HEADERS = {"X-Riot-Token": API_KEY}

# Faire la requête à l’API Riot
response = requests.get(MATCH_URL, headers=HEADERS)

if response.status_code == 200:
    match_data = response.json()

    # Étape 1 : Trouver l’équipe du joueur
    player_team_id = None
    for participant in match_data["info"]["participants"]:
        if participant["puuid"] == TEST_PLAYER_PUUID:
            player_team_id = participant["teamId"]
            break  # On a trouvé l'équipe du joueur

    if player_team_id is None:
        print("❌ Impossible de trouver le joueur dans ce match.")
    else:
        print(f"✅ Le joueur est dans l'équipe {player_team_id}.")

        # Étape 2 : Vérifier si son équipe a pris le premier dragon
        team_with_first_dragon = None
        for team in match_data["info"]["teams"]:
            if team["objectives"]["dragon"]["first"]:  # Si cette équipe a pris le premier dragon
                team_with_first_dragon = team["teamId"]

        if team_with_first_dragon is not None:
            print(f"🏆 L'équipe {team_with_first_dragon} a pris le premier dragon.")

            # Étape 3 : Vérifier si le joueur était dans cette équipe
            if player_team_id == team_with_first_dragon:
                print("✅ Le joueur était dans l’équipe qui a pris le premier dragon !")
            else:
                print("❌ Le joueur n’était PAS dans l’équipe qui a pris le premier dragon.")
        else:
            print("❌ Aucune équipe n'a pris le premier dragon dans ce match.")

else:
    print(f"❌ Erreur API : {response.status_code} - {response.text}")
