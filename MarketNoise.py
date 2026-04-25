import zmq
import time
import random
import numpy as np
from Models import MarketNoise
from functools import partial

def run_trader():
    ## setup sockets
    context = zmq.Context()

    # PUSH sends orders TO the exchange
    push_sock = context.socket(zmq.PUSH)
    push_sock.connect("tcp://127.0.0.1:5555")

    # Subscribe to Market Data from Exchange
    sub_sock = context.socket(zmq.SUB)
    sub_sock.connect("tcp://127.0.0.1:5556")
    sub_sock.setsockopt_string(zmq.SUBSCRIBE, "") # Listen to all updates

    market_noise = MarketNoise()

    print("Market noise is being generated, orders sent to :5555")

    q_funcs = {
        "limit": lambda: max(1, int(np.random.normal(3, 1))),
        "market": lambda: max(1, int(np.random.lognormal(3, 1)))
    }

    # Initial "Dummy" data in case we haven't heard from the exchange yet
    data = {'mid': 100, 'best_bid': 99.5, 'best_ask': 100.5, 'bid_vol': 100, 'ask_vol': 100}
    
    ## for debugging: to show that orders hitting the exchange are immediately processed 
    ## (ie minimal execution latency)
    orders_sent = 1

    while True:
        # update market view
        try:
            # by default socket.recv_json() blocks the script and waits till an update arrives.
            # noblock indicates not waiting for data, so the trader keeps thinking even if there's no data
            data = sub_sock.recv_json(flags=zmq.NOBLOCK)
        except zmq.Again: # if no data is waiting, throw this error instead of waiting for another update
            pass
        
        # calibration of parameters
        s_val = market_noise.sigmoid_imbalance(data.get('bid_vol', 0), data.get('ask_vol', 0), 7)
        market_noise.calibrate_limit_orders(s_val, 0.6, 0.5, 7)
        market_noise.calibrate_market_orders(s_val, 0.1, 1.5, 7)
        market_noise.calibrate_cancels(s_val, 0.1, 2, 7)
        market_noise.calibrate_probabilities()
        
        # timing: poisson / exponential
        total_lambda = sum(market_noise.lambdas)
        dt = np.random.exponential(1 / total_lambda)
        time.sleep(max(dt, 1e-9))

        event_key = market_noise.sample_probability()

        q_type = "market" if event_key[0] == "m" else "limit"
        quantity = int(q_funcs[q_type]())

        side = "buy" if event_key[-3] == "b" else "sell"
        
        price = round(float(market_noise.sample_price(data.get('mid'), data.get('best_bid'), data.get('best_ask'), side)), 2) 
        
        # Send the order to the exchange
        # need generalisation across market and limit orders in the receiver
        push_sock.send_json({"agent_id": market_noise.agent_id,
                             "order_id": None,
                             "orders_sent": orders_sent,
                             "type": event_key,
                             "side": side,
                             "quantity": quantity,
                             "price": price})

        ## for debugging: to show that orders hitting the exchange are immediately processed 
        ## (ie minimal execution latency). Muted because printing is computationally expensive
        orders_sent += 1
        # print(orders_sent, price)

        #time.sleep(1)

if __name__ == "__main__":
    run_trader()