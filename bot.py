import os
import random
from discord.ext import commands
from tda import auth
from dotenv import load_dotenv
import logging

#logging
logging.basicConfig(filename='bot.log', filemode='w', level=logging.INFO)

load_dotenv()

#const
token_path = 'token.json'
api_key = os.getenv('API_KEY')
TOKEN = os.getenv('DISCORD_TOKEN')

#oauth
try:
    c = auth.client_from_token_file(token_path, api_key)
except FileNotFoundError:
    print("Token file not found")

TOKEN = os.getenv('DISCORD_TOKEN')

bot = commands.Bot(command_prefix='!', help="sdf")

@bot.command(name='99')
async def nine_nine(ctx):
    brooklyn_99_quotes = [
        'I\'m the human form of the 💯 emoji.',
        'Bingpot!',
        (
            'Cool. Cool cool cool cool cool cool cool, '
            'no doubt no doubt no doubt no doubt.'
        ),
    ]

    response = random.choice(brooklyn_99_quotes)
    await ctx.send(response)

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    
bot.run(TOKEN)