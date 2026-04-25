import zmq
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets
import numpy as np

def to_price(price_in_ticks, tick_size):
    if price_in_ticks is None: return None
    return round(float(price_in_ticks) * tick_size, 2)

tick_size = 0.01

class LiveOrderBookPlot:
    def __init__(self):
        self.context = zmq.Context()
        self.subscriber = self.context.socket(zmq.SUB)

        self.subscriber.setsockopt(zmq.RCVHWM, 1)

        self.subscriber.connect("tcp://localhost:5558")
        self.subscriber.setsockopt_string(zmq.SUBSCRIBE, "")

        # Initialize UI
        self.app = QtWidgets.QApplication([])
        self.win = pg.GraphicsLayoutWidget(show=True, title="Exchange Monitor")
        self.plot = self.win.addPlot(row=1, col=0, title="Mid-Price Real-Time")
        self.curve = self.plot.plot(pen='g')
        
        self.stats_label = self.win.addLabel(
            "System Idle...", 
            row=0, col=0, 
            justify='left', 
            color='w', 
            size='12pt'
        )

        self.prices = []
        self.max_points = 200

        # Setup Timer for updates
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(10) # in milliseconds
        
    def update(self):
        last_data = None
        while True:
            try:
                last_data = self.subscriber.recv_json(flags=zmq.NOBLOCK)
            except zmq.Again:
                break

        if last_data:
            mid_price = last_data.get('mid_after')
            
            if mid_price is not None:
                self.prices.append(mid_price)

            if len(self.prices) > self.max_points:
                self.prices.pop(0)
            
            curr_id = last_data.get('order_id', "NA")
            stats_text = (
                f"<span style='color: #00FF00; font-weight: bold;'>Total Processed (order_id): {curr_id}</span><br>"
                )
            self.stats_label.setText(stats_text)

            self.curve.setData(self.prices)

    def run(self):
        self.app.exec()

if __name__ == "__main__":
    monitor = LiveOrderBookPlot()
    monitor.run()