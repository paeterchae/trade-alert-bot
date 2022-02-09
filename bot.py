import os
from discord.ext import commands
from discord import Embed
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
COLOR = 0x50f276

def oauth(TOKEN_PATH, API_KEY):
    try:
        return auth.client_from_token_file(TOKEN_PATH, API_KEY)
    except FileNotFoundError:
        print("Token file not found")

def filter(msg):
    msg_type = msg["content"][0]["MESSAGE_TYPE"]
    try:
        msg_data = xmltodict.parse(msg["content"][0]["MESSAGE_DATA"])
    except:
        pass
    if msg_type == "SUBSCRIBED":
        return format(Embed(title="Trade Alert Bot Activated"))
        #return "account stream has begun"
    elif msg_type == "OrderEntryRequest":
        order = msg_data["OrderEntryRequestMessage"]["Order"]
        option = order["Security"]["Symbol"].split("_")
        exp = option[1][:6]
        cp = "Call" if option[1][6] == "C" else "Put"
        order_type = order["OrderType"]
        e = Embed(title="{} {} {} {}/{} {}".format(order["OrderInstructions"], option[0], option[1][7:], exp[:2], exp[2:4], cp), description = "Order Placed")
        e.add_field(name="Order Type", value=order_type, inline=True)
        if order_type == "Limit":
            e.add_field(name="Limit Price", value=order["OrderPricing"]["Limit"], inline=True)
        e.add_field(name="Size", value=order["OriginalQuantity"])
        return format(e)
    elif msg_type == "UROUT":
        order = msg_data["UROUTMessage"]["Order"]
        option = order["Security"]["Symbol"].split("_")
        exp = option[1][:6]
        cp = "Call" if option[1][6] == "C" else "Put"
        e = Embed(title="Order Cancelled", description = "{} {} {} {}/{} {}".format(order["OrderInstructions"], option[0], option[1][7:], exp[:2], exp[2:4], cp))
        return format(e)
    else:
        #return json.dumps(xmltodict.parse(msg["content"][0]["MESSAGE_DATA"]), indent=4)
        return Embed.Empty
        #return ""

def format(e=Embed):
    e.color=COLOR
    e.set_author(name="Highstrike", url="https://highstrike.com/",
                icon_url="https://www.highstriketrading.com/hosted/images/78/b23e71dc0b420c80120008ffeb837d/Circle-Logo.png")
    e.set_thumbnail(url="https://www.highstriketrading.com/hosted/images/78/b23e71dc0b420c80120008ffeb837d/Circle-Logo.png")
    e.set_footer(text="Highstrike Signals")
    return e

bot = commands.Bot(command_prefix='!')

streaming = True

@bot.command(name="alert", help="Begins streaming from account")
async def read_stream(ctx):
    stream_client = StreamClient(oauth(TOKEN_PATH, API_KEY))
    await stream_client.login()
    await stream_client.quality_of_service(StreamClient.QOSLevel.EXPRESS)
    
    async def send_response(msg):
        await ctx.send(embed=filter(msg))
        #await ctx.send(filter(msg))

    stream_client.add_account_activity_handler(send_response)
    await stream_client.account_activity_sub()
 
    while streaming:
        await stream_client.handle_message()

@bot.command(name="stop", help="Stops streaming from account")
async def unsub(ctx):
    global streaming
    streaming = False

    stream_client = StreamClient(oauth(TOKEN_PATH, API_KEY))
    await stream_client.login()
    await stream_client.quality_of_service(StreamClient.QOSLevel.EXPRESS)

    await stream_client.account_activity_unsubs()

    streaming = True

    await ctx.send(embed=format(Embed(title="Trade Alert Bot Deactivated")))

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')

bot.run(TOKEN)