from Models import OrderBook

import zmq
import json
import sys
from Models import OrderBook

def run_exchange():

    ctx = zmq.Context()

    pull_sock = ctx.socket(zmq.PULL)
    pull_sock.bind("tcp://127.0.0.1:5555")
    
    # market data socket
    pub_sock = ctx.socket(zmq.PUB)
    pub_sock.bind("tcp://127.0.0.1:5556")

    # execution socket
    exec_socket = ctx.socket(zmq.PUB)
    exec_socket.bind("tcp://127.0.0.1:5557")

    # analytics socket
    analytics_socket = ctx.socket(zmq.PUB)
    analytics_socket.bind("tcp://127.0.0.1:5558")
    
    poller = zmq.Poller()
    poller.register(pull_sock, zmq.POLLIN)

    book = OrderBook()
    
    print("MATCHING ENGINE LIVE | Listening on :5555 | Publishing on :5556")
    
    orders_received = 1

    while True:
        events = dict(poller.poll())

        if pull_sock in events:
            while True:
                try:
                    order_data = pull_sock.recv_json(flags=zmq.NOBLOCK) 
                    book.parse_order(order_data)
                    
                    ## for debugging: to show that orders hitting the exchange are immediately processed 
                    ## (ie minimal execution latency)
                    # print("orders sent", order_data['orders_sent'], "orders received", orders_received)

                    analytics_snapshot = book.analytics_snapshot 

                    exec_reports = book.output_exec_reports()
                    if exec_reports:
                        for report in exec_reports:
                            topic = report['agent_id']
                            exec_socket.send_string(f"{topic} {json.dumps(report)}")
                    book.exec_reports = []

                    if analytics_snapshot:
                        analytics_socket.send_json(analytics_snapshot)
                        book.analytics_snapshot = None

                    # for debugging: to show that orders hitting the exchange are immediately processed
                    if order_data: orders_received += 1

                except zmq.Again:
                    break

            bid_vol, ask_vol = book.get_book_vols()

            market_snapshot = {
                "mid": book.to_price(book.mid),
                "best_bid": book.to_price(book.best_bid()),
                "best_ask": book.to_price(book.best_ask()),
                "bid_vol": int(bid_vol),
                "ask_vol": int(ask_vol),
                "orders": int(book.order_id),
                "seq_id": int(book.seq_number),
                "reject/cancel rate": int(book.order_id) / int(book.seq_number)
            }
            
            pub_sock.send_json(market_snapshot)

if __name__ == "__main__":
    try:
        run_exchange()
    except KeyboardInterrupt:
        print("\nExchange Shutting Down.")