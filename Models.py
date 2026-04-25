from functools import partial
import random
import pandas as pd
import numpy as np
import copy
from collections import deque, defaultdict
from sortedcontainers import SortedDict
from abc import ABC, abstractmethod

class Order(ABC):
    def __init__(self, side, quantity, order_id, agent_id, price):
        self.side = side
        self.init_quantity = quantity
        self.quantity = quantity
        self.price = price
        self.order_id = order_id
        self.agent_id = agent_id
        self.fill_prices = []
        self.fill_quantities = []

    @abstractmethod
    def get_details(self):
        pass

    @abstractmethod
    def get_type(self):
        pass

    def copy(self):
        return copy.deepcopy(self)
        
    def get_side(self):
        return self.side
    def get_quantity(self):
        return self.quantity
    def get_orderid(self):
        return self.orderid

class LimitOrder(Order):
    def __init__(self, side, quantity, order_id, agent_id, price):
        super().__init__(side, quantity, order_id, agent_id, price)
    def get_type(self):
        return f"Limit"
    def get_price(self):
        return self.price
    def get_details(self):
        return f"Limit {self.side} order at {self.price} of {self.quantity}"

class MarketOrder(Order):
    def __init__(self, side, quantity, order_id, agent_id, price = None):
        super().__init__(side, quantity, order_id, agent_id, price=None)
    def get_type(self):
        return f"Market"
    def get_details(self):
        return f"Market {self.side} order of {self.quantity}" 

class OrderFactory:
    @staticmethod        
    def create_market_order(side, quantity, order_id, agent_id):
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")
        if side.upper() not in ["BUY", "SELL"]:
            raise ValueError("Side must be either buy or sell.")
        return MarketOrder(side, quantity, order_id, agent_id)
    
    @staticmethod
    def create_limit_order(side, quantity, order_id, agent_id, price):
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")
        if price <= 0:
            raise ValueError("Price must be greater than zero.")
        if side.upper() not in ["BUY", "SELL"]:
            raise ValueError("Side must be either buy or sell.")
        return LimitOrder(side, quantity, order_id, agent_id, price)


class Node:
    def __init__(self, order = None):
        self.stored_order = order
        self.prev = None
        self.next = None

        # list index stored to facilitate O(1) cancels of random MarketNoise orders which do not track order_id.
        # when orders are fully filled, this list_index will be used to pop the node from the list 
        self.list_index = None

class OrderQueue:
    def __init__(self):
        # initialise markers for the starting node and ending node
        # head node and tail node will hold no orders
        self.head = Node()
        self.tail = Node()
        self.head.next = self.tail
        self.tail.prev = self.head

        self.total_volume = 0
        self.count = 0
        self.last_order = None

        # Node list to facilitate O(1) cancels of random MarketNoise orders which do not track order_id.
        self.node_list = []

    def remove_node(self, node):
        if not node or node.stored_order is None:
            print(f"Removal failed. Order not found")
            return

        index = node.list_index
        quantity = node.stored_order.quantity
        
        node.prev.next, node.next.prev = node.next, node.prev

        if index is not None:
            self.node_list[index] = self.node_list[-1]
            self.node_list[index].list_index = index
            self.node_list.pop()

        self.total_volume -= quantity
        self.count -= 1

        node.stored_order, node.list_index = None, None
        node.prev, node.next = None, None

    def add_order(self, order):
        new_node = Node(order)

        # access node before tail node
        last_real_node = self.tail.prev
        new_node.next = self.tail
        new_node.prev = last_real_node
        last_real_node.next = new_node
        self.tail.prev = new_node

        self.total_volume += order.quantity
        self.count += 1

        return new_node

    def add_order_MN(self, order):
        new_node = self.add_order(order)
        new_node.list_index = len(self.node_list)
        self.node_list.append(new_node)

    def fill_order(self, fill_quantity):
        if self.total_volume == 0:
            print(f'Queue is empty. Unable to fill')
            return
        if fill_quantity > self.head.next.stored_order.quantity:
            print(f'Sitting order has insufficient quantity to fill.')
            
        self.head.next.stored_order.quantity -= fill_quantity
        self.total_volume -= fill_quantity

        # fully filled logic
        if self.head.next.stored_order.quantity == 0:
            self.remove_node(self.head.next)

    def cancel_index(self, index):
        if index > len(self.node_list) - 1:
            print(f"Cancellation failed. Index out of range")
            return

        node = self.node_list[index]
        order_id = node.stored_order.order_id
        self.remove_node(node)
        return order_id

class OrderBook:
    def __init__(self, mid=100):

        self.bids = SortedDict()
        self.asks = SortedDict()
        self.active_orders = {}
        self.tick_size = 0.01
        
        self.mid = self.to_tick(mid)
        self.last_valid_spread = self.to_tick(self.tick_size * 2)
        self.last_exec_price = None
        self.order_id = 1
        self.seq_number = 1
        self.book_vols = {"bids":0,
                          "asks":0}

        self.analytics = Analytics()
        self.order_factory = OrderFactory()
        self.analytics_snapshot = None
        self.exec_reports = []
    
    def best_bid(self):
        """
        Returns best bid
        """
        return self.bids.peekitem(-1)[0] if self.bids else None

    def best_ask(self):
        """
        Returns best ask
        """
        return self.asks.peekitem(0)[0] if self.asks else None

    def get_bid_quantity(self):
        """
        Returns volume of existing bids
        """
        return self.book_vols["bids"]

    def get_ask_quantity(self):
        """
        Returns volume of existing asks
        """
        return self.book_vols["asks"]

    def get_toplevel_quantity(self, book):
        return self.asks.peekitem(0)[1].total_volume if book == "asks" else self.bids.peekitem(-1)[1].total_volume
        
    def update_mid(self):
        """
        Updates mid price
        Note that you are operating in ticks, so no conversion needed
        """
        best_bid = self.best_bid()
        best_ask = self.best_ask()
        
        if best_bid is not None and best_ask is not None:
            self.mid = (best_bid + best_ask) / 2
            self.last_valid_spread = best_ask - best_bid
        
        elif best_bid is not None:
            if self.last_exec_price is not None:
                self.mid = (best_bid + self.last_exec_price) / 2
            else:
                self.mid = best_bid + (self.last_valid_spread / 2)
        elif best_ask is not None:
            if self.last_exec_price is not None:
                self.mid = (best_ask + self.last_exec_price) / 2
            else:
                self.mid = max(0, best_ask - (self.last_valid_spread / 2))
        else:
            pass

    def round_to_tick(self, price):
        return round(round(float(price) / self.tick_size) * self.tick_size, 2)
    
    def to_tick(self, price):
        if price is None: return None
        return round(float(price) / self.tick_size)
    
    def to_price(self, price_in_ticks):
        if price_in_ticks is None: return None
        return round(float(price_in_ticks) * self.tick_size, 2)
    
    def parse_order(self, order_data):
        event_type = order_data.get('type', '')
        side = order_data.get('side')
        qty = order_data.get('quantity', 0)
        price = self.to_tick(order_data.get('price', 0))
        agent_id = order_data.get('agent_id')
        order_id = order_data.get('order_id')

        if event_type.startswith('l'):
            return self.add_limit(side, price, qty, agent_id)
        elif event_type.startswith('m'):
            return self.market_order(side, qty, agent_id)
        elif event_type.startswith('c'):
            if order_data['order_id'] == None:
                return self.cancel_side(side)
            else:
                return self.cancel_limit(agent_id, order_id)
        else:
            print(f"Unknown order type received: {event_type}")
            return None

    def add_limit(self, side, price, qty, agent_id):
        """
        Creates a limit order dictionary and adds it to the relevant book.
        Note that prices have to be stored in ticks
        """
        order = self.order_factory.create_limit_order(side, qty, self.order_id, agent_id, price) 
        self.last_exec_price = None
        
        event = "limit"
        executed_qty = 0

        bid_before = self.best_bid()
        ask_before = self.best_ask()
        mid_before = self.mid
        order_init_qty = order.quantity
        avg_prices = []
        signed_qty = order_init_qty if side == "buy" else -order_init_qty

        ## FOR DEBUGGING ##
        try:
            best_quote_vol = self.get_toplevel_quantity("asks") if order.side == "buy" else self.get_toplevel_quantity("bids")
            book_penetration = order_init_qty / best_quote_vol
        except:
            book_penetration = None
        ## FOR DEBUGGING ##
        
        self.exec_reports.append(self.gen_exec_report(order, 0, order.price))

        if order.side == "buy":
            cross_idx = self.asks.bisect_right(order.price)
            marketable_prices = list(self.asks.keys()[:cross_idx])

            for level_price in marketable_prices:
                if order.quantity <= 0: 
                    break
                
                queue = self.asks[level_price]

                while order.quantity > 0 and queue.count > 0:
                    order_on_book_node = queue.head.next
                    order_on_book = order_on_book_node.stored_order
                    trade = min(order.quantity, order_on_book.quantity)

                    self.book_vols["asks"] -= trade
                    order.quantity -= trade
                    executed_qty += trade
                    queue.fill_order(trade)

                    avg_prices.append((level_price, trade))

                    order.fill_prices.append(level_price)
                    order.fill_quantities.append(trade)
                    order_on_book.fill_prices.append(level_price)
                    order_on_book.fill_quantities.append(trade)
                    self.exec_reports.append(self.gen_exec_report(order, trade, level_price))
                    self.exec_reports.append(self.gen_exec_report(order_on_book, trade, level_price))

                    if order_on_book.quantity == 0:
                        del self.active_orders[order_on_book.order_id]

                if queue.total_volume == 0:
                    self.asks.popitem(0)

                self.last_exec_price = level_price
                     
        else:                                      
            cross_idx = self.bids.bisect_left(order.price)
            marketable_prices = list(self.bids.keys()[cross_idx:])            

            for level_price in reversed(marketable_prices):
                if order.quantity <= 0: 
                    break
                
                queue = self.bids[level_price]
            
                while order.quantity > 0 and queue.count > 0:
                    order_on_book_node = queue.head.next
                    order_on_book = order_on_book_node.stored_order
                    trade = min(order.quantity, order_on_book.quantity)
                    
                    self.book_vols["bids"] -= trade
                    order.quantity -= trade
                    executed_qty += trade
                    queue.fill_order(trade)

                    avg_prices.append((level_price, trade))
                    
                    order.fill_prices.append(level_price)
                    order.fill_quantities.append(trade)
                    order_on_book.fill_prices.append(level_price)
                    order_on_book.fill_quantities.append(trade)
                    self.exec_reports.append(self.gen_exec_report(order, trade, level_price))
                    self.exec_reports.append(self.gen_exec_report(order_on_book, trade, level_price))

                    if order_on_book.quantity == 0:
                        del self.active_orders[order_on_book.order_id]
                        
                if queue.total_volume == 0:
                    self.bids.popitem(-1)

                self.last_exec_price = level_price

        bid_after = self.best_bid()
        ask_after = self.best_ask()

        self.update_mid()
        mid_intermed = self.mid
        
        if order.quantity > 0:
            target_book = self.bids if order.side == "buy" else self.asks
            if order.price not in target_book:
                target_book[order.price] = OrderQueue()
            if order.agent_id[:2] == "MN": target_book[order.price].add_order_MN(order)
            else: target_book[order.price].add_order(order)
            self.book_vols["bids" if order.side == "buy" else "asks"] += order.quantity
            self.active_orders[order.order_id] = target_book[order.price].tail.prev

        self.update_mid()
        
        if executed_qty:

            exec_order_size = sum(exec_price * exec_qty for exec_price, exec_qty in avg_prices)
            total_exec_qty = sum(exec_qty for _, exec_qty in avg_prices)
            avg_price = exec_order_size / total_exec_qty if total_exec_qty != 0 else 0
        
            self.output_analytics(self.order_id, event, order.side, order_init_qty, executed_qty, avg_price, 
                                  bid_before, bid_after, ask_before, ask_after, mid_before, mid_intermed, signed_qty, book_penetration)
        else:
            self.analytics_snapshot = None        
        
        self.order_id += 1
        
    def market_order(self, side, qty, agent_id):
        """
        Executed market order against existing books
        Returns a list of trades done
        """
        book = self.asks if side == "buy" else self.bids
        self.last_exec_price = None
        
        if not book:
        #    print("Market order rejected. Insufficient liquidity")
            return

        order = self.order_factory.create_market_order(side, qty, self.order_id, agent_id)
        
        event = "market"
        mid_before = self.mid
        order_init_qty = order.quantity
        signed_qty = order_init_qty if side == "buy" else -order_init_qty
        bid_before = self.best_bid()
        ask_before = self.best_ask()

        ## FOR DEBUGGING ##
        try:
            best_quote_vol = self.get_toplevel_quantity("asks") if order.side == "buy" else self.get_toplevel_quantity("bids")
            book_penetration = order_init_qty / best_quote_vol
        except:
            book_penetration = None
        ## FOR DEBUGGING ##
        
        trades = []

        executed_qty = 0
        avg_prices = []
        
        if side == "sell":
            while order.quantity > 0 and self.bids:
                level_price, queue = self.bids.peekitem(-1)
                while queue.count > 0 and order.quantity > 0:
                    order_on_book_node = queue.head.next
                    order_on_book = order_on_book_node.stored_order
                    trade = min(order_on_book.quantity, order.quantity)
    
                    queue.fill_order(trade)
                    self.book_vols["bids"] -= trade
                    order.quantity -= trade           
                    executed_qty += trade
                    
                    avg_prices.append((level_price , trade))
                    
                    order.fill_prices.append(level_price)
                    order.fill_quantities.append(trade)
                    order_on_book.fill_prices.append(level_price)
                    order_on_book.fill_quantities.append(trade)
                    self.exec_reports.append(self.gen_exec_report(order, trade, level_price))
                    self.exec_reports.append(self.gen_exec_report(order_on_book, trade, level_price))
                                        
                    if order_on_book.quantity == 0:
                        del self.active_orders[order_on_book.order_id]
                            
                if queue.total_volume == 0:
                    self.bids.popitem(-1)

                self.last_exec_price = level_price

        elif side == "buy":
            while order.quantity > 0 and self.asks:
                level_price, queue = self.asks.peekitem(0)
                while queue.count > 0 and order.quantity > 0:
                    order_on_book_node = queue.head.next
                    order_on_book = order_on_book_node.stored_order
                    
                    trade = min(order_on_book.quantity, order.quantity) 

                    queue.fill_order(trade)
                    order.quantity -= trade
                    executed_qty += trade

                    avg_prices.append((level_price , trade))

                    order.fill_prices.append(level_price)
                    order.fill_quantities.append(trade)
                    order_on_book.fill_prices.append(level_price)
                    order_on_book.fill_quantities.append(trade)
                    self.exec_reports.append(self.gen_exec_report(order, trade, level_price))
                    self.exec_reports.append(self.gen_exec_report(order_on_book, trade, level_price))
                                        
                    if order_on_book.quantity == 0:
                        del self.active_orders[order_on_book.order_id]

                if queue.total_volume == 0: 
                    self.asks.popitem(0)

                self.last_exec_price = level_price
                    
        bid_after = self.best_bid()
        ask_after = self.best_ask()
        
        self.update_mid()
        mid_after = self.mid

        if executed_qty:

            exec_order_size = sum(exec_price * exec_qty for exec_price, exec_qty in avg_prices)
            total_exec_qty = sum(exec_qty for _, exec_qty in avg_prices)
            avg_price = exec_order_size / total_exec_qty if total_exec_qty != 0 else 0
            
            self.output_analytics(self.order_id, event, order.side, order_init_qty, executed_qty, avg_price, 
                                  bid_before, bid_after, ask_before, ask_after, mid_before, mid_after, signed_qty, book_penetration)

        else:
            self.analytics_snapshot = None
        
        self.order_id += 1

    def cancel_limit(self, agent_id, order_id):
        order_node = self.active_orders.get(order_id)
        order = order_node.stored_order

        if not order:
            print(f"Order was not found. Order_id: {order_id}")
            # The order was already filled or moved.
            # Send a message so the MM knows to unlock the side.
            self.exec_reports.append({
                "agent_id": agent_id,
                "order_id": order_id,
                "status": "REJECTED", # Or "NOT_FOUND"
                "reason": "Order already matched or missing"
            })
            return
        if agent_id != order.agent_id:
            print(f"Mismatch in agent_id.")
            return

        book = self.bids if order.side == "buy" else self.asks
        price_level = book.get(order.price)
        if price_level.count > 0:
            price_level.remove_node(order_node)
            if price_level.count == 0:
                del book[order.price]
            
            # I just need the cancellation confirmation for now
            # take note that the executed_qty in the CANCEL exec_report will be inaccurate
            # since the order is added from the 
            self.exec_reports.append(
                self.gen_exec_report(order, 0, 0, cancel = True))
            
            del self.active_orders[order_id]
            self.update_mid()
        else:
            print("Error, empty queue selected.")

    def cancel_side(self, side):
        """
        Cancels a random order on a specific side of the order book.
        Used to implement market noise cancellations, not specific agents.
        """
        book = self.bids if side == "buy" else self.asks
        if not book: return
    
        price = np.random.choice(list(book.keys()))
        queue = book[price]
        order_id = None

        if queue.count > 1:
            idx = random.randint(0, len(queue.node_list) - 1)
            order_id = queue.cancel_index(idx)
            del self.active_orders[order_id]
        elif queue.count == 1:
            order_id = queue.cancel_index(0)
            del self.active_orders[order_id]
        elif queue.count == 0:
            print("Error. empty queue selected.")
        if queue.total_volume == 0:
            del book[price]
        
        self.update_mid()

    def sample_price(self, side):
        """
        Samples the order book. Used to control the distribution of incoming limit orders around the current book.
        Note that you are operating in ticks internally
        Think that this should be put under a separate market class.
        """
        mid = self.mid
        best_bid_ticks = self.best_bid()
        best_ask_ticks = self.best_ask()
        
        spread = (best_ask_ticks - best_bid_ticks) if best_ask_ticks and best_bid_ticks else 100

        if np.random.rand() < 0.02:
            if side == "buy" and best_ask_ticks:
                return self.to_price(best_ask_ticks)  # crosses
            elif side == "sell" and best_bid_ticks:
                return self.to_price(best_bid_ticks)

        # draw from geometric distribution. Returns the number of trials it took to get first success given probability p.
        # note that this is in ticks
        offset = min(np.random.geometric(0.2), 10) / 0.01

        buffer = 20
        
        if side == "buy":
            price_in_ticks = max(mid - (offset + buffer), 100 * self.tick_size)
        else:
            price_in_ticks = max(mid + (offset + buffer), 100 * self.tick_size)
        return self.to_price(price_in_ticks)

    def get_book_vols(self, depth=2):
        
        bid_prices = self.bids.keys()[-depth:][::-1]
        ask_prices = self.asks.keys()[:depth]
        
        bid_vol = sum(self.bids[p].total_volume for p in bid_prices)
        ask_vol = sum(self.asks[p].total_volume for p in ask_prices)
            
        return bid_vol, ask_vol
    
    def output_analytics(self, order_id, event, side, order_init_qty, 
                         executed_qty, avg_price, bid_before, bid_after, ask_before, ask_after, mid_before, mid_after, signed_qty, book_penetration):
        self.analytics_snapshot = {"order_id": order_id,
                "event": event,
                 "side": side,
                 "order_init_qty": order_init_qty,
                  "executed_qty": executed_qty,
                  "avg_price": self.to_price(avg_price),
                  "bid_before": self.to_price(bid_before),
                  "bid_after": self.to_price(bid_after),
                  "ask_before": self.to_price(ask_before),
                  "ask_after": self.to_price(ask_after),
                  "mid_before": self.to_price(mid_before),
                  "mid_after": self.to_price(mid_after),
                  "signed_qty": signed_qty,
                  "book_penetration": book_penetration}

    def gen_exec_report(self, order, executed_qty, avg_fill_price, cancel = False):
        total_value = sum(p * q for p, q in zip(order.fill_prices, order.fill_quantities))
        total_qty = sum(order.fill_quantities)
        overall_avg_fill = total_value / total_qty if total_qty > 0 else 0
        status = None

        if cancel:
            status = "CANCELLED"
        elif order.quantity == 0:
            status = "FULLY FILLED"
        elif order.quantity == order.init_quantity:
            status = "OPEN"
        else:
            status = "PARTIALLY FILLED"

        return {
            "agent_id": order.agent_id,
            "order_id": order.order_id,
            "side": order.side,
            "status": status,
            "price": self.to_price(order.price),
            "order_init_qty": order.init_quantity,
            "last_exec_qty": executed_qty,
            "remaining_qty": order.quantity,
            "avg_fill_price": self.to_price(avg_fill_price),
            "overall_avg_fill": self.to_price(overall_avg_fill)
        }
    
    def output_exec_reports(self):
        return self.exec_reports
        
    def trades_df(self):
        return pd.DataFrame(self.analytics.records)
    
class Analytics:
    def __init__(self):
        self.records = []
        self.tick_size = 0.01

    def to_tick(self, price):
        return round(price / self.tick_size)
    
    def to_price(self, price_in_ticks):
        return round(price_in_ticks * self.tick_size, 2)
        
    def log_trade(self, analytics_data):
        side = analytics_data.get('side')
        if side == "buy":
            direction = 1
        else: 
            direction = -1
        avg_price = analytics_data.get('avg_price', np.nan)
        mid_before = analytics_data.get('mid_before', np.nan) 
        mid_after = analytics_data.get('mid_after', np.nan)
        impact = direction * (mid_after - mid_before)
        init_qty = analytics_data.get('order_init_qty')
        filled_qty = analytics_data.get('executed_qty')
        data = {"order_id" : analytics_data.get('order_id'),
                "event": analytics_data.get('event'),
               "side": side,
               "init_qty": init_qty,
               "filled_qty": filled_qty,
                "fill_ratio": filled_qty / init_qty,
                "avg_price": avg_price,
                "bid_before": analytics_data.get('bid_before', np.nan),
                "bid_after": analytics_data.get('bid_after', np.nan),
                "ask_before": analytics_data.get('ask_before', np.nan),
                "ask_after": analytics_data.get('ask_after', np.nan),
                "mid_before": mid_before,
                "mid_after": mid_after,
                "slippage": direction * (avg_price - mid_before),
                "impact": impact,
                "impact per unit": impact / filled_qty if filled_qty > 0 else 0,
                "signed_qty": analytics_data.get('signed_qty'),
                "book_penet": analytics_data.get('book_penetration')
               }
        self.records.append(data)
        return data

class MarketNoise:
    def __init__(self, agent_id = "MN01"):
        self.agent_id = agent_id

    def compute_imbalance(self, bid_vol, ask_vol):
        if not bid_vol and not ask_vol: return 0
        if bid_vol + ask_vol == 0: return 0
        return (bid_vol - ask_vol) / (bid_vol + ask_vol)
    
    def sigmoid_imbalance(self, bid_vol, ask_vol, k = 7):
        return 1 / (1 + np.exp(-k * self.compute_imbalance(bid_vol, ask_vol)))

    def calibrate_limit_orders(self, s_val, mean = 0.3, scaling = 0.5, k = 7):
        self.λ_limit_buy = mean + scaling * (1 - s_val)
        self.λ_limit_sell = mean + scaling * s_val
        
    def calibrate_market_orders(self, s_val, mean = 0.1, scaling = 3, k = 7):
        self.λ_market_buy = mean + scaling * max(0, (s_val - 0.5) * 2)
        self.λ_market_sell = mean + scaling * max(0, (0.5 - s_val) * 2)

    def calibrate_cancels(self, s_val, mean = 0.2, scaling = 0.8, k = 7):
        self.λ_cancel_buy  = mean + scaling * max(0, (0.5 - s_val) * 2)
        self.λ_cancel_sell = mean + scaling * max(0, (s_val - 0.5) * 2)
    
    def calibrate_probabilities(self):
        self.events = [
            "limit_buy","limit_sell",
            "market_buy","market_sell",
            "cancel_buy","cancel_sell"
        ]
    
        self.lambdas = [
            self.λ_limit_buy, self.λ_limit_sell,
            self.λ_market_buy, self.λ_market_sell,
            self.λ_cancel_buy, self.λ_cancel_sell
        ]
        self.probs = np.array(self.lambdas) / max(sum(self.lambdas), 1e-9)
    
    def sample_probability(self):
        return np.random.choice(self.events, p=self.probs)
    
    def sample_price(self, mid, best_bid, best_ask, side):
        spread = (best_ask - best_bid) if best_ask and best_bid else 0.01

        # possibility of aggressive limit
        if np.random.rand() < 0.02:
            if side == "buy" and best_ask:
                return best_ask
            elif side == "sell" and best_bid:
                return best_bid

        offset = min(np.random.geometric(0.2), 10)
        buffer = 0.02
        
        if side == "buy":
            price = max(mid - (offset + buffer), 1)
        else:
            price = max(mid + (offset + buffer), 1)
        return price

    def limit_order(self, side, book, mean = 3, sigma = 1):
        """
        Limit orders function uses normally distributed random values for quantity
        This is to reflect the nature that limit orders are usually more consistent
        Market makers / "patient" traders often trade in standardised blocks of order sizes
        """
        if side == "buy":
            price = book.sample_price("buy")
            qty = max(1, int(np.random.normal(mean, sigma)) + 1)
            book.add_limit("buy", price, qty, self.agent_id)
        else:
            price = book.sample_price("sell")
            qty = max(1, int(np.random.normal(mean, sigma)) + 1)
            book.add_limit("sell", price, qty, self.agent_id)

    def market_order(self, side, book, mean = 3, sigma = 1):
        """
        Market orders function uses lognormally distributed random values for quantity
        In real markets, the distribution of market orders has a small mean, but wide tails
        in which massive orders from whales occasionally sweep the books
        """
        if side == "buy":
            qty = max(1, int(np.random.lognormal(mean, sigma)) + 1)
            book.market_order("buy", qty, self.agent_id)
        else:
            qty = max(1, int(np.random.lognormal(mean, sigma)) + 1)
            book.market_order("sell", qty, self.agent_id)

    def order_cancel(self, side, book):
        if side == "buy":
            book.cancel_side("buy")
        else:
            book.cancel_side("sell")
    
    def setup_events_map(self, book):
        self.events_map = {"limit_buy": partial(self.limit_order, "buy", book),
              "limit_sell": partial(self.limit_order, "sell", book),
              "market_buy": partial(self.market_order, "buy", book),
              "market_sell": partial(self.market_order, "sell", book),
              "cancel_buy": partial(self.order_cancel, "buy", book),
              "cancel_sell": partial(self.order_cancel, "sell", book)
             }