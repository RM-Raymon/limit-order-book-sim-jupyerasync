from PyQt6 import QtWidgets, QtCore, QtGui
import numpy as np
import zmq
import zmq.asyncio
import asyncio
import sys
from Models import Analytics

analytics = Analytics()

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class BlotterWindow(QtWidgets.QMainWindow):
    def __init__(self, port="5558"):
        super().__init__()
        self.setWindowTitle("Trade Analytics Blotter")
        self.resize(800, 500)

        # UI Setup
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Side", "Qty", "Avg Price", "Slippage", "Impact", "Penetration", "Fill %"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.setCentralWidget(self.table)

        # ZMQ Setup
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.connect(f"tcp://localhost:{port}")
        self.socket.setsockopt_string(zmq.SUBSCRIBE, "")
        self.socket.setsockopt(zmq.RCVHWM, 50) # Buffer a few if we lag

        # Timer to poll data
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.poll_data)
        self.timer.start(50) # 20Hz update rate

    def poll_data(self):
        try:
            while True:  # Process all pending messages
                analytics_json = self.socket.recv_json(flags=zmq.NOBLOCK)
                
                if not analytics_json:
                    continue

                analytics_data = analytics.log_trade(analytics_json)
                self.add_row(analytics_data)
        except zmq.Again:
            pass

    def add_row(self, data):
        self.table.insertRow(0)
        
        order_id = str(data.get('order_id', '---'))
        self.table.setItem(0, 0, QtWidgets.QTableWidgetItem(order_id))

        # 1. Side with Color Coding
        side = str(data.get('side', 'N/A')).upper()
        side_item = QtWidgets.QTableWidgetItem(side)
        if side == "BUY":
            side_item.setForeground(QtGui.QColor("green"))
        elif side == "SELL":
            side_item.setForeground(QtGui.QColor("red"))
        self.table.setItem(0, 1, side_item)

        # 2. Qty & 3. Price
        self.table.setItem(0, 2, QtWidgets.QTableWidgetItem(f"{data.get('filled_qty', 0)}"))
        self.table.setItem(0, 3, QtWidgets.QTableWidgetItem(f"{data.get('avg_price', 0):.2f}"))
        
        # 4. Slippage 
        slip_val = data.get('slippage', 0)
        slip_item = QtWidgets.QTableWidgetItem(f"{slip_val:.4f}")
        if abs(slip_val) > 0.10: 
            slip_item.setBackground(QtGui.QColor(200, 0, 0, 150))
        self.table.setItem(0, 4, slip_item)
        
        # 5. Impact, 6. Penetration, 7. Fill %
        self.table.setItem(0, 5, QtWidgets.QTableWidgetItem(f"{data.get('impact', 0):.4f}"))
        self.table.setItem(0, 6, QtWidgets.QTableWidgetItem(f"{data.get('book_penet', 0):.1f}"))
        
        fill_pct = data.get('fill_ratio', 0) * 100
        self.table.setItem(0, 7, QtWidgets.QTableWidgetItem(f"{fill_pct:.1f}%"))

if __name__ == "__main__":
    # 1. Create the application instance
    app = QtWidgets.QApplication(sys.argv)
    
    # 2. Initialize your window
    # The QTimer inside starts calling poll_data() immediately
    window = BlotterWindow()
    window.show()
    
    # 3. Start the event loop (this keeps the script running)
    sys.exit(app.exec())