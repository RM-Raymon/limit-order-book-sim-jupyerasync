# Limit order book simulator

This project is aimed at building a simulated trading environment, where I can build and test market making strategies in order to explore and quantify:

- Different market making strategies
- Effects of inclusion of a basic market maker in a non-liquid market (in general, but more specifically, on execution metrics)
- Various levers in market making strategy and their efficiency 

### Project details

#### Development phases

i) Jupyter notebook: discrete time
- Building of overarching market environment, including limit orderbook and analytics collection.
- Building of simulated market noise suite.
- Bugfixing of limit orderbook matching logic via rigorous analytics collection and visualisation.
- Creation of discrete time simulation via for loops.

ii) Jupyter notebook: asyncio simulation
- Implemented asyncio infrastructure in order to have a continuous, non-blocking market environment, where the market noise and matching engine operate "independently" within the simulation.
- Key insight: Due to the existence of Python's Global Interpreter Lock (GIL), asyncio is not true concurrency, rather single-threaded concurrency. Therefore, it was necessary to take care to ensure that order processing and state updates maintained logical consistency, mimicking parallel operations despite the lack of true multi-core execution.

iii) Visual Studio Code: ZeroMQ distributed architecture
- Conceptualised in order to circumvent the limitations of Asyncio and the Python GIL and achieve true concurrency between agents and the matching engine.
- I ported the core engine from monolithic Jupyter environment to a modular implementation in VSC, utilising ZMQ to achieve true concurrency. The use of ZeroMQ bypasses the GIL by running the exchange and agents on different terminals in order to decouple their execution.
- Messaging patterns implented include: 1) PUSH-PULL for high-throughput order routing and load balancing between execution agents and the matching engine. 2) PUB / SUB for real-time broadcasting of LOB snapshots and trade data, allowing multiple downstream analytics listeners to subscribe without impacting engine latency.
- Several local ports were configured to manage the transmission of structured data, ensuring scalable communication backbone for the simulation.
- Due to the nature of ZeroMQ not being on the same terminal, class objects (such as orders, market snapshot dictionaries) cannot be passed around directly. Therefore additional helper functions had to be coded to facilitate processing of order data (e.g. parsing of JSON order data and subsequent conversion into order class), and collection and output of data (e.g. execution confirmation, analytics collection, output as market snapshots).
- Additionally, the responsibilities of the classes were reworked to more accurately reflect the relationship between a trader and the exchange (e.g. in the Jupyter version, the exchange owned the price sampling function which output a price for the MarketNoise to submit. In this distributed architecture version, the MarketNoise (and all future agents) have their own sampling functions which generates their order prices based on the latest market snapshots published by the exchange. 

#### Technical specifics

OrderBook data structure highlights:
- SortedDictionary was used for implementation of bid and ask books. SortedDicts store keys in a binary search tree enabling O(1) retrieval of top of book prices (at the cost of O(log n) additions of new queues).
- Doubly linked-list was used for implementation of order queues. Doubly linked-lists enable O(1) cancellation of orders (as opposed to using a queue or deque) while still maintaining the time priority of orders submitted to the book. The doubly linked-list was combined with a custom order quque class to store the volume in each queue explicitly, enabling O(1) retrieval of queue total volume.
- Use of dictionaries with order id as keys and pointers to the order object as values in order to facilitate O(1) lookup of existing orders (mainly for the purpose of cancellation).

Market noise logic highlights:
- Sends market, limit, and cancellation orders on both sides with respect to the current state of the market.
- Use of exponential distribution to model order arrival time.
- Samples sigmoid imbalance on books for calibration of buy / sell / cancel event probabilities to model trending prices.
- Samples current book snapshot for calculation of prices in limit order submission. The purpose is to allow flexibility for passive limit orders and aggressive limit orders. 
- Uses lognormal distribution to model order quantity for market orders in order to simulate occasional whale orders hitting the book.

#### Next steps:
- Currently working on fixing bugs in the MarketMaker module
- Analytics for execution metrics to quantify impact of live market maker operating on the exchange
- Explore possibilties for further abstraction of logic (e.g. there is a lot of repeated code in limit order matching and market order matching. To explore if there is a way work around the minute differences to abstract the matching logic into an order matching helper function).
- Build out further agents that execute varied strategies on the book

### Readme:
- Jupyter notebook (OB data simulation v1.5.ipynb): standalone simulation

1) Install all the packages in the first cell of the notebook. Run first cell of the notebook to import them into workspace.
2) Implementation of the OrderBook class is in cell 4. Implementation of MarketNoise class is in cell 6. Change parameters as desired in these cells (e.g. depth for top of book volume calculation, distribution of probabilities at which orders are sampled, distribution of quantity of orders etc.)
3) Run cells that contain implementation of the classes (cells 2 - 7)
4) Run the eighth cell to see async simulation with visualisation of mid trend.

- Distributed ZeroMQ version
1) Relevant files are:
   - Models.py: Stores augmented logic for underlying architecture (Order, Order Queues, OrderBook, Analytics, MarketNoise classes)
   - Exchange.py: File containing code that runs OrderBook class on ZeroMQ architecture
   - MarketNoise.py: File containing code that runs MarketNoise class on ZeroMQ architecture
   - Plotting.py: File that plots the live price trend for the order book based on published market snapshots
   - Blotter.py: File that outputs live most recent executed orders and their relevant analytics

2) Run Exchange.py to start up exchange
3) Run Blotter.py and Plotting.py to visualise analytics
4) Run MarketNoise.py to start the sending of orders
5) Watch the order matching process unfold on the Blotter and Plotting screens

