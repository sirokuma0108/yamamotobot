import discord
from discord.ext import commands
import json
import random
import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# トークンは環境変数から取得（GitHubには絶対に書かない）
TOKEN = os.getenv('DISCORD_TOKEN')

# --- 職業データの設定 ---
JOBS = {
    "フリーター": {
        "min": 100, "max": 300, "cooldown": 600, "level_bonus": 20, "price": 0
    },
    "サラリーマン": {
        "min": 600, "max": 800, "cooldown": 600, "level_bonus": 20, "price": 5000
    },
    "鍛冶職人": {
        "min": 50, "max": 80, "cooldown": 3600, "level_bonus": 150, "price": 5000
    },
    "医者": {
        "min": 2000, "max": 3000, "cooldown": 1200, "level_bonus": 50, "price": 50000
    }
}

# get_user関数内の初期値に "job": "フリーター" を追加してください
# data[uid] = { ... "job": "フリーター", ... }

# データ保存用ファイル
DATA_FILE = 'data.json'

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='y!', intents=intents)

# --- データ管理機能 ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def get_user(data, user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "money": 0,
            "bank": 0,
            "xp": 0,
            "lv": 1,
            "job": "フリーター", # ← これを追加！
            "last_work_time": None, # ← last_work から名称変更（workコマンドに合わせる）
            "items": {"けいけんアメ": 0, "ふしぎなアメ": 0}
        }
    return data[uid]

def check_lv_up(user):
    # 必要XP = 5 + (Lv-1)*5
    needed_xp = 5 + (user["lv"] - 1) * 5
    if user["xp"] >= needed_xp:
        user["xp"] -= needed_xp
        user["lv"] += 1
        return True
    return False

# --- コマンド ---

@bot.command()
async def work(ctx):
    data = load_data()
    user = get_user(data, ctx.author.id)
    job_info = JOBS.get(user.get("job", "フリーター"))
    
    # クールタイムの動的チェック (commands.cooldownの代わり)
    now = datetime.now()
    last_work_str = user.get("last_work_time")
    if last_work_str:
        last_work = datetime.fromisoformat(last_work_str)
        wait_time = timedelta(seconds=job_info["cooldown"])
        if now < last_work + wait_time:
            remaining = (last_work + wait_time - now).total_seconds()
            return await ctx.send(f"⏳ まだ働けません。あと **{int(remaining)}秒** 待ってください。")

    # 給料計算: (最低 + Lv*ボ) 〜 (最高 + Lv*ボ)
    # ※Lv1の時はボーナスがレベル1つ分乗る仕様（ご指定の「レベル1つ上がるごとに」）
    bonus = user["lv"] * job_info["level_bonus"]
    gain = random.randint(job_info["min"] + bonus, job_info["max"] + bonus)
    
    user["money"] += gain
    user["xp"] += 1
    user["last_work_time"] = now.isoformat() # 現在時刻を保存
    
    msg = f"💰 **{user['job']}**として働き、**{gain}コイン**獲得しました！"
    if check_lv_up(user):
        msg += f"\n🆙 レベルアップ！ **Lv.{user['lv']}** になりました！"
    
    save_data(data)
    await ctx.send(msg)

# --- ブラックジャック用のViewクラス ---
class BJView(discord.ui.View):
    def __init__(self, ctx, bet, user_data, full_data):
        super().__init__(timeout=60.0) # 60秒でタイムアウト
        self.ctx = ctx
        self.bet = bet
        self.user = user_data
        self.full_data = full_data
        self.player_cards = [random.randint(1, 11), random.randint(1, 11)]
        self.dealer_cards = [random.randint(1, 11), random.randint(1, 11)]

    def get_score(self, cards):
        score = sum(cards)
        # エース(11)の調整：21を超えたら1として扱う
        if score > 21 and 11 in cards:
            score -= 10
        return score

    def make_embed(self, finished=False):
        p_score = self.get_score(self.player_cards)
        d_score = self.get_score(self.dealer_cards)
        
        embed = discord.Embed(title="🃏 ブラックジャック", color=0x2f3136)
        embed.add_field(name=f"👤 {self.ctx.author.display_name}", value=f"カード: {self.player_cards}\nスコア: **{p_score}**", inline=True)
        
        if finished:
            embed.add_field(name="🤖 ディーラー", value=f"カード: {self.dealer_cards}\nスコア: **{d_score}**", inline=True)
        else:
            embed.add_field(name="🤖 ディーラー", value=f"カード: [{self.dealer_cards[0]}, ?]\nスコア: **??**", inline=True)
        
        embed.set_footer(text=f"ベット額: {self.bet}コイン")
        return embed

    @discord.ui.button(label="ヒット (引く)", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author: return
        
        self.player_cards.append(random.randint(1, 11))
        p_score = self.get_score(self.player_cards)
        
        if p_score > 21: # バースト
            self.stop()
            await self.end_game(interaction, "💥 バースト！あなたの負けです。", -self.bet)
        else:
            await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="スタンド (勝負)", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author: return
        self.stop()
        
        # ディーラーは17以上になるまで引き続ける
        while self.get_score(self.dealer_cards) < 17:
            self.dealer_cards.append(random.randint(1, 11))
        
        p_score = self.get_score(self.player_cards)
        d_score = self.get_score(self.dealer_cards)
        
        if d_score > 21 or p_score > d_score:
            await self.end_game(interaction, "🎉 おめでとうございます！あなたの勝ちです！", int(self.bet * 1.5) - self.bet)
        elif p_score < d_score:
            await self.end_game(interaction, "💀 ディーラーの勝ち。残念...", -self.bet)
        else:
            await self.end_game(interaction, "🤝 引き分けです。", 0)

    async def end_game(self, interaction, result_text, money_diff):
        self.user["money"] += money_diff
        save_data(self.full_data)
        
        embed = self.make_embed(finished=True)
        embed.description = f"**結果: {result_text}**\n所持金変動: {money_diff}コイン"
        
        # ボタンを無効化して更新
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

# --- コマンド部分 ---
@bot.command()
async def bj(ctx, bet: int):
    data = load_data()
    user = get_user(data, ctx.author.id)
    
    if bet <= 0:
        return await ctx.send("1コイン以上ベットしてください。")
    if user["money"] < bet:
        return await ctx.send(f"お金が足りません！（所持金: {user['money']}コイン）")
    
    view = BJView(ctx, bet, user, data)
    await ctx.send(embed=view.make_embed(), view=view)

@bot.command()
async def bal(ctx):
    data = load_data()
    user = get_user(data, ctx.author.id)
    embed = discord.Embed(title=f"{ctx.author.display_name}の残高", color=0x00ff00)
    embed.add_field(name="所持金", value=f"{user['money']}コイン")
    embed.add_field(name="銀行預金", value=f"{user['bank']}コイン")
    embed.add_field(name="レベル", value=f"Lv.{user['lv']} (xp:{user['xp']})")
    await ctx.send(embed=embed)

@bot.command()
async def dep(ctx, amount: str):
    data = load_data()
    user = get_user(data, ctx.author.id)
    if amount == "all":
        amount = user["money"]
    else:
        amount = int(amount)
    
    if user["money"] >= amount > 0:
        user["money"] -= amount
        user["bank"] += amount
        save_data(data)
        await ctx.send(f"🏦 銀行に**{amount}コイン**預け入れました。")
    else:
        await ctx.send("お金が足りないか、無効な数値です。")

@bot.command()
async def with_draw(ctx, amount: str): # 'with'はPython予約語のため
    data = load_data()
    user = get_user(data, ctx.author.id)
    if amount == "all":
        amount = user["bank"]
    else:
        amount = int(amount)
        
    if user["bank"] >= amount > 0:
        user["bank"] -= amount
        user["money"] += amount
        save_data(data)
        await ctx.send(f"💸 銀行から**{amount}コイン**引き出しました。")


# デフォルトのヘルプを削除（自作ヘルプを優先させるため）
bot.remove_command('help')

@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="📜 山本bot コマンド一覧",
        description="プレフィックスは `y!` です",
        color=0x3498db
    )

    # 基本コマンド
    embed.add_field(
        name="💰 基本操作",
        value=(
            "`y!work` - 仕事をしてお金とXPを獲得（職業により報酬・CTが変化）\n"
            "`y!bal` - 所持金、銀行残高、レベルを確認\n"
            "`y!top` - 総資産ランキングを表示"
        ),
        inline=False
    )

    # 銀行・ギャンブル
    embed.add_field(
        name="🏦 銀行 & 🎲 ギャンブル",
        value=(
            "`y!dep <金額>` - 銀行に預金（allで全額）\n"
            "`y!with <金額>` - 銀行から出金（allで全額）\n"
            "`y!bj <bet>` - ブラックジャック（勝てば1.5倍）\n"
            "`y!100pond <bet>` - 1/100の確率で100倍配当！"
        ),
        inline=False
    )

    # ショップ・職業
    embed.add_field(
        name="🛒 ショップ & 💼 転職",
        value=(
            "`y!shop` - アイテムショップを開く\n"
            "`y!use <個数> <アイテム名>` - アイテムを使用\n"
            "`y!job <職業名>` - 指定した職業に転職（レベルはリセットされます）"
        ),
        inline=False
    )

    # 職業ステータス一覧を動的に生成
    job_list = ""
    for name, info in JOBS.items():
        job_list += f"**{name}**: {info['price']}円 (CT:{info['cooldown']//60}分)\n"
    
    embed.add_field(name="📋 職業リスト", value=job_list, inline=False)

    embed.set_footer(text="レベルが上がると、すべての職業で給料の最低/最高額がアップします！")
    
    await ctx.send(embed=embed)

@bot.command()
async def top(ctx):
    data = load_data()
    ranking = sorted(data.items(), key=lambda x: x[1]['money'] + x[1]['bank'], reverse=True)
    
    embed = discord.Embed(title="🏆 総資産ランキング", color=0xffd700)
    for i, (uid, info) in enumerate(ranking[:10], 1):
        # get_user ではなく fetch_user を使う（非同期なので await が必要）
        try:
            user = await bot.fetch_user(int(uid))
            name = user.display_name
        except:
            name = f"Unknown({uid})"
            
        total = info['money'] + info['bank']
        embed.add_field(name=f"{i}位: {name}", value=f"{total}コイン (Lv.{info['lv']})", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def job(ctx, job_name: str):
    data = load_data()
    user = get_user(data, ctx.author.id)
    
    if job_name not in JOBS:
        return await ctx.send(f"❌ その職業は存在しません。利用可能: {', '.join(JOBS.keys())}")
    
    job_info = JOBS[job_name]
    
    # 既になっている職業の場合
    if user["job"] == job_name:
        return await ctx.send("既にその職業に就いています。")
    
    # 所持金チェック
    if user["money"] < job_info["price"]:
        return await ctx.send(f"🚫 お金が足りません。{job_name}になるには**{job_info['price']}コイン**必要です。")
    
    # 転職処理
    user["money"] -= job_info["price"]
    user["job"] = job_name
    user["lv"] = 1   # レベルリセット
    user["xp"] = 0   # XPもリセット
    
    save_data(data)
    await ctx.send(f"💼 **{job_name}**に転職しました！レベルは1にリセットされました。")

@bot.command(name="100pond")
async def pond(ctx, bet: int):
    data = load_data()
    user = get_user(data, ctx.author.id)
    if user["money"] < bet or bet <= 0:
        return await ctx.send("お金が足りません。")
    
    p = random.randint(1, 100)
    if p == 100:
        reward = bet * 100
        user["money"] += reward
        await ctx.send(f"🏴󠁧󠁢󠁧󠁢󠁥󠁮󠁧󠁿 **100ポンド！** ベットの100倍、**{reward}コイン**獲得！")
    else:
        user["money"] -= bet
        await ctx.send(f"☁️ {p}ポンドでした。ベット没収です。")
    save_data(data)

# --- ショップ & アイテム ---

class ShopView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx

    @discord.ui.button(label="けいけんアメ (1000円)", style=discord.ButtonStyle.primary)
    async def buy_xp(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_buy(interaction, "けいけんアメ", 1000)

    @discord.ui.button(label="ふしぎなアメ (10000円)", style=discord.ButtonStyle.success)
    async def buy_lv(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_buy(interaction, "ふしぎなアメ", 10000)

    async def process_buy(self, interaction, item_name, price):
        data = load_data()
        user = get_user(data, interaction.user.id)
        if user["money"] >= price:
            user["money"] -= price
            user["items"][item_name] = user["items"].get(item_name, 0) + 1
            save_data(data)
            await interaction.response.send_message(f"🛒 {item_name}を購入しました！", ephemeral=True)
        else:
            await interaction.response.send_message("お金が足りません。", ephemeral=True)

@bot.command()
async def shop(ctx):
    embed = discord.Embed(title="🏪 アイテムショップ", description="ボタンを押して購入できます。")
    await ctx.send(embed=embed, view=ShopView(ctx))

@bot.command()
async def use(ctx, amount: int, *, item_name: str):
    data = load_data()
    user = get_user(data, ctx.author.id)
    
    if user["items"].get(item_name, 0) < amount:
        return await ctx.send("アイテムを持っていません。")
    
    user["items"][item_name] -= amount
    msg = f"✨ {item_name}を{amount}個使用しました！\n"
    
    if item_name == "けいけんアメ":
        user["xp"] += 10 * amount
    elif item_name == "ふしぎなアメ":
        user["lv"] += 1 * amount
        
    while check_lv_up(user): pass # 連続レベルアップ対応
    
    save_data(data)
    await ctx.send(msg + f"現在のステータス: Lv.{user['lv']} (xp:{user['xp']})")

# エラーハンドリング (クールタイム用)
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"😫 クールタイム中だよ！ あと **{error.retry_after:.1f}秒** 待ってね。")

bot.run(TOKEN)