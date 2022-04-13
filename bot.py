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
from datetime import datetime

#logging
logging.basicConfig(format="%(asctime)s %(levelname)s:%(name)s: %(message)s", datefmt="%H:%M:%S",
                    filename='bot.log', filemode='w', level=logging.WARNING)

load_dotenv()

#const 
TOKEN_PATH = 'token.json'
API_KEY = os.getenv('API_KEY')
TOKEN = os.getenv('DISCORD_TOKEN')
ACCOUNT_ID = os.getenv('ACCOUNT_ID')
CHANNEL_ID = os.getenv('CHANNEL_ID')
USER_ID = os.getenv('USER_ID')

client = auth.client_from_token_file(TOKEN_PATH, API_KEY)

#initializing global variables
curr_positions = {}
try:
    active_positions = client.get_account(ACCOUNT_ID, fields=Client.Account.Fields.POSITIONS).json()["securitiesAccount"]["positions"]
    for pos in active_positions:
        symbol = pos["instrument"]["symbol"]
        curr_positions[symbol] = {"quantity": pos["longQuantity"], "total_cost": pos["longQuantity"] * pos["averagePrice"], "sell_price": 0}
except KeyError:
    pass

open_requests = len(client.get_orders_by_path(ACCOUNT_ID,status=Client.Order.Status.AWAITING_CONDITION).json())
open_requests += len(client.get_orders_by_path(ACCOUNT_ID,status=Client.Order.Status.QUEUED).json())
open_requests += len(client.get_orders_by_path(ACCOUNT_ID,status=Client.Order.Status.PENDING_ACTIVATION).json())

streaming = True
filled = set()

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
    acc_value = client.get_account(ACCOUNT_ID).json()["securitiesAccount"]["currentBalances"]["liquidationValue"]
    limit_price = None if order_type != "Limit" else "{:0.2f}".format(float(order["OrderPricing"]["Limit"]))
    bid = "{:0.2f}".format(float(order["OrderPricing"]["Bid"]))
    ask = "{:0.2f}".format(float(order["OrderPricing"]["Ask"]))
    if bs == "Sell":
        if curr_positions[symbol]["quantity"] - num_contracts > 0:
            bs = "Trim"
        else:
            avg_cost = curr_positions[symbol]["total_cost"] / curr_positions[symbol]["quantity"]
            try:
                bs = "Exit" if avg_cost < limit_price else "Cut"
            except TypeError: #market order
                bs = "Exit" if avg_cost < bid else "Cut"
    return bs, ticker, strike, exp, cp, order_type, acc_value, num_contracts, limit_price, bid, ask, symbol
        
def filter(msg):
    global open_requests
    msg_type = msg["content"][0]["MESSAGE_TYPE"]

    if msg_type == "SUBSCRIBED":
        return format(Embed(title="Trade Alert Bot Activated"))
    elif msg_type in {"OrderEntryRequest","OrderCancelReplaceRequest", "UROUT"}:
        if msg_type in {"OrderEntryRequest","OrderCancelReplaceRequest"}:
            open_requests += 1
            if not update_positions.is_running():
                update_positions.start()

        msg_data = xmltodict.parse(msg["content"][0]["MESSAGE_DATA"])
        bs, ticker, strike, exp, cp, order_type, acc_value, num_contracts, limit_price, bid, ask, symbol = parser(msg_data, msg_type)

        if bs == "Trim":
            trim_percentage = str(int(num_contracts/curr_positions[symbol]["quantity"] * 100)) + "%"
            e = Embed(title="{} {} {} {} {} {}".format(bs, trim_percentage, ticker, exp, strike, cp))
        else:
            e = Embed(title="{} {} {} {} {}".format(bs, ticker, exp, strike, cp))

        e.add_field(name="Order Type", value=order_type, inline=True)
        e.color = 0xFFFF00

        if order_type == "Limit" or order_type == "Stop Limit":
            e.add_field(name="Limit Price", value=limit_price, inline=True)
            if bs == "Buy":
                e.add_field(name="Position Size", value=str(int(float(limit_price) * 10000.0 * num_contracts / float(acc_value))) + "%")
        elif order_type == "Stop":
            try:
                e.add_field(name="Limit Price", value=str(msg_data[msg_type + "Message"]["Order"]["OrderPricing"]["Stop"]), inline=True)
            except KeyError:
                pass
        elif order_type == "Market":
            e.add_field(name="Bid", value= bid, inline=True)
            e.add_field(name="Ask", value=ask, inline=True)
            if bs == "Buy":
                e.add_field(name="Position Size", value=str(int((float(bid)+float(ask))/2 * 10000.0 * num_contracts / float(acc_value))) + "%")

        if msg_type == "UROUT":
            open_requests -= 1
            if open_requests == 0 and update_positions.is_running():
                update_positions.stop()
            if bs == "Trim":
                return format(Embed(title="Order Cancelled", description = "{} {} {} {} {} {}".format(bs, trim_percentage, ticker, exp, strike, cp), color=0xFF8B00))
            else:
                return format(Embed(title="Order Cancelled", description = "{} {} {} {} {}".format(bs, ticker, exp, strike, cp), color=0xFF8B00))
        elif msg_type == "OrderEntryRequest":
            e.description = "Order Placed"
        elif msg_type == "OrderCancelReplaceRequest":
            e.description = "Replacement Order Placed"
        return format(e)
    else:
        return None

def format(e):
    e.set_author(name=user.name, icon_url=user.avatar_url)
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
        filtered = filter(msg)
        if filtered != None:
            if str(filtered.color) == "#ffff00":
                await ctx.send("@here")
            await ctx.send(embed=filtered)

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
async def pos(ctx):
    await ctx.send(curr_positions)

@bot.command(name="filled", help="Displays past fills")
async def fill(ctx):
    await ctx.send(filled)

@bot.command(name="req", help="Displays open request count")
async def req(ctx):
    await ctx.send("Open Requests: " + str(open_requests))

async def order_fill(symbol, action, quantity, fill_price, acc_value):
    global open_requests
    open_requests -= 1
    if open_requests == 0 and update_positions.is_running():
        update_positions.stop()
    option = symbol.split("_")
    ticker = option[0]
    strike = option[1][7:]
    exp = option[1][:6][:2] + "/" + option[1][:6][2:4] + "/" + option[1][:6][4:6]
    cp = "Call" if option[1][6] == "C" else "Put"
    avg_cost = curr_positions[symbol]["total_cost"] / curr_positions[symbol]["quantity"]
    if action == "Sell" and curr_positions[symbol]["quantity"] > 0:
            trim_percentage = str(int(quantity / (curr_positions[symbol]["quantity"] + quantity) * 100)) + "%"
            e = Embed(title="Trim {} {} {} {} {}".format(trim_percentage, ticker, exp, strike, cp))
            e.add_field(name="Position Left", value= str(int(curr_positions[symbol]["total_cost"] / acc_value * 100)) + "%", inline=True)
    else:
        e = Embed(title="{} {} {} {} {}".format(action, ticker, exp, strike, cp))
    e.add_field(name="Average Cost", value="{:.2f}".format(avg_cost), inline=True)
    e.add_field(name="Fill Price", value=str(fill_price), inline=True)
    if action == "Buy":
        e.add_field(name="Total Position", value=str(int(curr_positions[symbol]["total_cost"] / acc_value * 100)) + "%", inline=True)
    else:
        e.add_field(name="Profit/Loss", value=str(int((fill_price-avg_cost) / avg_cost * 100))+"%", inline=True)
    e.color = 0x50f276 if action == "Buy" else 0xFF0000
    e.description = "Order Filled"
    channel = bot.get_channel(int(CHANNEL_ID))
    await channel.send(embed=format(e))

@tasks.loop(seconds=1)
async def update_positions():
    global curr_positions, filled
    account = client.get_account(ACCOUNT_ID, fields=Client.Account.Fields.ORDERS).json()["securitiesAccount"]
    acc_value = account["currentBalances"]["liquidationValue"]
    prev = copy.deepcopy(curr_positions)
    updated = {}
    try:
        orders = account["orderStrategies"]
        for order in orders:
            if order["status"] == "FILLED" and order["orderId"] not in filled:
                filled.add(order["orderId"])
                for leg in order["orderLegCollection"]:
                    inst = leg["instruction"]
                    symbol = leg["instrument"]["symbol"]
                    for exec in order["orderActivityCollection"]:
                        if exec["executionLegs"]["legId"] == leg["legId"]:
                            partial_amt = exec["executionLegs"]["quantity"]
                            price = exec["executionLegs"]["price"]
                            if inst == "BUY_TO_OPEN":
                                updated[symbol] = "Buy"
                                if curr_positions.get(symbol) == None:
                                    curr_positions[symbol] = {"quantity": partial_amt, "total_cost": price, "sell_price": 0}
                                else:
                                    curr_positions[symbol]["quantity"] += partial_amt
                                    curr_positions[symbol]["total_cost"] += price
                            elif inst == "SELL_TO_CLOSE":
                                updated[symbol] = "Sell"
                                curr_positions[symbol]["quantity"] -= partial_amt
                                curr_positions[symbol]["sell_price"] += price
        for symbol in updated:
            if updated[symbol] == "Buy":
                quantity = curr_positions[symbol]["quantity"] - prev[symbol]["quantity"]
                fill_price = (curr_positions[symbol]["total_cost"] - prev[symbol]["total_cost"]) / quantity
                await order_fill(symbol, "Buy", quantity, fill_price, acc_value)
            else:
                quantity = prev[symbol]["quantity"] - curr_positions[symbol]["quantity"]
                fill_price = curr_positions[symbol]["sell_price"] / quantity
                curr_positions[symbol]["sell_price"] = 0
                curr_positions[symbol]["total_cost"] = curr_positions[symbol]["total_cost"] / prev[symbol]["quantity"] * curr_positions[symbol]["quantity"]
                await order_fill(symbol, "Sell", quantity, fill_price, acc_value)
                if curr_positions[symbol]["quantity"] == 0:
                    del curr_positions[symbol]                      
    except KeyError:
        pass

@tasks.loop(minutes=59.9)
async def empty_filled():
    global filled
    if datetime.now().hour == 20:
        filled = set()

@bot.event
async def on_ready():
    global user
    channel = bot.get_channel(int(CHANNEL_ID))
    user = await bot.fetch_user(int(USER_ID))
    print(f'{bot.user.name} has connected to Discord!')
    empty_filled.start()
    if open_requests > 0:
        update_positions.start()
    await read_stream(channel)

bot.run(TOKEN)