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
import copy

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

#initializing global variables
curr_positions = {}
try:
    active_positions = client.get_account(ACCOUNT_ID, fields=Client.Account.Fields.POSITIONS).json()["securitiesAccount"]["positions"]
    for pos in active_positions:
        symbol = pos["instrument"]["symbol"]
        curr_positions[symbol] = pos
except KeyError:
    pass

open_requests = len(client.get_orders_by_path(ACCOUNT_ID,status=Client.Order.Status.AWAITING_CONDITION).json())
open_requests += len(client.get_orders_by_path(ACCOUNT_ID,status=Client.Order.Status.QUEUED).json())
open_requests += len(client.get_orders_by_path(ACCOUNT_ID,status=Client.Order.Status.PENDING_ACTIVATION).json())

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
        if curr_positions[symbol]["longQuantity"] - num_contracts > 0:
            bs = "Trim"
        else:
            bs = "Exit" if curr_positions[symbol]["currentDayProfitLossPercentage"] > 0 else "Cut"
    acc_value = client.get_account(ACCOUNT_ID).json()["securitiesAccount"]["currentBalances"]["liquidationValue"]
    limit_price = None if order_type != "Limit" else "{:0.2f}".format(float(order["OrderPricing"]["Limit"]))
    bid = "{:0.2f}".format(float(order["OrderPricing"]["Bid"]))
    ask = "{:0.2f}".format(float(order["OrderPricing"]["Ask"]))
    return bs, ticker, strike, exp, cp, order_type, acc_value, num_contracts, limit_price, bid, ask, symbol
        
def filter(msg):
    msg_type = msg["content"][0]["MESSAGE_TYPE"]
    if msg_type == "SUBSCRIBED":
        return format(Embed(title="Trade Alert Bot Activated"))
    elif msg_type == "TransactionTrade":
        return None
    else:
        msg_data = xmltodict.parse(msg["content"][0]["MESSAGE_DATA"])
        bs, ticker, strike, exp, cp, order_type, acc_value, num_contracts, limit_price, bid, ask, symbol = parser(msg_data, msg_type)
        if bs == "Trim":
            trim_percentage = str(num_contracts/curr_positions[symbol]["longQuantity"] * 100.0) + "%"
            e = Embed(title="{} {} {} {} {} {}".format(bs, trim_percentage, ticker, strike, exp, cp))  
        else:
            e = Embed(title="{} {} {} {} {}".format(bs, ticker, strike, exp, cp))
        e.add_field(name="Order Type", value=order_type, inline=True)
        e.color = 0xFFFF00
        #position size only visible if limit order
        if order_type == "Limit":
            e.add_field(name="Limit Price", value=limit_price, inline=True)
            if bs == "Buy":
                e.add_field(name="Position Size", value=str(int(float(limit_price) * 10000.0 * num_contracts / float(acc_value))) + "%")
        elif order_type == "Market":
            e.add_field(name="Bid", value= bid, inline=True)
            e.add_field(name="Ask", value=ask, inline=True)
            if bs == "Buy":
                e.add_field(name="Position Size", value=str(int((float(bid)+float(ask))/2 * 10000.0 * num_contracts / float(acc_value))) + "%")
        if msg_type == "OrderEntryRequest":
            open_requests += 1
            if not update_positions.is_running():
                update_positions.start()
            e.description = "Order Placed"
            return format(e)
        elif msg_type == "OrderCancelReplaceRequest":
            open_requests += 1
            if not update_positions.is_running():
                update_positions.start()
            e.description = "Replacement Order Placed"
            return format(e)
        elif msg_type == "UROUT":
            open_requests -= 1
            if open_requests == 0 and update_positions.is_running():
                update_positions.stop()
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
    global streaming
    streaming = False

    stream_client = StreamClient(client)
    await stream_client.login()
    await stream_client.quality_of_service(StreamClient.QOSLevel.EXPRESS)
    
    async def send_response(msg):
        if filter(msg) != None:
            await ctx.send(embed=filter(msg))

    stream_client.add_account_activity_handler(send_response)
    await stream_client.account_activity_sub()

    streaming = True
 
    while streaming:
        await stream_client.handle_message()

@bot.command(name="stop", help="Stops streaming from account")
async def unsub(ctx):
    global streaming
    streaming = False

    stream_client = StreamClient(client)
    await stream_client.login()
    await stream_client.quality_of_service(StreamClient.QOSLevel.EXPRESS)

    await stream_client.account_activity_unsubs()

    streaming = True

    await ctx.send(embed=format(Embed(title="Trade Alert Bot Deactivated")))

@bot.command(name="acc", help="Displays account information")
async def acc(ctx):
    r = client.get_account(ACCOUNT_ID)
    await ctx.send(json.dumps(r.json(), indent=4))

@bot.command(name="pos", help="Displays active positions")
async def status(ctx):
    await ctx.send(curr_positions)

async def order_fill(order, action, acc_value, prev=None):
    if order["instrument"]["assetType"] == "OPTION":
        symbol = order["instrument"]["symbol"]
        option = symbol.split("_")
        ticker = option[0]
        strike = option[1][7:]
        exp = option[1][:6][:2] + "/" + option[1][:6][2:4] + "/" + option[1][:6][4:6]
        cp = "Call" if option[1][6] == "C" else "Put"
        if action == "Trim":
            trim_percentage = str((1.0 - order["longQuantity"]/prev["longQuantity"]) * 100.0) + "%"
            e = Embed(title="{} {} {} {} {} {}".format(action, trim_percentage, ticker, strike, exp, cp))
            e.add_field(name="Position Left", value=str(order["marketValue"] / acc_value * 100.0) + "%", inline=True)
        else:
            e = Embed(title="{} {} {} {} {}".format(action, ticker, strike, exp, cp))
        e.add_field(name="Average Cost", value=str(order["averagePrice"]))
        e.add_field(name="Market Price", value=str(order["marketValue"]/order["longQuantity"]/100.0))
        e.add_field(name="P/L", value=str(order["currentDayProfitLossPercentage"])+"%")
        if action == "Buy":
            e.add_field(name="Total Position", value=str(order["marketValue"] / acc_value * 100.0) + "%", inline=True)
        e.color = 0x50f276 if action == "Buy" else 0xFF0000
        e.description = "Order Filled"
        channel = bot.get_channel(int(CHANNEL_ID))
        await channel.send(embed=format(e))

@tasks.loop(seconds=1)
async def update_positions():
    global curr_positions
    tmp = copy.deepcopy(curr_positions)
    try:
        account = client.get_account(ACCOUNT_ID, fields=Client.Account.Fields.POSITIONS).json()["securitiesAccount"]
        new_positions = account["positions"]
        acc_value = account["currentBalances"]["liquidationValue"]
        tracked_positions = []
        #addition or update
        for pos in new_positions:
            symbol = pos["instrument"]["symbol"]
            amt = pos["longQuantity"]
            tracked_positions.append(symbol)
            curr_positions[symbol] = pos
            if tmp.get(symbol) == None or amt > tmp[symbol]["longQuantity"]:
                await order_fill(pos, "Buy", acc_value)
            elif amt < tmp[symbol]["longQuantity"]:
                await order_fill(pos, "Trim", acc_value, tmp)
        #removal
        for symbol in tmp.keys():
            if symbol not in tracked_positions:
                del curr_positions[symbol]
                if tmp[symbol]["currentDayProfitLossPercentage"] > 0:
                    await order_fill(tmp[symbol], acc_value, "Exit")
                else:
                    await order_fill(tmp[symbol], acc_value, "Cut")
    except KeyError:
        if tmp != {}:
            curr_positions = {}
            for symbol in tmp.keys():
                if pos["currentDayProfitLossPercentage"] > 0:
                    await order_fill(tmp[symbol], acc_value, "Exit")
                else:
                    await order_fill(tmp[symbol], acc_value, "Cut")

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    if open_requests > 0:
        update_positions.start()

bot.run(TOKEN)