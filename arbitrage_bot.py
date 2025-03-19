import requests
import time
import json
import logging
from datetime import datetime
import pandas as pd
import concurrent.futures
from colorama import Fore, Back, Style, init
from tabulate import tabulate

# Initialize colorama
init(autoreset=True)

# تنظیمات لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("arbitrage.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ArbitrageBot")

class ArbitrageBot:
    def __init__(self, config_file="config.json"):
        """راه‌اندازی ربات آربیتراژ"""
        self.load_config(config_file)
        self.exchanges = {}
        self.initialize_exchanges()
        
    def load_config(self, config_file):
        """بارگذاری تنظیمات از فایل پیکربندی"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            logger.info("Configuration loaded successfully")
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            # تنظیمات پیش‌فرض
            self.config = {
                "exchanges": {
                    "nobitex": {
                        "url": "https://api.nobitex.ir/market/stats",
                        "enabled": True
                    },
                    "wallex": {
                        "url": "https://api.wallex.ir/v1/markets",
                        "enabled": True
                    },
                    "ramzinex": {
                        "url": "https://ramzinex.com/exchange/api/v1.0/exchange/pairs",
                        "enabled": True
                    },
                    "exir": {
                        "url": "https://api.exir.io/v1/orderbooks/all",
                        "enabled": True
                    }
                },
                "pairs": ["USDT-IRT"],  # فقط جفت ارز تتر-تومان
                "min_profit_percent": 1.0,
                "check_interval": 60,
                "proxy": None
            }
            
    def initialize_exchanges(self):
        """راه‌اندازی اتصال به صرافی‌ها"""
        for exchange_name, exchange_data in self.config["exchanges"].items():
            if exchange_data["enabled"]:
                self.exchanges[exchange_name] = {
                    "url": exchange_data["url"],
                    "parser": getattr(self, f"parse_{exchange_name}")
                }
        logger.info(f"Active exchanges: {list(self.exchanges.keys())}")
    
    def parse_nobitex(self, data):
        """تجزیه داده‌های نوبیتکس"""
        results = {}
        try:
            # Check if data is a dictionary
            if not isinstance(data, dict):
                logger.error(f"Nobitex data is not a dictionary: {type(data)}")
                return {}
            
            # بررسی جفت ارز USDT/IRT
            stats = data.get("stats", {})
            
            # جستجو برای جفت ارز USDT/IRT یا USDT/TMN
            for pair_name in ["usdt-rls", "usdt-irt", "usdt-tmn"]:
                if pair_name in stats:
                    pair_data = stats[pair_name]
                    
                    # استخراج قیمت‌ها
                    if "bestSell" in pair_data and "bestBuy" in pair_data:
                        ask_price = float(pair_data["bestSell"])
                        bid_price = float(pair_data["bestBuy"])
                        
                        # نرمال‌سازی قیمت‌ها
                        ask_price = self.normalize_price(ask_price, "nobitex")
                        bid_price = self.normalize_price(bid_price, "nobitex")
                        
                        if ask_price > 0 and bid_price > 0:
                            results["USDT-IRT"] = {
                                "ask": ask_price,
                                "bid": bid_price
                            }
                            break
            
            # اگر داده‌ای پیدا نشد، لاگ کن
            if not results:
                available_pairs = list(stats.keys()) if stats else []
                logger.warning(f"No USDT-IRT pair found in Nobitex data. Available pairs: {available_pairs}")
            
            return results
        except Exception as e:
            logger.error(f"Error parsing Nobitex data: {e}")
            return {}
    
    def parse_wallex(self, data):
        """تجزیه داده‌های والکس"""
        results = {}
        try:
            # Check if data is a dictionary
            if not isinstance(data, dict):
                logger.error(f"Wallex data is not a dictionary: {type(data)}")
                return {}
            
            # بررسی در result.symbols
            symbols = data.get("result", {}).get("symbols", {})
            if isinstance(symbols, dict):
                for symbol_name, symbol_data in symbols.items():
                    if any(s in symbol_name.lower() for s in ["usdttmn", "usdtirt", "usdtirr"]):
                        stats = symbol_data.get("stats", {})
                        
                        # استخراج قیمت‌ها
                        ask_price = float(stats.get("askPrice", 0))
                        bid_price = float(stats.get("bidPrice", 0))
                        
                        if ask_price > 0 and bid_price > 0:
                            results["USDT-IRT"] = {
                                "ask": ask_price,
                                "bid": bid_price
                            }
                            break
            
            # اگر داده‌ای پیدا نشد، لاگ کن
            if not results:
                available_symbols = list(symbols.keys()) if isinstance(symbols, dict) else []
                logger.warning(f"No USDT-IRT pair found in Wallex data. Available symbols: {available_symbols}")
            
            return results
        except Exception as e:
            logger.error(f"Error parsing Wallex data: {e}")
            return {}
    
    def parse_ramzinex(self, data):
        """تجزیه داده‌های رمزینکس"""
        results = {}
        try:
            # Check if data is a dictionary
            if not isinstance(data, dict):
                logger.error(f"Ramzinex data is not a dictionary: {type(data)}")
                return {}
            
            # بررسی در data.data
            pairs_data = data.get("data", [])
            if isinstance(pairs_data, list):
                for pair in pairs_data:
                    if not isinstance(pair, dict):
                        continue
                    
                    # بررسی اگر جفت ارز USDT/IRT است
                    if pair.get("source_currency", {}).get("code", "").lower() == "usdt" and \
                       pair.get("destination_currency", {}).get("code", "").lower() in ["irt", "irr", "tmn"]:
                        
                        # استخراج قیمت‌ها
                        ask_price = float(pair.get("sell_price", 0))
                        bid_price = float(pair.get("buy_price", 0))
                        
                        if ask_price > 0 and bid_price > 0:
                            results["USDT-IRT"] = {
                                "ask": ask_price,
                                "bid": bid_price
                            }
                            break
            
            # اگر داده‌ای پیدا نشد، لاگ کن
            if not results:
                logger.warning("No USDT-IRT pair found in Ramzinex data")
            
            return results
        except Exception as e:
            logger.error(f"Error parsing Ramzinex data: {e}")
            return {}
    
    def parse_exir(self, data):
        """تجزیه داده‌های اکسیر"""
        results = {}
        try:
            # Check if data is a dictionary
            if not isinstance(data, dict):
                logger.error(f"Exir data is not a dictionary: {type(data)}")
                return {}
            
            # بررسی تمام جفت ارزهای ممکن برای تتر-تومان
            possible_symbols = ["usdtirt", "usdttmn", "usdtirr"]
            
            for symbol, orderbook in data.items():
                if not isinstance(orderbook, dict):
                    continue
                
                if any(ps in symbol.lower() for ps in possible_symbols):
                    asks = orderbook.get("asks", [])
                    bids = orderbook.get("bids", [])
                    
                    if asks and bids:
                        try:
                            ask_price = float(asks[0][0])
                            bid_price = float(bids[0][0])
                            
                            results["USDT-IRT"] = {
                                "ask": ask_price,
                                "bid": bid_price
                            }
                            break
                        except (IndexError, ValueError) as e:
                            logger.warning(f"Error parsing prices for {symbol} on Exir: {e}")
            
            # اگر داده‌ای پیدا نشد، لاگ کن
            if not results:
                logger.warning(f"No USDT-IRT pair found in Exir data. Available symbols: {list(data.keys())}")
            
            return results
        except Exception as e:
            logger.error(f"Error parsing Exir data: {e}")
            return {}
    
    def fetch_exchange_data(self, exchange_name, exchange_info):
        """دریافت داده‌ها از یک صرافی"""
        try:
            proxies = {}
            if self.config.get("proxy"):
                proxies = {
                    "http": self.config["proxy"],
                    "https": self.config["proxy"]
                }
                
            logger.info(f"Fetching data from {exchange_name}...")
            response = requests.get(exchange_info["url"], proxies=proxies, timeout=10)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    
                    # لاگ کردن ساختار داده برای دیباگ (فقط 200 کاراکتر اول)
                    data_sample = str(data)[:200] + "..." if len(str(data)) > 200 else str(data)
                    logger.debug(f"{exchange_name} raw data sample: {data_sample}")
                    
                    parsed_data = exchange_info["parser"](data)
                    
                    if not parsed_data:
                        logger.warning(f"No valid data parsed from {exchange_name}")
                    
                    return exchange_name, parsed_data
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding JSON from {exchange_name}: {e}")
                    return exchange_name, {}
            else:
                logger.warning(f"Error fetching data from {exchange_name}: code {response.status_code}")
                return exchange_name, {}
        except Exception as e:
            logger.error(f"Error connecting to {exchange_name}: {e}")
            return exchange_name, {}
    
    def fetch_all_exchanges(self):
        """دریافت داده‌ها از تمام صرافی‌ها به صورت همزمان"""
        all_data = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.exchanges)) as executor:
            futures = {
                executor.submit(self.fetch_exchange_data, exchange_name, exchange_info): exchange_name
                for exchange_name, exchange_info in self.exchanges.items()
            }
            
            for future in concurrent.futures.as_completed(futures):
                exchange_name, data = future.result()
                all_data[exchange_name] = data
                
        return all_data
    
    def find_arbitrage_opportunities(self, market_data):
        """یافتن فرصت‌های آربیتراژ"""
        opportunities = []
        
        for pair in self.config["pairs"]:
            # جمع‌آوری قیمت‌های خرید و فروش از تمام صرافی‌ها برای این جفت ارز
            exchanges_data = []
            
            for exchange_name, exchange_data in market_data.items():
                if pair in exchange_data:
                    exchanges_data.append({
                        "exchange": exchange_name,
                        "pair": pair,
                        "ask": exchange_data[pair]["ask"],  # قیمت فروش صرافی (قیمتی که ما می‌خریم)
                        "bid": exchange_data[pair]["bid"]   # قیمت خرید صرافی (قیمتی که ما می‌فروشیم)
                    })
            
            # مرتب‌سازی صرافی‌ها بر اساس قیمت فروش (ask) - از کمترین به بیشترین
            exchanges_by_ask = sorted(exchanges_data, key=lambda x: x["ask"])
            
            # مرتب‌سازی صرافی‌ها بر اساس قیمت خرید (bid) - از بیشترین به کمترین
            exchanges_by_bid = sorted(exchanges_data, key=lambda x: x["bid"], reverse=True)
            
            # بررسی فرصت‌های آربیتراژ بین صرافی‌ها
            for buy_exchange in exchanges_by_ask:
                for sell_exchange in exchanges_by_bid:
                    if buy_exchange["exchange"] != sell_exchange["exchange"]:
                        # خرید با قیمت ask از صرافی با کمترین ask
                        buy_price = buy_exchange["ask"]
                        # فروش با قیمت bid به صرافی با بیشترین bid
                        sell_price = sell_exchange["bid"]
                        
                        profit_percent = ((sell_price - buy_price) / buy_price) * 100
                        
                        # فیلتر کردن فرصت‌های با سود غیرمعقول (بیش از 20%)
                        if profit_percent > self.config["min_profit_percent"] and profit_percent < 20:
                            opportunities.append({
                                "pair": pair,
                                "buy_exchange": buy_exchange["exchange"],
                                "buy_price": buy_price,
                                "sell_exchange": sell_exchange["exchange"],
                                "sell_price": sell_price,
                                "profit_percent": profit_percent
                            })
                            
                            # اگر یک فرصت پیدا کردیم، دیگر نیازی به بررسی صرافی‌های دیگر نیست
                            break
                
                # اگر یک فرصت پیدا کردیم، دیگر نیازی به بررسی صرافی‌های دیگر نیست
                if opportunities and opportunities[-1]["pair"] == pair:
                    break
        
        return opportunities
    
    def display_opportunities(self, opportunities):
        """نمایش فرصت‌های آربیتراژ"""
        if not opportunities:
            logger.info("No arbitrage opportunities found")
            return
        
        logger.info(f"Found {len(opportunities)} arbitrage opportunities:")
        
        # تبدیل به دیتافریم برای نمایش بهتر
        df = pd.DataFrame(opportunities)
        # محاسبه مقدار سود به تومان
        df['profit_amount'] = df['sell_price'] - df['buy_price']
        df = df.sort_values(by="profit_percent", ascending=False)
        
        # ایجاد جدول با tabulate
        table_data = []
        for _, row in df.iterrows():
            # رنگ‌بندی بر اساس درصد سود
            profit_color = Fore.GREEN
            if row['profit_percent'] > 5:
                profit_color = Fore.LIGHTGREEN_EX + Style.BRIGHT
            elif row['profit_percent'] > 3:
                profit_color = Fore.GREEN + Style.BRIGHT
            
            # ایجاد متن استراتژی
            strategy_text = f"Buy USDT from {row['buy_exchange']} at {row['buy_price']:,.0f} IRT → Sell on {row['sell_exchange']} at {row['sell_price']:,.0f} IRT"
            
            table_data.append([
                f"{Fore.CYAN}{row['pair']}{Style.RESET_ALL}",
                f"{Fore.WHITE}{strategy_text}{Style.RESET_ALL}",
                f"{Fore.WHITE}{row['profit_amount']:,.0f}{Style.RESET_ALL}",
                f"{profit_color}{row['profit_percent']:.2f}%{Style.RESET_ALL}"
            ])
        
        # نمایش جدول
        headers = [
            f"{Fore.WHITE}Pair{Style.RESET_ALL}", 
            f"{Fore.WHITE}Strategy{Style.RESET_ALL}", 
            f"{Fore.WHITE}Profit (IRT){Style.RESET_ALL}",
            f"{Fore.WHITE}Profit (%){Style.RESET_ALL}"
        ]
        
        print(f"\n{Back.BLUE}{Fore.WHITE} ARBITRAGE SIGNALS {Style.RESET_ALL}")
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # همچنان در فایل لاگ ثبت کن (بدون رنگ)
        for _, row in df.iterrows():
            logger.info(
                f"ARBITRAGE SIGNAL - Pair: {row['pair']} | "
                f"Strategy: Buy USDT from {row['buy_exchange']} at {row['buy_price']:.0f} IRT → Sell on {row['sell_exchange']} at {row['sell_price']:.0f} IRT | "
                f"Profit: {row['profit_amount']:.0f} IRT ({row['profit_percent']:.2f}%)"
            )
    
    def display_exchange_prices(self, market_data):
        """نمایش قیمت‌های تتر در تمام صرافی‌ها"""
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'Current USDT prices in all exchanges':^80}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        
        # جمع‌آوری قیمت‌های تمام صرافی‌ها
        exchange_prices = []
        
        for exchange_name, exchange_data in market_data.items():
            if "USDT-IRT" in exchange_data:
                exchange_prices.append({
                    "Exchange": exchange_name,
                    "Ask Price (Buy)": exchange_data["USDT-IRT"]["ask"],
                    "Bid Price (Sell)": exchange_data["USDT-IRT"]["bid"]
                })
        
        if not exchange_prices:
            print(f"{Fore.RED}No price data available from any exchange{Style.RESET_ALL}")
            logger.info("No price data available from any exchange")
            return
            
        # تبدیل به دیتافریم برای نمایش بهتر
        df = pd.DataFrame(exchange_prices)
        
        # ایجاد جدول قیمت‌ها
        table_data = []
        for _, row in df.iterrows():
            table_data.append([
                f"{Fore.YELLOW}{row['Exchange']}{Style.RESET_ALL}",
                f"{Fore.GREEN}{row['Ask Price (Buy)']:,.0f}{Style.RESET_ALL}",
                f"{Fore.BLUE}{row['Bid Price (Sell)']:,.0f}{Style.RESET_ALL}"
            ])
        
        # نمایش جدول قیمت‌ها
        headers = [
            f"{Fore.WHITE}Exchange{Style.RESET_ALL}", 
            f"{Fore.WHITE}Ask Price (Buy){Style.RESET_ALL}", 
            f"{Fore.WHITE}Bid Price (Sell){Style.RESET_ALL}"
        ]
        
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # مرتب‌سازی بر اساس قیمت خرید (صعودی)
        df_sorted_by_ask = df.sort_values(by="Ask Price (Buy)")
        
        # ایجاد جدول مرتب شده بر اساس قیمت خرید
        table_data_ask = []
        for _, row in df_sorted_by_ask.iterrows():
            table_data_ask.append([
                f"{Fore.YELLOW}{row['Exchange']}{Style.RESET_ALL}",
                f"{Fore.GREEN}{row['Ask Price (Buy)']:,.0f}{Style.RESET_ALL}",
                f"{Fore.BLUE}{row['Bid Price (Sell)']:,.0f}{Style.RESET_ALL}"
            ])
        
        print(f"\n{Fore.GREEN}Exchanges sorted by Ask Price (lowest to highest):{Style.RESET_ALL}")
        print(tabulate(table_data_ask, headers=headers, tablefmt="grid"))
        
        # مرتب‌سازی بر اساس قیمت فروش (نزولی)
        df_sorted_by_bid = df.sort_values(by="Bid Price (Sell)", ascending=False)
        
        # ایجاد جدول مرتب شده بر اساس قیمت فروش
        table_data_bid = []
        for _, row in df_sorted_by_bid.iterrows():
            table_data_bid.append([
                f"{Fore.YELLOW}{row['Exchange']}{Style.RESET_ALL}",
                f"{Fore.GREEN}{row['Ask Price (Buy)']:,.0f}{Style.RESET_ALL}",
                f"{Fore.BLUE}{row['Bid Price (Sell)']:,.0f}{Style.RESET_ALL}"
            ])
        
        print(f"\n{Fore.BLUE}Exchanges sorted by Bid Price (highest to lowest):{Style.RESET_ALL}")
        print(tabulate(table_data_bid, headers=headers, tablefmt="grid"))
        
        # همچنان در فایل لاگ ثبت کن (بدون رنگ)
        for _, row in df.iterrows():
            logger.info(
                f"{row['Exchange']}: "
                f"Ask: {row['Ask Price (Buy)']:,.0f} IRT | "
                f"Bid: {row['Bid Price (Sell)']:,.0f} IRT"
            )
        
        # نمایش بهترین فرصت خرید و فروش
        if len(df) >= 2:
            best_buy = df_sorted_by_ask.iloc[0]
            best_sell = df_sorted_by_bid.iloc[0]
            
            price_diff = best_sell["Bid Price (Sell)"] - best_buy["Ask Price (Buy)"]
            profit_percent = (price_diff / best_buy["Ask Price (Buy)"]) * 100
            
            # رنگ‌بندی بر اساس درصد سود
            profit_color = Fore.GREEN
            if profit_percent > 5:
                profit_color = Fore.LIGHTGREEN_EX + Style.BRIGHT
            elif profit_percent > 3:
                profit_color = Fore.GREEN + Style.BRIGHT
            elif profit_percent < 0:
                profit_color = Fore.RED
            
            # ایجاد جدول بهترین فرصت
            best_opportunity = [
                [
                    f"{Fore.YELLOW}{best_buy['Exchange']}{Style.RESET_ALL}",
                    f"{Fore.GREEN}{best_buy['Ask Price (Buy)']:,.0f}{Style.RESET_ALL}",
                    f"{Fore.YELLOW}{best_sell['Exchange']}{Style.RESET_ALL}",
                    f"{Fore.BLUE}{best_sell['Bid Price (Sell)']:,.0f}{Style.RESET_ALL}",
                    f"{Fore.WHITE}{price_diff:,.0f}{Style.RESET_ALL}",
                    f"{profit_color}{profit_percent:.2f}%{Style.RESET_ALL}"
                ]
            ]
            
            best_headers = [
                f"{Fore.WHITE}Buy Exchange{Style.RESET_ALL}", 
                f"{Fore.WHITE}Buy Price{Style.RESET_ALL}", 
                f"{Fore.WHITE}Sell Exchange{Style.RESET_ALL}", 
                f"{Fore.WHITE}Sell Price{Style.RESET_ALL}", 
                f"{Fore.WHITE}Profit (IRT){Style.RESET_ALL}", 
                f"{Fore.WHITE}Profit (%){Style.RESET_ALL}"
            ]
            
            print(f"\n{Back.MAGENTA}{Fore.WHITE} BEST OPPORTUNITY {Style.RESET_ALL}")
            print(tabulate(best_opportunity, headers=best_headers, tablefmt="grid"))
            
            # همچنان در فایل لاگ ثبت کن (بدون رنگ)
            logger.info(
                f"Best opportunity: Buy from {best_buy['Exchange']} at {best_buy['Ask Price (Buy)']:,.0f} IRT, "
                f"Sell on {best_sell['Exchange']} at {best_sell['Bid Price (Sell)']:,.0f} IRT. "
                f"Potential profit: {price_diff:,.0f} IRT ({profit_percent:.2f}%)"
            )
        
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
    
    def normalize_price(self, price, exchange_name):
        """نرمال‌سازی قیمت‌ها به تومان"""
        # اگر قیمت بیش از 10 برابر میانگین قیمت تتر است، احتمالاً به ریال است
        if price > 500000:  # احتمالاً به ریال است
            return price / 10  # تبدیل به تومان
        return price
    
    def run(self):
        """اجرای ربات آربیتراژ"""
        logger.info("Arbitrage bot started...")
        
        while True:
            try:
                start_time = time.time()
                
                # دریافت داده‌ها از تمام صرافی‌ها
                market_data = self.fetch_all_exchanges()
                
                # نمایش قیمت‌های تتر در تمام صرافی‌ها
                self.display_exchange_prices(market_data)
                
                # یافتن فرصت‌های آربیتراژ
                opportunities = self.find_arbitrage_opportunities(market_data)
                
                # نمایش فرصت‌ها
                self.display_opportunities(opportunities)
                
                # ذخیره فرصت‌ها در فایل
                if opportunities:
                    with open(f"opportunities_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w", encoding="utf-8") as f:
                        json.dump(opportunities, f, ensure_ascii=False, indent=2)
                
                execution_time = time.time() - start_time
                logger.info(f"Execution time: {execution_time:.2f} seconds")
                
                # انتظار تا بررسی بعدی
                sleep_time = max(1, self.config["check_interval"] - execution_time)
                time.sleep(sleep_time)
                
            except KeyboardInterrupt:
                logger.info("Bot stopped")
                break
            except Exception as e:
                logger.error(f"Error running bot: {e}")
                time.sleep(30)  # انتظار قبل از تلاش مجدد

if __name__ == "__main__":
    bot = ArbitrageBot()
    bot.run() 