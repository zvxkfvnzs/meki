import asyncio
import json
import random
import string
import time
from datetime import datetime
from urllib.parse import unquote
import cloudscraper
from utils.headers import headers_set
from utils.query import QUERY_USER, QUERY_LOGIN, MUTATION_GAME_PROCESS_TAPS_BATCH, QUERY_BOOSTER, QUERY_NEXT_BOSS
from utils.query import QUERY_TASK_VERIF, QUERY_TASK_COMPLETED, QUERY_GET_TASK, QUERY_TASK_ID, QUERY_GAME_CONFIG

url = "https://api-gw-tg.memefi.club/graphql"

# ANSI color codes
black = "\033[0;30m"
red = "\033[0;31m"
green = "\033[0;32m"
yellow = "\033[0;33m"
blue = "\033[0;34m"
magenta = "\033[0;35m"
cyan = "\033[0;36m"
white = "\033[0;37m"
reset = "\033[0m"

def log(msg, color=white):
    now = datetime.now().isoformat(" ").split(".")[0]
    print(f"{black}[{now}]{reset} {color}{msg}{reset}")

def log2(message, color):
    print(f"{color}{message}\033[0m", end="\r")

def generate_random_nonce(length=52):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

async def fetch(account_line):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with open('data.txt', 'r') as file:
                lines = file.readlines()
                raw_data = lines[account_line - 1].strip()

            tg_web_data = unquote(unquote(raw_data))
            query_id = tg_web_data.split('query_id=', maxsplit=1)[1].split('&user', maxsplit=1)[0]
            user_data = tg_web_data.split('user=', maxsplit=1)[1].split('&auth_date', maxsplit=1)[0]
            auth_date = tg_web_data.split('auth_date=', maxsplit=1)[1].split('&hash', maxsplit=1)[0]
            hash_ = tg_web_data.split('hash=', maxsplit=1)[1].split('&', maxsplit=1)[0]

            user_data_dict = json.loads(unquote(user_data))

            data = {
                "operationName": "MutationTelegramUserLogin",
                "variables": {
                    "webAppData": {
                        "auth_date": int(auth_date),
                        "hash": hash_,
                        "query_id": query_id,
                        "checkDataString": f"auth_date={auth_date}\nquery_id={query_id}\nuser={unquote(user_data)}",
                        "user": {
                            "id": user_data_dict["id"],
                            "allows_write_to_pm": user_data_dict["allows_write_to_pm"],
                            "first_name": user_data_dict["first_name"],
                            "last_name": user_data_dict["last_name"],
                            "username": user_data_dict.get("username", "Username not set"),
                            "language_code": user_data_dict["language_code"],
                            "version": "7.2",
                            "platform": "ios"
                        }
                    }
                },
                "query": QUERY_LOGIN
            }
            
            scraper = cloudscraper.create_scraper()
            response = scraper.post(url, headers=headers_set, json=data)
            json_response = response.json()
            
            if 'errors' in json_response:
                log("Error in response. Retrying...", yellow)
            else:
                access_token = json_response['data']['telegramUserLogin']['access_token']
                return access_token

        except Exception as e:
            log(f"❌ Unexpected error: {e}. Retrying...", red)

        await asyncio.sleep(5)  # Wait for 5 seconds before retrying

    log("❌ Max retries reached. Moving to next task.", red)
    return None

async def check_user(index):
    access_token = await fetch(index + 1)
    if not access_token:
        return None

    headers = headers_set.copy()
    headers['Authorization'] = f'Bearer {access_token}'
    
    json_payload = {
        "operationName": "QueryTelegramUserMe",
        "variables": {},
        "query": QUERY_USER
    }
    
    scraper = cloudscraper.create_scraper()
    response = scraper.post(url, headers=headers, json=json_payload)
    
    if response.status_code == 200:
        response_data = response.json()
        if 'errors' in response_data:
            log(f"❌ Error: Incorrect Query ID", red)
            return None
        else:
            user_data = response_data['data']['telegramUserMe']
            return user_data
    else:
        log(f"❌ Error with status {response.status_code}, retrying...", red)
        return None

async def activate_energy_recharge_booster(index):
    access_token = await fetch(index + 1)
    if not access_token:
        return None

    headers = headers_set.copy()
    headers['Authorization'] = f'Bearer {access_token}'
    
    recharge_booster_payload = {
        "operationName": "telegramGameActivateBooster",
        "variables": {"boosterType": "Recharge"},
        "query": QUERY_BOOSTER
    }
    
    scraper = cloudscraper.create_scraper()
    response = scraper.post(url, headers=headers, json=recharge_booster_payload)
    
    if response.status_code == 200:
        response_data = response.json()
        if response_data and 'data' in response_data and response_data['data'] and 'telegramGameActivateBooster' in response_data['data']:
            new_energy = response_data['data']['telegramGameActivateBooster']['currentEnergy']
            log(f"Energy recharge successful. Current energy: {new_energy}", green)
        else:
            log("❌ Unable to activate Recharge Booster: Incomplete or missing data.", red)
    else:
        log(f"❌ Error with status code {response.status_code}, retrying...", red)
        return None

async def activate_booster(index):
    access_token = await fetch(index + 1)
    if not access_token:
        return None

    headers = headers_set.copy()
    headers['Authorization'] = f'Bearer {access_token}'

    recharge_booster_payload = {
        "operationName": "telegramGameActivateBooster",
        "variables": {"boosterType": "Turbo"},
        "query": QUERY_BOOSTER
    }
    
    scraper = cloudscraper.create_scraper()
    response = scraper.post(url, headers=headers, json=recharge_booster_payload)
    
    if response.status_code == 200:
        response_data = response.json()
        current_health = response_data['data']['telegramGameActivateBooster']['currentBoss']['currentHealth']
        if current_health == 0:
            log("Boss defeated, moving to next boss...", yellow)
            await set_next_boss(index)
        else:
            initial_hit = 500000000
            for _ in range(10):
                total_hit = initial_hit
                for retry in range(3):
                    tap_payload = {
                        "operationName": "MutationGameProcessTapsBatch",
                        "variables": {
                            "payload": {
                                "nonce": generate_random_nonce(),
                                "tapsCount": int(total_hit)
                            }
                        },
                        "query": MUTATION_GAME_PROCESS_TAPS_BATCH
                    }
                    
                    tap_result = await submit_taps(index, tap_payload)
                    if tap_result is not None and isinstance(tap_result, dict) and 'data' in tap_result and 'telegramGameProcessTapsBatch' in tap_result['data']:
                        tap_data = tap_result['data']['telegramGameProcessTapsBatch']
                        if tap_data['currentBoss']['currentHealth'] == 0:
                            log("Boss defeated, moving to the next boss...", yellow)
                            await set_next_boss(index)
                        log(f"Fighting: {tap_data['coinsAmount']}, Boss ⚔️: {tap_data['currentBoss']['currentHealth']} - {tap_data['currentBoss']['maxHealth']}", green)
                    else:
                        log(f"❌ Invalid tap result: {tap_result}", red)
                        
                    await asyncio.sleep(1)
                
                if tap_result is None:
                    continue
    else:
        log(f"❌ Encountered an issue with status code {response.status_code}, try again...", red)
    
    log("Turbo Boost activation process completed", cyan)

async def submit_taps(index, json_payload):
    try:
        access_token = await fetch(index + 1)
        if not access_token:
            return None

        headers = headers_set.copy()
        headers['Authorization'] = f'Bearer {access_token}'

        scraper = cloudscraper.create_scraper()
        response = scraper.post(url, headers=headers, json=json_payload)
        
        if response.status_code == 200:
            response_data = response.json()
            return response_data
        else:
            log(f"❌ Failed with status {response.status_code}, try again...", red)
            return None
    except Exception as e:
        log(f"Error: {e}", red)
        return None

async def set_next_boss(index):
    access_token = await fetch(index + 1)
    if not access_token:
        return None

    headers = headers_set.copy()
    headers['Authorization'] = f'Bearer {access_token}'

    json_payload = {
        "operationName": "telegramGameSetNextBoss",
        "variables": {},
        "query": QUERY_NEXT_BOSS
    }
    
    scraper = cloudscraper.create_scraper()
    response = scraper.post(url, headers=headers, json=json_payload)
    
    if response.status_code == 200:
        response_data = response.json()
        if response_data and 'data' in response_data:
            log("Next boss has been successfully set!", green)
            return response_data
        else:
            log("❌ Unable to set next boss: Data is incomplete or not available.", red)
            return None
    else:
        log(f"❌ Encountered an issue with status code {response.status_code}, try again...", red)
        return None

async def check_stat(index):
    access_token = await fetch(index + 1)
    if not access_token:
        return None

    headers = headers_set.copy()
    headers['Authorization'] = f'Bearer {access_token}'
    
    json_payload = {
        "operationName": "QUERY_GAME_CONFIG",
        "variables": {},
        "query": QUERY_GAME_CONFIG
    }
    
    scraper = cloudscraper.create_scraper()
    response = scraper.post(url, headers=headers, json=json_payload)
    
    if response.status_code == 200:
        response_data = response.json()
        if 'errors' in response_data:
            return None
        else:
            user_data = response_data['data']['telegramGameGetConfig']
            return user_data
    else:
        log(f"❌ Error with status {response.status_code}, try again...", red)
        return None

async def main():
    welcome = """
                        ██╗  ██╗██╗   ██╗██████╗ ██████╗  █████╗ 
                        ██║ ██╔╝██║   ██║██╔══██╗██╔══██╗██╔══██╗
                        █████╔╝ ██║   ██║██████╔╝██████╔╝███████║
                        ██╔═██╗ ██║   ██║██╔═══╝ ██╔══██╗██╔══██║
                        ██║  ██╗╚██████╔╝██║     ██║  ██║██║  ██║
                        ╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝                                            
"""
    print(blue + welcome.center(3) + reset)
    print(cyan + "=========================================".center(90) + reset)
    print(magenta + "=========> Bot by Kupra <=========".center(90) + reset)
    print(cyan + "=========================================".center(90) + reset)

    while True:
        with open('data.txt', 'r') as file:
            account_lines = file.readlines()
            
            accounts = []

            for index, line in enumerate(account_lines):
                result = await check_user(index)
                if result is not None:
                    first_name = result.get('firstName', 'Unknown')
                    last_name = result.get('lastName', 'Unknown')
                    accounts.append((index, result, first_name, last_name))
                else:
                    log(f"❌ Account {index + 1}: Invalid token or an error occurred", red)


            for index, result, first_name, last_name in accounts:
                try:  # Tambahkan blok try di sini
                    headers = {'Authorization': f'Bearer {result}'}
                    should_continue_to_next_account = False
                    stat_result = await check_stat(index)

                    if stat_result is not None:
                        user_data = stat_result
                        log("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~", cyan)
                        log(f"Account {index + 1} : {first_name} {last_name}", cyan)
                        log(f"Balance 💎 {user_data.get('coinsAmount', 'Unknown')} Energy : {user_data.get('currentEnergy', 'Unknown')} / {user_data.get('maxEnergy', 'Unknown')}", green)
                        log(f"Boss LV {user_data['currentBoss'].get('level', 'Unknown')} ❤️  {user_data['currentBoss'].get('currentHealth', 'Unknown')} - {user_data['currentBoss'].get('maxHealth', 'Unknown')}", green)
                        log(f"Turbo {user_data['freeBoosts'].get('currentTurboAmount', 'Unknown')} Recharge {user_data['freeBoosts'].get('currentRefillEnergyAmount', 'Unknown')}", green)
                    else:
                        log(f"⚠️ Warning: Unable to retrieve user data for account {index}. Moving to next account.", red)
                        continue
                    if 'currentBoss' in user_data:
                        lv_boss = user_data['currentBoss']['level']
                        mau_boss = user_data['currentBoss']['currentHealth']
                        if lv_boss >= 14 and mau_boss == 0:
                            log(f"=================== {first_name} {last_name} FINISHED ====================", magenta)
                            should_continue_to_next_account = True
                        if mau_boss == 0:
                            log("Boss defeated, moving to next boss...", yellow)
                            await set_next_boss(index)
                    log("Starting tap", green)

                    energy_now = user_data['currentEnergy']
                    recharge_available = user_data['freeBoosts']['currentRefillEnergyAmount']
                    if not should_continue_to_next_account:
                        while energy_now > 500 or recharge_available > 0:
                            total_tap = random.randint(100, 200)
                            tap_payload = {
                                "operationName": "MutationGameProcessTapsBatch",
                                "variables": {
                                    "payload": {
                                        "nonce": generate_random_nonce(),
                                        "tapsCount": total_tap
                                    }
                                },
                                "query": MUTATION_GAME_PROCESS_TAPS_BATCH
                            }

                            tap_result = await submit_taps(index, tap_payload)
                            if tap_result is not None:
                                user_data = await check_stat(index)
                                energy_now = user_data['currentEnergy']
                                recharge_available = user_data['freeBoosts']['currentRefillEnergyAmount']
                                log(f"Tapping Memefi2 : Balance 💎 {user_data['coinsAmount']} Energy : {energy_now} / {user_data['maxEnergy']}", green)
                            else:
                                log(f"❌ Error with status {tap_result}, retrying...", red)

                            if energy_now < 500:
                                if recharge_available > 0:
                                    log("Out of energy, activating Recharge...", yellow)
                                    await activate_energy_recharge_booster(index)
                                    user_data = await check_stat(index)
                                    energy_now = user_data['currentEnergy']
                                    recharge_available = user_data['freeBoosts']['currentRefillEnergyAmount']
                                else:
                                    log("Energy below 500 and no Recharge left, moving to next account.", yellow)
                                    break

                            if user_data['freeBoosts']['currentTurboAmount'] > 0:
                                await activate_booster(index)
                    if should_continue_to_next_account:
                        continue
                except Exception as e:  # Tangkap kesalahan di sini
                    log(f"❌ Error processing account {index + 1}: {e}", red)
                    continue  # Lanjutkan ke akun berikutnya
        log("=== [ ALL ACCOUNTS PROCESSED ] ===", magenta)
        animate_energy_recharge(10)

def animate_energy_recharge(duration=1):
    frames = ["|", "/", "-", "\\"]
    end_time = time.time() + duration
    while time.time() < end_time:
        remaining_time = int(end_time - time.time())
        for frame in frames:
            log2(f"Recharging energy {frame} - {remaining_time} seconds remaining", cyan)
            time.sleep(0.25)
    log2("Energy recharge complete.", green)

if __name__ == "__main__":
    asyncio.run(main())