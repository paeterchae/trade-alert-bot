import os
from discord.ext import commands, tasks
from discord import Embed
from tda import auth
from dotenv import load_dotenv
import logging
from tda.streaming import StreamClient
from tda.client import Client
import json
import xmltodict
from deepdiff import DeepDiff

#logging
logging.basicConfig(format="%(asctime)s %(levelname)s:%(name)s: %(message)s", datefmt="%H:%M:%S",
                    filename='bot.log', filemode='w', level=logging.INFO)

load_dotenv()

#const
TOKEN_PATH = 'test_token.json'
API_KEY = os.getenv('API_KEY')
TOKEN = os.getenv('DISCORD_TOKEN')
ACCOUNT_ID = os.getenv('ACCOUNT_ID')
CHANNEL_ID = os.getenv('CHANNEL_ID')

client = auth.client_from_token_file(TOKEN_PATH, API_KEY)

#global variables
curr_positions = []
update = False
streaming = True

def parser(msg_data, msg_type):
    order = msg_data[msg_type + "Message"]["Order"]
    symbol = order["Security"]["Symbol"]
    option = symbol.split("_")
    ticker = option[0]
    strike = option[1][7:]
    exp = option[1][:6][:2] + "/" + option[1][:6][2:4] + "/" + option[1][:6][4:6]
    cp = "Call" if option[1][6] == "C" else "Put"
    order_type = order["OrderType"]
    bs = order["OrderInstructions"]
    num_contracts = int(order["OriginalQuantity"])
    if bs == "Sell":
        bs = "Trim" if curr_positions[symbol] - num_contracts > 0 else "Exit"
    acc_value = client.get_account(ACCOUNT_ID).json()["securitiesAccount"]["currentBalances"]["liquidationValue"]
    limit_price = None if order_type != "Limit" else "{:0.2f}".format(float(order["OrderPricing"]["Limit"]))
    bid = "{:0.2f}".format(float(order["OrderPricing"]["Bid"]))
    ask = "{:0.2f}".format(float(order["OrderPricing"]["Ask"]))
    return bs, ticker, strike, exp, cp, order_type, acc_value, num_contracts, limit_price, symbol, bid, ask
        
def filter(msg):
    msg_type = msg["content"][0]["MESSAGE_TYPE"]
    if msg_type == "SUBSCRIBED":
        return format(Embed(title="Trade Alert Bot Activated"))
    elif msg_type == "TransactionTrade":
        return None
    else:
        msg_data = xmltodict.parse(msg["content"][0]["MESSAGE_DATA"])
        bs, ticker, strike, exp, cp, order_type, acc_value, num_contracts, limit_price, symbol, bid, ask = parser(msg_data, msg_type)
        e = Embed(title="{} {} {} {} {}".format(bs, ticker, strike, exp, cp))
        e.add_field(name="Order Type", value=order_type, inline=True)
        #position size only visible if limit order
        if order_type == "Limit":
            e.add_field(name="Limit Price", value=limit_price, inline=True)
            e.add_field(name="Position Size", value=str(int(float(limit_price) * 10000.0 * num_contracts / float(acc_value))) + "%")
        elif order_type == "Market":
            e.add_field(name="Bid", value= bid, inline=True)
            e.add_field(name="Ask", value=ask, inline=True)
            e.add_field(name="Position Size", value=str(int((float(bid)+float(ask))/2 * 10000.0 * num_contracts / float(acc_value))) + "%")
        if msg_type == "OrderEntryRequest":
            update_positions(bs, symbol, num_contracts)
            e.description = "Order Placed"
            e.color = 0x50f276 if (bs == "Buy") else 0xFF0000
            return format(e)
        elif msg_type == "OrderCancelReplaceRequest":
            e.color = 0x50f276 if (bs == "Buy") else 0xFF0000
            e.description = "Replacement Order Placed"
            return format(e)
        elif msg_type == "UROUT":
            return format(Embed(title="Order Cancelled", description = "{} {} {} {} {}".format(bs, ticker, strike, exp, cp), color=0xFF8B00))
        else:
            return None

def format(e=Embed):
    e.set_author(name="Highstrike", url="https://highstrike.com/",
                icon_url="https://www.highstriketrading.com/hosted/images/78/b23e71dc0b420c80120008ffeb837d/Circle-Logo.png")
    e.set_thumbnail(url="https://www.highstriketrading.com/hosted/images/78/b23e71dc0b420c80120008ffeb837d/Circle-Logo.png")
    e.set_footer(text="Highstrike Signals")
    return e

bot = commands.Bot(command_prefix='!')

@bot.command(name="alert", help="Begins streaming from account")
async def read_stream(ctx):
    stream_client = StreamClient(client, account_id=ACCOUNT_ID)
    #stream_client = StreamClient(client)
    await stream_client.login()
    await stream_client.quality_of_service(StreamClient.QOSLevel.EXPRESS)
    
    async def send_response(msg):
        if isinstance(filter(msg), Embed):
            await ctx.send(embed=filter(msg))
        elif filter(msg) != None:
            try:
                await ctx.send(filter(msg))
            except:
                with open("error.log", "a+") as file:
                    file.write(filter(msg))
                    print(filter(msg))
                file.close()

    stream_client.add_account_activity_handler(send_response)
    await stream_client.account_activity_sub()
 
    while streaming:
        await stream_client.handle_message()

@bot.command(name="stop", help="Stops streaming from account")
async def unsub(ctx):
    global streaming
    streaming = False

    stream_client = StreamClient(client, account_id=ACCOUNT_ID)
    #stream_client = StreamClient(client)
    await stream_client.login()
    await stream_client.quality_of_service(StreamClient.QOSLevel.EXPRESS)

    await stream_client.account_activity_unsubs()

    streaming = True

    await ctx.send(embed=format(Embed(title="Trade Alert Bot Deactivated")))

@bot.command(name="acc", help="acc")
async def acc(ctx):
    r = client.get_account(ACCOUNT_ID)
    await ctx.send(json.dumps(r.json(), indent=4))
    slow_count.stop()

@bot.command(name="pos", help="pos")
async def pos(ctx):
    r = client.get_account(ACCOUNT_ID, fields=Client.Account.Fields.POSITIONS)
    try:
        with open("position.log", "a+") as file:
            file.write(json.dumps(r.json()["securitiesAccount"]["positions"], indent=4))
        file.close()
        await ctx.send(json.dumps(r.json()["securitiesAccount"]["positions"], indent=4))
    except KeyError:
        await ctx.send("No current positions")

@bot.command(name="status", help="status")
async def status(ctx):
    await ctx.send(curr_positions)
    if not slow_count.is_running():
        slow_count.start()
    else:
        print("process already started")

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    update_positions.start()

@tasks.loop(seconds=1)
async def slow_count():
    print(slow_count.current_loop)
    channel = bot.get_channel(int(CHANNEL_ID))
    await channel.send(slow_count.current_loop)

async def order_fill():
    #update curr_positions here
    channel = bot.get_channel(int(CHANNEL_ID))
    await channel.send("Filled")

#figure out difference HERE
@tasks.loop(seconds=1)
async def update_positions():
    global curr_positions
    global update
    try:
        new_positions = client.get_account(ACCOUNT_ID, fields=Client.Account.Fields.POSITIONS).json()["securitiesAccount"]["positions"]
        #new positions taken or deleted
        """if len(curr_positions) != len(new_positions):
            order_fill(new_positions, 0)
            update = True
        else:
            #additions or subtractions to existing positions
            for old, new in zip(curr_positions, new_positions):
                if old["longQuantity"] != new["longQuantity"] or old["shortQuantity"] != new["shortQuantity"]:
                    update = True

                    break"""
        
        #filter(lambda old: old["instrument"]["symbol"], curr_positions)

        for i, (old, new) in enumerate(zip(curr_positions, new_positions)):
            pass
            #new purchase (len 0 v len 2), adjust quant of existing position (same len), deleted position (len 2 v len 0)
        for i, pos in enumerate(new_positions):
            symbol = pos["instrument"]["symbol"]
            amt = pos["longQuantity"]
            if curr_positions.get(symbol) == None or amt > curr_positions[symbol]:
                await order_fill(new_positions, i, "Buy")
            elif amt < curr_positions[symbol]:
                await order_fill(new_positions, i, "Sell")

    except KeyError:
        if curr_positions != []:
            curr_positions = []
            update = True
    if update:
        await order_fill()
        update = False

test=[
    {
        "shortQuantity": 0.0,
        "averagePrice": 3.02,
        "currentDayCost": 302.0,
        "currentDayProfitLoss": -0.5,
        "currentDayProfitLossPercentage": -0.17,
        "longQuantity": 5.0,
        "settledLongQuantity": 0.0,
        "settledShortQuantity": 0.0,
        "instrument": {
            "assetType": "OPTION",
            "cusip": "0QQQ..D120370000",
            "symbol": "QQQ_040122C370",
            "description": "QQQ Apr 01 2022 370.0 Call",
            "type": "VANILLA",
            "putCall": "CALL",
            "underlyingSymbol": "QQQ"
        },
        "marketValue": 301.5,
        "maintenanceRequirement": 0.0,
        "previousSessionLongQuantity": 0.0
    },
    {
        "shortQuantity": 0.0,
        "averagePrice": 2.32,
        "currentDayCost": 232.0,
        "currentDayProfitLoss": -3.5,
        "currentDayProfitLossPercentage": -1.51,
        "longQuantity": 1.0,
        "settledLongQuantity": 0.0,
        "settledShortQuantity": 0.0,
        "instrument": {
            "assetType": "OPTION",
            "cusip": "0SPY..D120461000",
            "symbol": "SPY_040122C461",
            "description": "SPY Apr 01 2022 461.0 Call",
            "type": "VANILLA",
            "putCall": "CALL",
            "underlyingSymbol": "SPY"
        },
        "marketValue": 228.5,
        "maintenanceRequirement": 0.0,
        "previousSessionLongQuantity": 0.0
    }
]

test2=[
    {
        "shortQuantity": 0.0,
        "averagePrice": 3.02,
        "currentDayCost": 302.0,
        "currentDayProfitLoss": -0.5,
        "currentDayProfitLossPercentage": -0.17,
        "longQuantity": 1.0,
        "settledLongQuantity": 0.0,
        "settledShortQuantity": 0.0,
        "instrument": {
            "assetType": "OPTION",
            "cusip": "0QQQ..D120370000",
            "symbol": "QQQ_040122C370",
            "description": "QQQ Apr 01 2022 370.0 Call",
            "type": "VANILLA",
            "putCall": "CALL",
            "underlyingSymbol": "QQQ"
        },
        "marketValue": 301.5,
        "maintenanceRequirement": 0.0,
        "previousSessionLongQuantity": 0.0
    },
    {
        "shortQuantity": 0.0,
        "averagePrice": 2.32,
        "currentDayCost": 232.0,
        "currentDayProfitLoss": -3.5,
        "currentDayProfitLossPercentage": -1.51,
        "longQuantity": 3.0,
        "settledLongQuantity": 0.0,
        "settledShortQuantity": 0.0,
        "instrument": {
            "assetType": "OPTION",
            "cusip": "0SPY..D120461000",
            "symbol": "SPY_040122C461",
            "description": "SPY Apr 01 2022 461.0 Call",
            "type": "VANILLA",
            "putCall": "CALL",
            "underlyingSymbol": "SPY"
        },
        "marketValue": 228.5,
        "maintenanceRequirement": 0.0,
        "previousSessionLongQuantity": 0.0
    },
    {
        "shortQuantity": 0.0,
        "averagePrice": 2.32,
        "currentDayCost": 232.0,
        "currentDayProfitLoss": -3.5,
        "currentDayProfitLossPercentage": -1.51,
        "longQuantity": 3.0,
        "settledLongQuantity": 0.0,
        "settledShortQuantity": 0.0,
        "instrument": {
            "assetType": "OPTION",
            "cusip": "0SPY..D120461000",
            "symbol": "SPY_040122C461",
            "description": "SPYD Apr 01 2022 461.0 Call",
            "type": "VANILLA",
            "putCall": "CALL",
            "underlyingSymbol": "SPY"
        },
        "marketValue": 228.5,
        "maintenanceRequirement": 0.0,
        "previousSessionLongQuantity": 0.0
    }
]

print(DeepDiff(test,test2))

bot.run(TOKEN)