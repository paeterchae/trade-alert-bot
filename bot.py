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
ACCOUNT_ID = os.getenv("ACCOUNT_ID")
COLOR = 0x50f276

client = auth.client_from_token_file(TOKEN_PATH, API_KEY)

curr_positions = {}

def parser(msg_data, msg_type):
    order = msg_data[msg_type + "Message"]["Order"]
    option = order["Security"]["Symbol"].split("_")
    ticker = option[0]
    strike = option[1][7:]
    exp = option[1][:6][:2] + "/" + option[1][:6][2:4]
    cp = "Call" if option[1][6] == "C" else "Put"
    order_type = order["OrderType"]
    bs = order["OrderInstructions"]
    acc_value = client.get_account(ACCOUNT_ID).json()["securitiesAccount"]["initialBalances"]["accountValue"]
    num_contracts = order["OriginalQuantity"]
    limit_price = None if order_type != "Limit" else order["OrderPricing"]["Limit"]
    return bs, ticker, strike, exp, cp, order_type, acc_value, num_contracts, limit_price

def filter(msg):
    msg_type = msg["content"][0]["MESSAGE_TYPE"]
    try:
        msg_data = xmltodict.parse(msg["content"][0]["MESSAGE_DATA"])
        bs, ticker, strike, exp, cp, order_type, acc_value, num_contracts, limit_price = parser(msg_data, msg_type)
    except:
        pass
    if msg_type == "SUBSCRIBED":
        return format(Embed(title="Trade Alert Bot Activated"))
        #return "account stream has begun"
    elif msg_type == "OrderEntryRequest":
        e = Embed(title="{} {} {} {} {}".format(bs, ticker, strike, exp, cp), description = "Order Placed")
        e.add_field(name="Order Type", value=order_type, inline=True)
        #position size only visible if limit order
        if order_type == "Limit":
            e.add_field(name="Limit Price", value=limit_price, inline=True)
            e.add_field(name="Position Size", value=str(int(float(limit_price) * 10000.0 * int(num_contracts) / float(acc_value))) + "%")
        return format(e)
    elif msg_type == "UROUT":
        e = Embed(title="Order Cancelled", description = "{} {} {} {} {}".format(bs, ticker, strike, exp, cp))
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
    stream_client = StreamClient(client, account_id=ACCOUNT_ID)
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

    stream_client = StreamClient(client, account_id=ACCOUNT_ID)
    await stream_client.login()
    await stream_client.quality_of_service(StreamClient.QOSLevel.EXPRESS)

    await stream_client.account_activity_unsubs()

    streaming = True

    await ctx.send(embed=format(Embed(title="Trade Alert Bot Deactivated")))

@bot.command(name="acc", help="acc")
async def unsub(ctx):
    r = client.get_account(ACCOUNT_ID)
    #await ctx.send(r.json()["securitiesAccount"]["initialBalances"]["accountValue"])
    await ctx.send(json.dumps(r.json(), indent=4))
    #await ctx.send(r.json().keys())


@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')

bot.run(TOKEN)