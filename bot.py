import os
import random
from discord.ext import commands
from tda import auth, client
import json
from dotenv import load_dotenv

load_dotenv()

token_path = 'token.json'
api_key = os.getenv('API_KEY')
redirect_uri = 'https://localhost'

try:
    c = auth.client_from_token_file(token_path, api_key)
except FileNotFoundError:
    print("Token file not found")

r = c.get_price_history('AAPL',
        period_type=client.Client.PriceHistory.PeriodType.YEAR,
        period=client.Client.PriceHistory.Period.TWENTY_YEARS,
        frequency_type=client.Client.PriceHistory.FrequencyType.DAILY,
        frequency=client.Client.PriceHistory.Frequency.DAILY)

assert r.status_code == 200, r.raise_for_status()
print(json.dumps(r.json(), indent=4))
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