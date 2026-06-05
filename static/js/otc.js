// OTC Market WebSocket Handler
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Socket.IO connection with auth
    const socket = io({
        reconnection: true,
        reconnectionAttempts: 10,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        auth: {
            token: document.cookie.split('; ').find(row => row.startsWith('session='))?.split('=')[1]
        }
    });

    // Get elements
    const currentRateElement = document.getElementById('currentRate');
    const dataSourceElement = document.getElementById('dataSource');
    const callPriceElement = document.getElementById('callPrice');
    const putPriceElement = document.getElementById('putPrice');
    const selectedPairElement = document.querySelector('select[name="pair"]');
    const lastUpdateElement = document.getElementById('lastUpdate');
    const chartCanvas = document.getElementById('priceChart');
    
    // Keep track of update count and last update time
    let updateCount = 0;
    let lastUpdateTime = Date.now();
    
    // Initialize chart
    let priceChart = null;
    let chartInitialized = false;
    let updateInterval = null;

    // Initialize chart if canvas exists
    function initializeChart() {
        if (!chartCanvas) {
            console.warn('Chart canvas not found');
            return null;
        }

        try {
            // Ensure any existing chart is destroyed
            if (priceChart) {
                priceChart.destroy();
                priceChart = null;
            }

            const ctx = chartCanvas.getContext('2d');
            if (!ctx) {
                console.warn('Could not get 2D context from canvas');
                return null;
            }

            priceChart = TechnicalIndicators.initializeChart(ctx, [new Date().toLocaleTimeString()], [0]);
            chartInitialized = true;
            return priceChart;
        } catch (error) {
            console.error('Error initializing chart:', error);
            return null;
        }
    }

    // Connection handlers
    socket.on('connect', () => {
        console.log('Connected to WebSocket');
        updateStatus('Connected', 'Connected');
        if (selectedPairElement && selectedPairElement.value) {
            subscribeToPrice(selectedPairElement.value);
        }
    });

    socket.on('connect_error', (error) => {
        console.error('Connection error:', error);
        updateStatus('Connection error', 'Error');
        if (error.message === 'Not authenticated') {
            window.location.reload();
        }
    });

    socket.on('disconnect', () => {
        console.log('Disconnected from WebSocket');
        updateStatus('Disconnected', 'No connection');
    });

    // Subscribe response handler
    socket.on('subscribe_response', (response) => {
        console.log('Subscribe response:', response);
        if (response.error) {
            updateStatus('Subscription error: ' + response.error, 'Error');
        }
    });

    // Price update handler with improved error handling
    socket.on('price_update', (data) => {
        console.log('Received price update:', data);
        
        try {
            // Handle both direct data and nested data.type === 'price_update' format
            const updateData = data.type === 'price_update' ? data : data.data;
            
            if (!updateData || !updateData.rate) {
                console.warn('Received invalid price update data:', data);
                updateStatus('Invalid data', 'Error');
                return;
            }
            
            if (updateData.error) {
                console.warn('Error in price update:', updateData.error);
                updateStatus('Error: ' + updateData.error, 'Error');
                return;
            }
            
            updateDisplayWithData(updateData);
            
            // Update last update time
            const now = Date.now();
            const timeSinceLastUpdate = now - lastUpdateTime;
            lastUpdateTime = now;
            updateCount++;
            
            // Log update statistics
            if (lastUpdateElement) {
                const updateTime = new Date().toLocaleTimeString();
                lastUpdateElement.textContent = `Last update: ${updateTime} (${timeSinceLastUpdate}ms ago)`;
            }
            
            // Log successful update
            console.log('Updated display with new data:', updateData);
            console.log(`Update frequency: ${Math.round(1000 / timeSinceLastUpdate)} updates/second`);
        } catch (error) {
            console.error('Error processing price update:', error);
            updateStatus('Processing error', 'Error');
        }
    });

    // Subscribe to price updates when pair is selected
    if (selectedPairElement) {
        selectedPairElement.addEventListener('change', function() {
            const pair = this.value;
            if (pair) {
                subscribeToPrice(pair);
            }
        });

        // Initial subscription if pair is already selected
        if (selectedPairElement.value) {
            subscribeToPrice(selectedPairElement.value);
        }
    }

    function subscribeToPrice(pair) {
        console.log('Subscribing to:', pair);
        // Reset update statistics
        updateCount = 0;
        lastUpdateTime = Date.now();
        
        // Unsubscribe from previous pair if any
        if (window.currentPair) {
            console.log('Unsubscribing from:', window.currentPair);
            socket.emit('unsubscribe', { pair: window.currentPair });
        }
        
        // Subscribe to new pair
        console.log('Subscribing to new pair:', pair);
        socket.emit('subscribe', { pair: pair });
        window.currentPair = pair;
        
        // Update status
        updateStatus('Loading...', 'Fetching...');

        // Reset chart when changing pairs
        chartInitialized = false;
        if (priceChart) {
            priceChart.destroy();
            priceChart = null;
        }
    }

    function updateStatus(rate, source) {
        if (currentRateElement) {
            currentRateElement.textContent = rate;
        }
        if (dataSourceElement) {
            dataSourceElement.textContent = source;
        }
    }

    function updateDisplayWithData(data) {
        try {
            // Update current rate
            if (typeof data.rate === 'number' && !isNaN(data.rate)) {
                document.getElementById('currentRate').textContent = data.rate.toFixed(6);
                document.querySelectorAll('.current-market-price').forEach(el => {
                    el.textContent = data.rate.toFixed(6);
                });
            }

            // Update data source
            document.getElementById('dataSource').textContent = data.source || 'Real-time';

            // Update call/put prices if available
            if (typeof data.call_price === 'number' && !isNaN(data.call_price)) {
                document.getElementById('callPrice').textContent = data.call_price.toFixed(6);
            }
            if (typeof data.put_price === 'number' && !isNaN(data.put_price)) {
                document.getElementById('putPrice').textContent = data.put_price.toFixed(6);
            }

            // Update chart
            if (typeof data.rate === 'number' && !isNaN(data.rate)) {
                if (!chartInitialized) {
                    initializeChart([new Date().toLocaleTimeString()], [data.rate]);
                } else {
                    if (priceChart.data.labels.length > 100) {
                        priceChart.data.labels.shift();
                        priceChart.data.datasets[0].data.shift();
                    }
                    priceChart.data.labels.push(new Date().toLocaleTimeString());
                    priceChart.data.datasets[0].data.push(data.rate);
                    priceChart.update('none');
                }
                document.getElementById('noDataMsg').style.display = 'none';
            }

            // Update technical indicators
            if (data.indicators) {
                // RSI
                if (typeof data.indicators.rsi === 'number') {
                    const rsiElement = document.getElementById('rsiValue');
                    const rsiSignal = document.getElementById('rsiSignal');
                    if (rsiElement) rsiElement.textContent = data.indicators.rsi.toFixed(2);
                    if (rsiSignal) {
                        if (data.indicators.rsi > 70) {
                            rsiSignal.textContent = 'Overbought';
                            rsiSignal.className = 'indicator-signal bearish';
                        } else if (data.indicators.rsi < 30) {
                            rsiSignal.textContent = 'Oversold';
                            rsiSignal.className = 'indicator-signal bullish';
                        } else {
                            rsiSignal.textContent = 'Neutral';
                            rsiSignal.className = 'indicator-signal neutral';
                        }
                    }
                }

                // MACD
                if (typeof data.indicators.macd === 'number' && typeof data.indicators.macd_signal === 'number') {
                    const macdElement = document.getElementById('macdValue');
                    const macdSignal = document.getElementById('macdSignal');
                    if (macdElement) {
                        macdElement.textContent = `${data.indicators.macd.toFixed(6)} / ${data.indicators.macd_signal.toFixed(6)}`;
                    }
                    if (macdSignal) {
                        if (data.indicators.macd > data.indicators.macd_signal) {
                            macdSignal.textContent = 'Bullish';
                            macdSignal.className = 'indicator-signal bullish';
                        } else if (data.indicators.macd < data.indicators.macd_signal) {
                            macdSignal.textContent = 'Bearish';
                            macdSignal.className = 'indicator-signal bearish';
                        } else {
                            macdSignal.textContent = 'Neutral';
                            macdSignal.className = 'indicator-signal neutral';
                        }
                    }
                }

                // Bollinger Bands
                if (typeof data.indicators.bb_upper === 'number' && typeof data.indicators.bb_lower === 'number') {
                    const bbElement = document.getElementById('bbValue');
                    const bbSignal = document.getElementById('bbSignal');
                    if (bbElement) {
                        bbElement.textContent = `${data.indicators.bb_lower.toFixed(6)} - ${data.indicators.bb_upper.toFixed(6)}`;
                    }
                    if (bbSignal && typeof data.rate === 'number') {
                        if (data.rate > data.indicators.bb_upper) {
                            bbSignal.textContent = 'Overbought';
                            bbSignal.className = 'indicator-signal bearish';
                        } else if (data.rate < data.indicators.bb_lower) {
                            bbSignal.textContent = 'Oversold';
                            bbSignal.className = 'indicator-signal bullish';
                        } else {
                            bbSignal.textContent = 'Within Bands';
                            bbSignal.className = 'indicator-signal neutral';
                        }
                    }
                }

                // Stochastic RSI
                if (typeof data.indicators.stoch_rsi_k === 'number' && typeof data.indicators.stoch_rsi_d === 'number') {
                    const stochElement = document.getElementById('stochRsiValue');
                    const stochSignal = document.getElementById('stochRsiSignal');
                    if (stochElement) {
                        stochElement.textContent = `K:${data.indicators.stoch_rsi_k.toFixed(2)} D:${data.indicators.stoch_rsi_d.toFixed(2)}`;
                    }
                    if (stochSignal) {
                        if (data.indicators.stoch_rsi_k > 80 && data.indicators.stoch_rsi_d > 80) {
                            stochSignal.textContent = 'Overbought';
                            stochSignal.className = 'indicator-signal bearish';
                        } else if (data.indicators.stoch_rsi_k < 20 && data.indicators.stoch_rsi_d < 20) {
                            stochSignal.textContent = 'Oversold';
                            stochSignal.className = 'indicator-signal bullish';
                        } else {
                            stochSignal.textContent = 'Neutral';
                            stochSignal.className = 'indicator-signal neutral';
                        }
                    }
                }
            }

            // Update last update time
            const lastUpdateElement = document.getElementById('lastUpdate');
            if (lastUpdateElement) {
                lastUpdateElement.textContent = `Last update: ${new Date().toLocaleTimeString()}`;
            }
        } catch (error) {
            console.error('Error updating display:', error);
        }
    }

    function clearDisplayData() {
        if (currentRateElement) currentRateElement.textContent = 'N/A';
        if (dataSourceElement) dataSourceElement.textContent = 'No Data';
        if (callPriceElement) callPriceElement.textContent = 'N/A';
        if (putPriceElement) putPriceElement.textContent = 'N/A';
        document.querySelectorAll('.current-market-price').forEach(el => el.textContent = 'N/A');
        
        const elements = {
            volatilityVal: document.getElementById('volatilityVal'),
            expiryVal: document.getElementById('expiryVal'),
            riskFreeVal: document.getElementById('riskFreeVal'),
            payoutVal: document.getElementById('payoutVal'),
            selectedBroker: document.getElementById('selectedBroker'),
            brokerSelect: document.getElementById('brokerSelect')
        };

        Object.entries(elements).forEach(([key, element]) => {
            if (element) {
                if (key === 'selectedBroker' && elements.brokerSelect) {
                    element.textContent = elements.brokerSelect.value;
                } else {
                    element.textContent = 'N/A';
                }
            }
        });

        // Clear chart
        if (priceChart) {
            priceChart.destroy();
            priceChart = null;
        }
        chartInitialized = false;
    }

    // Update when broker changes
    document.getElementById('brokerSelect').addEventListener('change', function() {
        const broker = this.value;
        
        // Update payout display based on broker
        const payouts = {
            "Quotex": 0.85,
            "Pocket Option": 0.80,
            "Binolla": 0.78,
            "IQ Option": 0.82,
            "Bullex": 0.75,
            "Exnova": 0.77
        };
        
        // Update payout display
        const payout = payouts[broker] || 0.75;
        document.getElementById('payoutVal').textContent = `${(payout * 100).toFixed(0)}%`;
        
        // Update selected broker display
        document.getElementById('selectedBroker').textContent = broker;
    });

    // Toggle signals visibility
    const toggleButton = document.getElementById('toggleSignals');
    const signalsContainer = document.getElementById('signalsContainer');
    
    if (toggleButton && signalsContainer) {
        toggleButton.addEventListener('click', function() {
            const isVisible = !signalsContainer.classList.contains('hidden');
            
            if (isVisible) {
                signalsContainer.classList.add('hidden');
                toggleButton.innerHTML = '<i class="fas fa-chevron-down"></i> Click to Show Generated Signals';
            } else {
                signalsContainer.classList.remove('hidden');
                toggleButton.innerHTML = '<i class="fas fa-chevron-up"></i> Click to Hide Generated Signals';
            }
        });
    }

    // Demo timer fetch
    function updateDemoTime() {
        fetch("/get_demo_time").then(r => r.json()).then(data => {
            document.getElementById("demo-time").textContent = data.time_left;
        });
    }
    setInterval(updateDemoTime, 1000);
    updateDemoTime();

    // Cleanup on page unload
    window.addEventListener('beforeunload', function() {
        if (priceChart) {
            priceChart.destroy();
            priceChart = null;
        }
        if (socket) {
            socket.disconnect();
        }
    });
}); 