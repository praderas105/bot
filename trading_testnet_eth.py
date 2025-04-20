from binance.client import Client
import time
import matplotlib.pyplot as plt
import requests

# -------- Configuración de claves y conexión a Testnet --------
# Inserta tus claves API del Testnet (mantenlas en privado)
api_key = 'ZbNp855k1jeg3kEm8ib8xIbDpxgBvwo5DF8MhAlJVSo3K88OMsZ6icqZCbyqZ2la'
api_secret = 'GXapMvfEGLHOFyFlkaJIH1kI3AelA17t1ruWCrJGA4KLoVqjrzbmoGdDYUqCdCVS'
client = Client(api_key, api_secret, testnet=True)

# -------- Parámetros de la estrategia --------
commission_rate = 0.001         # Tasa de comisión por operación
profit_target = 0.1             # Objetivo de ganancia grupal (10%)
spread_percent = 0.002          # Spread porcentual simulado en la ejecución
latency_steps = 0             # Latencia (se deja en 0 para simplificar)
umbral_tercero = -0.10         # Umbral para detectar desequilibrio y escalar la posición
stop_loss_individual = -0.15   # Umbral de pérdida individual (15%)
take_profit_individual = 0.01   # Umbral de ganancia individual (1%) CAMBIADO a 1% (0.01)
balance_inicial = 10000.0      # Balance inicial simulado

# -------- Funciones auxiliares --------
def precio_ejecucion(tipo, price, spread_percent):
    """
    Calcula el precio de ejecución ajustado según el spread.
    Para 'buy' se aumenta el precio; para 'sell', se disminuye.
    """
    if tipo == 'buy':
        return price * (1 + spread_percent / 2)
    else:
        return price * (1 - spread_percent / 2)

def calcular_retorno(pos, current_price):
    """
    Calcula el retorno porcentual de una posición dado el precio actual.
    """
    try:
        if pos['type'] == 'buy':
            return (current_price - pos['executed_price']) / pos['executed_price']
        else:
            return (pos['executed_price'] - current_price) / pos['executed_price']
    except ZeroDivisionError:
        return 0.0

def cerrar_posicion(pos, current_price, commission_rate):
    """
    Calcula el PnL (ganancia/pérdida) al cerrar una posición y descuenta la comisión.
    """
    ret = calcular_retorno(pos, current_price)
    if pos['type'] == 'buy':
        pnl = (current_price - pos['executed_price']) * pos['qty']
    else:
        pnl = (pos['executed_price'] - current_price) * pos['qty']
    commission = commission_rate * current_price * pos['qty']
    pnl -= commission
    return pnl, ret

def obtener_precio(symbol="ETHUSDT"):
    """
    Obtiene el precio actual del símbolo indicado desde el Testnet.
    En caso de timeout, reintenta la operación después de 2 segundos.
    """
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except requests.exceptions.ReadTimeout:
        print(f"Timeout al obtener precio de {symbol} - reintentando en 2 segundos...")
        time.sleep(2)
        return obtener_precio(symbol)

# -------- Función principal de trading en Testnet --------
def trading_testnet():
    balance = balance_inicial
    balance_history = [balance]
    prices_history = []
    scaling_executed = False

    # Obtener el precio inicial de ETHUSDT
    initial_price = obtener_precio("ETHUSDT")
    prices_history.append(initial_price)
    print(f"Precio inicial de ETHUSDT: {initial_price:.2f}")

    # Apertura inicial: posiciones opuestas (buy y sell) en el precio inicial
    active_positions = [
        {
            'type': 'buy',
            'entry': initial_price,
            'qty': 1,
            'executed_price': precio_ejecucion('buy', initial_price, spread_percent)
        },
        {
            'type': 'sell',
            'entry': initial_price,
            'qty': 1,
            'executed_price': precio_ejecucion('sell', initial_price, spread_percent)
        }
    ]
    
    step = 1
    try:
        while True:
            # Obtener precio actual de ETHUSDT
            current_price = obtener_precio("ETHUSDT")
            prices_history.append(current_price)
            print(f"\n[Paso {step}] Precio actual de ETHUSDT: {current_price:.2f}")

            # 1. Escalado de posición: si hay desequilibrio y una posición supera el take profit, se escala
            if len(active_positions) == 2 and not scaling_executed:
                retornos = [calcular_retorno(pos, current_price) for pos in active_positions]
                if min(retornos) < umbral_tercero and max(retornos) > take_profit_individual:
                    perdedora_idx = retornos.index(min(retornos))
                    tipo_nueva = active_positions[perdedora_idx]['type']
                    new_pos = {
                        'type': tipo_nueva,
                        'entry': current_price,
                        'qty': 1,
                        'executed_price': precio_ejecucion(tipo_nueva, current_price, spread_percent)
                    }
                    active_positions.append(new_pos)
                    scaling_executed = True
                    print(f"[Paso {step}] Escalado: Se añadió posición '{tipo_nueva}' a {current_price:.2f}.")

            # 2. Evaluar y cerrar posiciones individualmente (Take Profit o Stop Loss)
            nuevas_posiciones = []
            for pos in active_positions:
                pnl, ret = cerrar_posicion(pos, current_price, commission_rate)
                if ret >= take_profit_individual:
                    balance += pnl
                    print(f"[Paso {step}] Cierre (Take Profit): {pos['type']} a {current_price:.2f}, Retorno: {ret:.2%}, PnL = $ {pnl:.2f}")
                elif ret <= stop_loss_individual:
                    balance += pnl
                    print(f"[Paso {step}] Cierre (Stop Loss): {pos['type']} a {current_price:.2f}, Retorno: {ret:.2%}, PnL = $ {pnl:.2f}")
                else:
                    nuevas_posiciones.append(pos)
            active_positions = nuevas_posiciones

            # 3. Cierre grupal: si la ganancia combinada de las posiciones supera el profit_target
            if active_positions:
                pnl_grupal = sum(cerrar_posicion(pos, current_price, commission_rate)[0] for pos in active_positions)
                if pnl_grupal >= profit_target:
                    balance += pnl_grupal
                    print(f"[Paso {step}] Cierre grupal: Ganancia combinada de $ {pnl_grupal:.2f} a {current_price:.2f}.")
                    active_positions = []
                    scaling_executed = False
                    # Reapertura de posiciones opuestas en el precio actual
                    active_positions.append({
                        'type': 'buy',
                        'entry': current_price,
                        'qty': 1,
                        'executed_price': precio_ejecucion('buy', current_price, spread_percent)
                    })
                    active_positions.append({
                        'type': 'sell',
                        'entry': current_price,
                        'qty': 1,
                        'executed_price': precio_ejecucion('sell', current_price, spread_percent)
                    })

            balance_history.append(balance)
            print(f"[Paso {step}] Balance actual: $ {balance:.2f}")
            step += 1
            time.sleep(5)  # Pausa de 5 segundos entre iteraciones
    except KeyboardInterrupt:
        print("\nEjecución detenida por el usuario.")

    return balance, balance_history, prices_history

# -------- Función para visualizar los resultados --------
def visualizar_resultados(prices_history, balance_history):
    plt.figure(figsize=(12, 8))
    
    plt.subplot(2, 1, 1)
    plt.plot(prices_history, label="Precio de ETHUSDT")
    plt.title("Evolución del Precio de ETHUSDT")
    plt.xlabel("Pasos")
    plt.ylabel("Precio")
    plt.legend()
    
    plt.subplot(2, 1, 2)
    plt.plot(balance_history, label="Balance de la Cuenta", color="green")
    plt.title("Evolución del Balance de la Cuenta")
    plt.xlabel("Pasos")
    plt.ylabel("Balance ($)")
    plt.legend()
    
    plt.tight_layout()
    plt.show()

# -------- Ejecución del programa de trading en Testnet --------
if __name__ == '__main__':
    final_balance, balance_history, prices_history = trading_testnet()
    visualizar_resultados(prices_history, balance_history)
    print(f"Balance final: $ {final_balance:.2f}")
