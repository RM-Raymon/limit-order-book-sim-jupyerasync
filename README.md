# Limit order book simulator

This project is aimed at building a simulated trading environment, where I can build and test market making strategies in order to quantify:

- Inclusion of a market maker vs without
- The efficiency of various levers in market making strategy 

#### Project phases

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
- Bugfix MarketMaker module
- Analytics for execution metrics to quantify impact of live market maker operating on the exchange.
- Build out further agents that execute varied strategies on the book.

 
