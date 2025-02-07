from flask import Flask, render_template, jsonify
import ccxt
import logging
from datetime import datetime

app = Flask(__name__)

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações iniciais
min_profit_margin = 0.002  # Margem mínima de lucro (0.2%)
transaction_fee = 0.001    # Taxa de transação (0.1%)
slippage = 0.0005          # Derrapagem (0.05%)
fixed_investment = 100     # Valor fixo de compra por operação ($100)

# Lista inicial de pares (mais utilizados em arbitragem)
initial_pairs = [
    "ETH/USDT", "XRP/USDT", "ADA/USDT", "NEAR/USDT",
    "TRON/USDT", "DOT/USDT", "AVAX/USDT", "TON/USDT",
    "ENA/USDT", "AAVE/USDT", "LTC/USDT", "APT/USDT"
]

# Exchanges suportadas
exchanges = {
    "binance": ccxt.binance({'timeout': 10000}),
    "kraken": ccxt.kraken({'timeout': 10000}),
    "coinbase": ccxt.coinbase({'timeout': 10000}),
    "kucoin": ccxt.kucoin({'timeout': 10000}),
    "bitget": ccxt.bitget({'timeout': 10000}),
    "bitfinex": ccxt.bitfinex({'timeout': 10000}),
}

# Variáveis globais
transaction_history = []
unsupported_pairs = set()  # Para armazenar pares não suportados

def get_supported_pairs(pairs):
    """Filtra apenas os pares suportados por pelo menos duas exchanges."""
    supported_pairs = []
    for pair in pairs:
        if pair in unsupported_pairs:  # Ignora pares já identificados como não suportados
            continue
        supported_exchanges = []
        for exchange_name, exchange in exchanges.items():
            try:
                markets = exchange.load_markets()
                if pair in markets:
                    supported_exchanges.append(exchange_name)
            except Exception as e:
                logger.error(f"Erro ao carregar mercados na {exchange_name}: {e}")
        if len(supported_exchanges) >= 2:  # Requer pelo menos 2 exchanges suportando o par
            logger.info(f"Par {pair} suportado pelas exchanges: {supported_exchanges}")
            supported_pairs.append(pair)
        else:
            logger.warning(f"Par {pair} não suportado por pelo menos 2 exchanges.")
            unsupported_pairs.add(pair)  # Adiciona o par à lista de não suportados
    logger.info(f"Pares suportados: {supported_pairs}")  # Log dos pares suportados
    return supported_pairs

def get_prices(pairs):
    """Obtém preços das exchanges para os pares suportados."""
    all_prices = {}
    for pair in pairs:
        prices = {}
        for exchange_name, exchange in exchanges.items():
            try:
                ticker = exchange.fetch_ticker(pair)
                prices[exchange_name] = {
                    "last": ticker['last'],
                    "volume": ticker['quoteVolume'],  # Volume 24h
                }
                logger.info(f"Preço obtido na {exchange_name}: {ticker['last']} para o par {pair}")
            except Exception as e:
                logger.error(f"Erro ao obter preço na {exchange_name} para o par {pair}: {e}")
                prices[exchange_name] = None
        all_prices[pair] = prices
    logger.info(f"Preços obtidos: {all_prices}")  # Log dos preços obtidos
    return all_prices

def calculate_arbitrage(prices):
    """Calcula oportunidades de arbitragem."""
    global transaction_history
    results = []
    for pair, pair_prices in prices.items():
        valid_prices = {k: v for k, v in pair_prices.items() if v is not None and v['last'] is not None}
        
        # Verifica se há preços válidos tanto na Binance quanto em outras exchanges
        binance_prices = valid_prices.get("binance")
        other_exchanges_prices = {k: v for k, v in valid_prices.items() if k != "binance"}
        
        if not binance_prices or not other_exchanges_prices:
            logger.warning(f"Par {pair} não suportado por Binance ou outras exchanges.")
            continue
        
        # Define a Binance como exchange de venda
        sell_exchange = "binance"
        sell_price = binance_prices['last']
        
        # Encontra a melhor exchange para compra (menor preço)
        buy_exchange = min(other_exchanges_prices, key=lambda x: other_exchanges_prices[x]['last'])
        buy_price = other_exchanges_prices[buy_exchange]['last']
        
        # Aplica taxa de transação e derrapagem
        adjusted_buy_price = buy_price * (1 + transaction_fee + slippage)
        adjusted_sell_price = sell_price * (1 - transaction_fee - slippage)
        
        # Calcula o ROI ajustado
        roi = ((adjusted_sell_price - adjusted_buy_price) / adjusted_buy_price) * 100 if adjusted_buy_price > 0 else 0
        
        # Calcula o spread médio
        avg_price = sum(p['last'] for p in valid_prices.values()) / len(valid_prices)
        spread = (sell_price - buy_price) / avg_price * 100 if avg_price > 0 else 0
        
        logger.info(f"Par: {pair}, Compra: {buy_exchange} (${buy_price}), Venda: {sell_exchange} (${sell_price}), ROI: {roi:.2f}%, Spread: {spread:.2f}%")
        
        # Filtra apenas oportunidades com ROI acima da margem mínima
        if roi >= min_profit_margin * 100:
            # Calcula o valor total da operação
            usd_operation_value = fixed_investment * (1 + roi / 100)
            
            results.append({
                "pair": pair,
                "buy_exchange": buy_exchange,
                "buy_price": buy_price,
                "sell_exchange": sell_exchange,
                "sell_price": sell_price,
                "roi": roi,
                "spread": spread,
                "avg_price": avg_price,
                "usd_operation_value": usd_operation_value,  # Valor total da operação em USD
            })
            
            # Registra a transação
            transaction = {
                "pair": pair,
                "buy_exchange": buy_exchange,
                "buy_price": buy_price,
                "sell_exchange": sell_exchange,
                "sell_price": sell_price,
                "roi": roi,
                "spread": spread,
                "avg_price": avg_price,
                "usd_operation_value": usd_operation_value,  # Valor total da operação em USD
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            transaction_history.append(transaction)
    
    logger.info(f"Resultados de arbitragem: {results}")  # Log dos resultados
    return results

@app.route('/')
def index():
    """Rota principal que renderiza o dashboard."""
    return render_template('index.html')

@app.route('/api/get_data')
def get_data_api():
    """API para fornecer os dados em tempo real."""
    pairs = get_supported_pairs(initial_pairs)
    prices = get_prices(pairs)
    results = calculate_arbitrage(prices)
    
    # Simulação de dados (caso não haja resultados reais)
    if not results:
        logger.warning("Nenhuma oportunidade de arbitragem encontrada. Usando dados simulados.")
        results = [
            {
                "pair": "ETH/USDT",
                "buy_exchange": "kraken",
                "buy_price": 3000.0,
                "sell_exchange": "binance",
                "sell_price": 3020.0,
                "roi": 0.67,
                "spread": 0.45,
                "avg_price": 3010.0,
                "usd_operation_value": 100.67,
            }
        ]
    
    # Calcula o desempenho geral com base no histórico de transações
    total_roi = sum(tx["roi"] for tx in transaction_history) if transaction_history else 0
    total_usd_operations = sum(tx["usd_operation_value"] for tx in transaction_history) if transaction_history else 0
    
    performance = {
        "total_roi": total_roi,
        "total_usd_operations": total_usd_operations,  # Total de operações em USD
    }
    logger.info(f"Dados enviados pela API: results={results}, performance={performance}")
    return jsonify({
        "results": results,
        "performance": performance,
        "transaction_history": transaction_history,
    })

if __name__ == '__main__':
    app.run(debug=True)