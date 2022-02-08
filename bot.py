import os
from discord.ext import commands
from tda import auth
from dotenv import load_dotenv
import logging
from tda.streaming import StreamClient
import json
import xmltodict

#logging
logging.basicConfig(format="%(asctime)s %(levelname)s:%(name)s: %(message)s", datefmt="%H:%M:%S",
                    filename='bot.log', filemode='w', level=logging.INFO)

load_dotenv()

#const
TOKEN_PATH = 'token.json'
API_KEY = os.getenv('API_KEY')
TOKEN = os.getenv('DISCORD_TOKEN')
ACCOUNT_ID = os.getenv("ACCOUNT_ID")

def oauth(TOKEN_PATH, API_KEY):
    try:
        client = auth.client_from_token_file(TOKEN_PATH, API_KEY)
        return client
    except FileNotFoundError:
        print("Token file not found")

def filter(msg):
    if msg["content"][0]["MESSAGE_TYPE"] == "SUBSCRIBED":
        return "Account stream has begun"
    else:
        return json.dumps(xmltodict.parse(msg["content"][0]["MESSAGE_DATA"]), indent=4)

bot = commands.Bot(command_prefix='!')

@bot.command(name="alert", help="Begins streaming from account")
async def read_stream(ctx):
    stream_client = StreamClient(oauth(TOKEN_PATH, API_KEY))
    await stream_client.login()
    await stream_client.quality_of_service(StreamClient.QOSLevel.EXPRESS)
    
    async def send_response(msg):
        await ctx.send(filter(msg))

    stream_client.add_account_activity_handler(send_response)
    await stream_client.account_activity_sub()
 
    while True:
        await stream_client.handle_message()

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')

bot.run(TOKEN)