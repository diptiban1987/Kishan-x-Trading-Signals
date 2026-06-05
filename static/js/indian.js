// Initialize Socket.IO connection
const socket = io({
    reconnection: true,
    reconnectionAttempts: 10,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 20000,
    transports: ['websocket', 'polling'],
    auth: {
        token: document.cookie.split('; ').find(row => row.startsWith('session='))?.split('=')[1]
    }
});

// Initialize state variables
let chartLabels = [];
let chartPrices = [];
let chart = null; // Global chart variable for checkbox controls
let chartInitialized = false;
const MAX_DATA_POINTS = 100;
let lastUpdateTime = Date.now();
let currentPair = null;
let updateCount = 0;

// Real-time data variables
let previousPrice = null;
let dayHigh = null;
let dayLow = null;
let priceHistory = [];
const MAX_PRICE_HISTORY = 50; // Keep last 50 price points for signal calculation

// Initialize chart
function initializeChart() {
    const chartCanvas = document.getElementById('priceChart');
    if (!chartCanvas) return null;
    
    const ctx = chartCanvas.getContext('2d');
    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Price',
                    data: [],
                    borderColor: '#00e6d0',
                    backgroundColor: 'rgba(0, 230, 208, 0.1)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHitRadius: 10,
                    borderWidth: 2
                },
                {
                    label: 'RSI',
                    data: [],
                    borderColor: '#ffb300',
                    backgroundColor: 'transparent',
                    borderDash: [5, 5],
                    tension: 0.4,
                    pointRadius: 0,
                    hidden: true
                },
                {
                    label: 'MACD',
                    data: [],
                    borderColor: '#f44336',
                    backgroundColor: 'transparent',
                    borderDash: [3, 3],
                    tension: 0.4,
                    pointRadius: 0,
                    hidden: true
                },
                {
                    label: 'Bollinger Upper',
                    data: [],
                    borderColor: '#4CAF50',
                    backgroundColor: 'transparent',
                    borderDash: [2, 2],
                    tension: 0.4,
                    pointRadius: 0,
                    hidden: true
                },
                {
                    label: 'Bollinger Lower',
                    data: [],
                    borderColor: '#4CAF50',
                    backgroundColor: 'transparent',
                    borderDash: [2, 2],
                    tension: 0.4,
                    pointRadius: 0,
                    hidden: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 0
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#fff',
                        usePointStyle: true
                    }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#00e6d0',
                    bodyColor: '#fff',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    display: true,
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: '#aaa',
                        maxRotation: 0
                    }
                },
                y: {
                    display: true,
                    position: 'right',
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: '#aaa'
                    }
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            }
        }
    });
}

// Calculate technical indicators
function calculateIndicators(prices) {
    // RSI calculation
    const rsi = calculateRSI(prices);
    const currentRSI = rsi[rsi.length - 1];
    document.getElementById('rsiValue').textContent = currentRSI ? currentRSI.toFixed(2) : 'N/A';
    
    // Update RSI signal
    const rsiSignal = document.getElementById('rsiSignal');
    if (currentRSI) {
        if (currentRSI > 70) {
            rsiSignal.textContent = 'Overbought';
            rsiSignal.className = 'indicator-signal bearish';
        } else if (currentRSI < 30) {
            rsiSignal.textContent = 'Oversold';
            rsiSignal.className = 'indicator-signal bullish';
        } else {
            rsiSignal.textContent = 'Neutral';
            rsiSignal.className = 'indicator-signal neutral';
        }
    }

    // MACD calculation
    const macd = calculateMACD(prices);
    const currentMACD = macd.histogram[macd.histogram.length - 1];
    document.getElementById('macdValue').textContent = currentMACD ? currentMACD.toFixed(6) : 'N/A';
    
    // Update MACD signal
    const macdSignal = document.getElementById('macdSignal');
    if (currentMACD) {
        if (currentMACD > 0) {
            macdSignal.textContent = 'Bullish';
            macdSignal.className = 'indicator-signal bullish';
        } else if (currentMACD < 0) {
            macdSignal.textContent = 'Bearish';
            macdSignal.className = 'indicator-signal bearish';
        } else {
            macdSignal.textContent = 'Neutral';
            macdSignal.className = 'indicator-signal neutral';
        }
    }

    // Calculate Bollinger Bands
    const bb = calculateBollingerBands(prices);
    
    return { rsi, macd, bb };
}

// Calculate RSI
function calculateRSI(prices, period = 14) {
    if (prices.length < period) return [];
    
    let gains = [];
    let losses = [];
    
    for (let i = 1; i < prices.length; i++) {
        const change = prices[i] - prices[i-1];
        gains.push(change > 0 ? change : 0);
        losses.push(change < 0 ? -change : 0);
    }
    
    let avgGain = gains.slice(0, period).reduce((a, b) => a + b) / period;
    let avgLoss = losses.slice(0, period).reduce((a, b) => a + b) / period;
    
    let rsi = [];
    rsi.push(100 - (100 / (1 + avgGain / avgLoss)));
    
    for (let i = period; i < prices.length; i++) {
        avgGain = (avgGain * (period - 1) + gains[i-1]) / period;
        avgLoss = (avgLoss * (period - 1) + losses[i-1]) / period;
        rsi.push(100 - (100 / (1 + avgGain / avgLoss)));
    }
    
    return rsi;
}

// Calculate MACD
function calculateMACD(prices, fastPeriod = 12, slowPeriod = 26, signalPeriod = 9) {
    function calculateEMA(data, period) {
        const k = 2 / (period + 1);
        let ema = [data[0]];
        
        for (let i = 1; i < data.length; i++) {
            ema.push(data[i] * k + ema[i-1] * (1-k));
        }
        
        return ema;
    }
    
    const fastEMA = calculateEMA(prices, fastPeriod);
    const slowEMA = calculateEMA(prices, slowPeriod);
    const macdLine = fastEMA.map((fast, i) => fast - slowEMA[i]);
    const signalLine = calculateEMA(macdLine, signalPeriod);
    
    return {
        macd: macdLine,
        signal: signalLine,
        histogram: macdLine.map((macd, i) => macd - signalLine[i])
    };
}

// Calculate Bollinger Bands
function calculateBollingerBands(prices, period = 20, multiplier = 2) {
    if (prices.length < period) return { upper: [], lower: [], middle: [] };
    
    const sma = [];
    const upper = [];
    const lower = [];
    
    for (let i = period - 1; i < prices.length; i++) {
        const slice = prices.slice(i - period + 1, i + 1);
        const avg = slice.reduce((a, b) => a + b) / period;
        const squaredDiffs = slice.map(price => Math.pow(price - avg, 2));
        const standardDev = Math.sqrt(squaredDiffs.reduce((a, b) => a + b) / period);
        
        sma.push(avg);
        upper.push(avg + (multiplier * standardDev));
        lower.push(avg - (multiplier * standardDev));
    }
    
    return { upper, lower, middle: sma };
}

// Update info card and chart
function updateInfoCardAndChart(data) {
    try {
        if (!data) {
            console.warn('No data received in updateInfoCardAndChart');
            showErrorState('No data received');
            return;
        }

        // Get broker info from select element
        const brokerSelect = document.getElementById('brokerSelect');
        const selectedBroker = brokerSelect ? brokerSelect.value : 'Quotex'; // Default to Quotex if not found
        
        // Update current rate
        if (typeof data.rate === 'number' && !isNaN(data.rate)) {
            const currentRateElement = document.getElementById('currentRate');
            if (currentRateElement) {
                currentRateElement.textContent = data.rate.toFixed(6);
            }
            
            // Update all price displays
            document.querySelectorAll('.current-market-price').forEach(el => {
                el.textContent = data.rate.toFixed(6);
            });
        }

        // Update data source
        const dataSourceElement = document.getElementById('dataSource');
        if (dataSourceElement) {
            dataSourceElement.textContent = data.source || 'Real-time';
        }

        // Update call/put prices if available
        if (typeof data.call_price === 'number' && !isNaN(data.call_price)) {
            const callPriceElement = document.getElementById('callPrice');
            if (callPriceElement) {
                callPriceElement.textContent = data.call_price.toFixed(6);
            }
        }
        if (typeof data.put_price === 'number' && !isNaN(data.put_price)) {
            const putPriceElement = document.getElementById('putPrice');
            if (putPriceElement) {
                putPriceElement.textContent = data.put_price.toFixed(6);
            }
        }

        // Update chart
        const chartCanvas = document.getElementById('priceChart');
        if (typeof data.rate === 'number' && !isNaN(data.rate) && chartCanvas) {
            if (!chartInitialized || !chart) {
                chart = initializeChart();
                chartInitialized = true;
            }
            
            if (chart) {
                try {
                    const timestamp = new Date().toLocaleTimeString();
                    
                    if (chartLabels.length > MAX_DATA_POINTS) {
                        chartLabels.shift();
                        chartPrices.shift();
                    }
                    
                    chartLabels.push(timestamp);
                    chartPrices.push(data.rate);
                    
                    // Calculate indicators
                    const indicators = calculateIndicators(chartPrices);
                    
                    // Update chart datasets
                    chart.data.labels = chartLabels;
                    chart.data.datasets[0].data = chartPrices;
                    chart.data.datasets[1].data = indicators.rsi;
                    chart.data.datasets[2].data = indicators.macd.histogram;
                    chart.data.datasets[3].data = indicators.bb.upper;
                    chart.data.datasets[4].data = indicators.bb.lower;
                    
                    chart.update('none');
                    
                    // Update indicator displays
                    updateIndicatorDisplays(indicators);
                    
                    const noDataMsg = document.getElementById('noDataMsg');
                    if (noDataMsg) {
                        noDataMsg.style.display = 'none';
                    }
                } catch (error) {
                    console.error('Error updating chart:', error);
                    // Attempt to reinitialize chart on error
                    chartInitialized = false;
                    chart = null;
                }
            }
        }

        // Update last update time
        const lastUpdateElement = document.getElementById('lastUpdate');
        if (lastUpdateElement) {
            const now = new Date();
            lastUpdateElement.textContent = `Last update: ${now.toLocaleTimeString()}`;
        }

        // Update broker info
        const selectedBrokerElement = document.getElementById('selectedBroker');
        if (selectedBrokerElement) {
            selectedBrokerElement.textContent = selectedBroker;
        }

        // Update payout based on broker
        const payouts = {
            "Quotex": 0.85,
            "Pocket Option": 0.80,
            "Binolla": 0.78,
            "IQ Option": 0.82,
            "Bullex": 0.75,
            "Exnova": 0.77,
            "Zerodha": 0.75,
            "Upstox": 0.78,
            "Angel One": 0.77,
            "Groww": 0.76,
            "ICICI Direct": 0.75,
            "HDFC Securities": 0.74
        };
        
        const payout = payouts[selectedBroker] || 0.75;
        const payoutElement = document.getElementById('payoutVal');
        if (payoutElement) {
            payoutElement.textContent = `${(payout * 100).toFixed(0)}%`;
        }
    } catch (error) {
        console.error('Error updating info card and chart:', error);
        showErrorState('Error updating display');
    }
}

// Update indicator displays
function updateIndicatorDisplays(indicators) {
    try {
        // Update RSI
        const rsiValue = document.getElementById('rsiValue');
        if (rsiValue && indicators.rsi.length > 0) {
            const currentRSI = indicators.rsi[indicators.rsi.length - 1];
            rsiValue.textContent = currentRSI.toFixed(2);
        }

        // Update MACD
        const macdValue = document.getElementById('macdValue');
        if (macdValue && indicators.macd.histogram.length > 0) {
            const currentMACD = indicators.macd.histogram[indicators.macd.histogram.length - 1];
            macdValue.textContent = currentMACD.toFixed(6);
        }

        // Update Bollinger Bands
        const bbValue = document.getElementById('bbValue');
        if (bbValue && indicators.bb.upper.length > 0) {
            const currentBB = indicators.bb.upper[indicators.bb.upper.length - 1];
            bbValue.textContent = currentBB.toFixed(6);
        }
    } catch (error) {
        console.error('Error updating indicators:', error);
    }
}

// Show error state
function showErrorState(errorMessage) {
    const currentRateElement = document.getElementById('currentRate');
    const dataSourceElement = document.getElementById('dataSource');
    
    if (currentRateElement) currentRateElement.textContent = 'Error';
    if (dataSourceElement) dataSourceElement.textContent = 'Error';
    
    const callPriceElement = document.getElementById('callPrice');
    const putPriceElement = document.getElementById('putPrice');
    if (callPriceElement) callPriceElement.textContent = 'N/A';
    if (putPriceElement) putPriceElement.textContent = 'N/A';
    
    const noDataMsg = document.getElementById('noDataMsg');
    if (noDataMsg) {
        noDataMsg.style.display = 'block';
        noDataMsg.textContent = errorMessage;
    }
}

// Subscribe to price updates
function subscribeToPrice(pair) {
    if (!pair) return;
    
    console.log('Subscribing to:', pair);
    // Reset update statistics
    updateCount = 0;
    lastUpdateTime = Date.now();
    
    // Unsubscribe from previous pair if any
    if (currentPair) {
        console.log('Unsubscribing from:', currentPair);
        socket.emit('unsubscribe', { 
            pair: currentPair,
            type: 'indian'
        });
    }
    
    // Subscribe to new pair
    console.log('Subscribing to new pair:', pair);
    socket.emit('subscribe', { 
        pair: pair,
        type: 'indian'
    });
    currentPair = pair;
    
    // Update status
    updateStatus('Loading...', 'Fetching...');

    // Reset chart when changing pairs
    chartLabels = [];
    chartPrices = [];
    chartInitialized = false;
    if (priceChart) {
        priceChart.destroy();
        priceChart = null;
    }
    
    // Show loading message
    const noDataMsg = document.getElementById('noDataMsg');
    if (noDataMsg) {
        noDataMsg.style.display = 'block';
        noDataMsg.textContent = 'Loading chart data...';
    }

    // Clear current rate display
    const currentRateElement = document.getElementById('currentRate');
    if (currentRateElement) {
        currentRateElement.textContent = 'Loading...';
    }
    document.querySelectorAll('.current-market-price').forEach(el => {
        el.textContent = 'Loading...';
    });
    
    // Clear indicator displays
    const indicators = ['rsiValue', 'macdValue', 'bbValue'];
    indicators.forEach(id => {
        const element = document.getElementById(id);
        if (element) element.textContent = 'Loading...';
    });
    
    // Clear option prices
    const callPriceElement = document.getElementById('callPrice');
    const putPriceElement = document.getElementById('putPrice');
    if (callPriceElement) callPriceElement.textContent = 'N/A';
    if (putPriceElement) putPriceElement.textContent = 'N/A';
}

// Update status display
function updateStatus(rate, source) {
    const currentRateElement = document.getElementById('currentRate');
    const dataSourceElement = document.getElementById('dataSource');
    
    if (currentRateElement) {
        currentRateElement.textContent = rate;
    }
    if (dataSourceElement) {
        dataSourceElement.textContent = source;
    }
}

// Clear display data
function clearDisplayData() {
    const currentRateElement = document.getElementById('currentRate');
    const dataSourceElement = document.getElementById('dataSource');
    const callPriceElement = document.getElementById('callPrice');
    const putPriceElement = document.getElementById('putPrice');
    
    if (currentRateElement) currentRateElement.textContent = 'N/A';
    if (dataSourceElement) dataSourceElement.textContent = 'No Data';
    if (callPriceElement) callPriceElement.textContent = 'N/A';
    if (putPriceElement) putPriceElement.textContent = 'N/A';
    
    document.querySelectorAll('.current-market-price').forEach(el => el.textContent = 'N/A');
    document.getElementById('volatilityVal').textContent = 'N/A';
    document.getElementById('expiryVal').textContent = 'N/A';
    document.getElementById('riskFreeVal').textContent = 'N/A';
    document.getElementById('payoutVal').textContent = 'N/A';
    
    const selectedBrokerElement = document.getElementById('selectedBroker');
    const brokerSelect = document.getElementById('brokerSelect');
    if (selectedBrokerElement && brokerSelect) {
        selectedBrokerElement.textContent = brokerSelect.value;
    }
}

// Socket.IO event handlers
socket.on('connect', () => {
    console.log('Connected to WebSocket');
    updateStatus('Connected', 'Connected');
});

socket.on('disconnect', () => {
    console.log('Disconnected from WebSocket');
    updateStatus('Disconnected', 'Disconnected');
});

socket.on('connect_error', (error) => {
    console.error('Connection error:', error);
    updateStatus('Connection Error', 'Disconnected');
});

// Price update handler
socket.on('price_update', (data) => {
    console.log('Received price update:', data);
    
    try {
        // Handle both direct data and nested data.type === 'price_update' format
        const updateData = data.data || data;
        
        // Log the exact data structure for debugging
        try {
            console.log('Update data structure:', JSON.stringify(updateData));
        } catch (jsonError) {
            console.error('Error stringifying updateData:', jsonError);
            console.log('Raw updateData:', updateData);
            
            // Try to identify the problematic property
            for (const key in updateData) {
                try {
                    const value = JSON.stringify(updateData[key]);
                    console.log(`Property ${key} stringifies to:`, value);
                } catch (propError) {
                    console.error(`Error stringifying property ${key}:`, propError);
                    console.log(`Raw value of ${key}:`, updateData[key]);
                }
            }
        }
        
        if (!updateData || typeof updateData.rate !== 'number') {
            console.warn('Received invalid price update data:', data);
            updateStatus('Invalid data', 'Error');
            return;
        }
        
        if (updateData.error) {
            console.warn('Error in price update:', updateData.error);
            if (updateData.error === 'Not authenticated') {
                // Redirect to login page if not authenticated
                window.location.href = '/login';
                return;
            }
            updateStatus('Error: ' + updateData.error, 'Error');
            return;
        }
        
        // Only update if this is for the currently selected pair
        const selectedPairElement = document.getElementById('pair');
        if (!selectedPairElement || !updateData.pair) return;
        
        const currentPair = selectedPairElement.value.replace('/', '');
        if (updateData.pair !== currentPair) {
            console.log(`Ignoring update for ${updateData.pair} as current pair is ${currentPair}`);
            return;
        }
        
        // Update market status if available
        if (updateData.type === 'indian_update' && updateData.market_open !== undefined) {
            const marketOpen = updateData.market_open;
            const statusElement = document.querySelector('.market-status');
            
            if (statusElement) {
                if (marketOpen) {
                    statusElement.innerHTML = '<span class="status-indicator open"></span> Market Open';
                    statusElement.className = 'market-status open';
                } else {
                    statusElement.innerHTML = '<span class="status-indicator closed"></span> Market Closed';
                    statusElement.className = 'market-status closed';
                    
                    // Add message about data if not already present
                    const realtimeHeader = document.querySelector('.realtime-header');
                    if (realtimeHeader && !realtimeHeader.querySelector('.market-message')) {
                        const messageElement = document.createElement('div');
                        messageElement.className = 'market-message';
                        messageElement.textContent = 'Chart data shows the last available market session. Live updates will resume when market opens.';
                        realtimeHeader.appendChild(messageElement);
                    }
                }
            }
        }
        
        updateInfoCardAndChart(updateData);
        
        // Update last update time
        const now = Date.now();
        const timeSinceLastUpdate = now - lastUpdateTime;
        lastUpdateTime = now;
        updateCount++;
        
        // Log update statistics
        const lastUpdateElement = document.getElementById('lastUpdate');
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

// Initialize on document ready
document.addEventListener('DOMContentLoaded', function() {
    try {
        // Set up chart control checkboxes
        const showPrice = document.getElementById('showPrice');
        const showRSI = document.getElementById('showRSI');
        const showMACD = document.getElementById('showMACD');
        const showBB = document.getElementById('showBB');
        
        if (showPrice) {
            showPrice.addEventListener('change', function() {
                if (chart && chart.data && chart.data.datasets) {
                    chart.data.datasets[0].hidden = !this.checked;
                    chart.update();
                }
            });
        }
        
        if (showRSI) {
            showRSI.addEventListener('change', function() {
                if (chart && chart.data && chart.data.datasets) {
                    chart.data.datasets[1].hidden = !this.checked;
                    chart.update();
                }
            });
        }
        
        if (showMACD) {
            showMACD.addEventListener('change', function() {
                if (chart && chart.data && chart.data.datasets) {
                    chart.data.datasets[2].hidden = !this.checked;
                    chart.update();
                }
            });
        }
        
        if (showBB) {
            showBB.addEventListener('change', function() {
                if (chart && chart.data && chart.data.datasets) {
                    chart.data.datasets[3].hidden = !this.checked;
                    chart.data.datasets[4].hidden = !this.checked;
                    chart.update();
                }
            });
        }
        
        // Check if user is authenticated
        fetch('/api/check_auth', {
            credentials: 'same-origin'
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Not authenticated');
            }
            return response.json();
        })
        .then(data => {
            if (!data.authenticated) {
                window.location.href = '/login';
                return;
            }
            
            // Initialize broker select
            const brokerSelect = document.getElementById('brokerSelect');
            if (brokerSelect) {
                brokerSelect.addEventListener('change', function() {
                    const selectedBroker = this.value;
                    const selectedBrokerElement = document.getElementById('selectedBroker');
                    if (selectedBrokerElement) {
                        selectedBrokerElement.textContent = selectedBroker;
                    }
                    
                    // Update payout
                    const payouts = {
                        "Quotex": 0.85,
                        "Pocket Option": 0.80,
                        "Binolla": 0.78,
                        "IQ Option": 0.82,
                        "Bullex": 0.75,
                        "Exnova": 0.77,
                        "Zerodha": 0.75,
                        "Upstox": 0.78,
                        "Angel One": 0.77,
                        "Groww": 0.76,
                        "ICICI Direct": 0.75,
                        "HDFC Securities": 0.74
                    };
                    
                    const payout = payouts[selectedBroker] || 0.75;
                    const payoutElement = document.getElementById('payoutVal');
                    if (payoutElement) {
                        payoutElement.textContent = `${(payout * 100).toFixed(0)}%`;
                    }
                });
            }

            // Initialize pair select
            const selectedPairElement = document.getElementById('pair');
            if (selectedPairElement) {
                selectedPairElement.addEventListener('change', function() {
                    const pair = this.value;
                    if (pair && pair !== "Select Pair") {
                        subscribeToPrice(pair);
                    } else {
                        clearDisplayData();
                    }
                });

                // Initial subscription
                if (selectedPairElement.value && selectedPairElement.value !== "Select Pair") {
                    subscribeToPrice(selectedPairElement.value);
                }
            }
            
            // Initialize real-time data
            initializeRealTimeData();
        })
        .catch(error => {
            console.error('Authentication error:', error);
            window.location.href = '/login';
        });
    } catch (error) {
        console.error('Error initializing page:', error);
    }
});

// Initialize real-time data
function initializeRealTimeData() {
    // Check if market is open
    function isMarketOpen() {
        const now = new Date();
        const indiaTime = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
        const day = indiaTime.getDay();
        const hours = indiaTime.getHours();
        const minutes = indiaTime.getMinutes();
        
        // Indian markets are open Monday-Friday, 9:15 AM to 3:30 PM IST
        const isWeekday = day >= 1 && day <= 5;
        const isOpenTime = (hours > 9 || (hours === 9 && minutes >= 15)) && (hours < 15 || (hours === 15 && minutes <= 30));
        
        return isWeekday && isOpenTime;
    }
    
    // Update market status message
    function updateMarketStatus() {
        const marketOpen = isMarketOpen();
        const statusElement = document.createElement('div');
        statusElement.className = 'market-status';
        
        if (marketOpen) {
            statusElement.innerHTML = '<span class="status-indicator open"></span> Market Open';
            statusElement.classList.add('open');
        } else {
            statusElement.innerHTML = '<span class="status-indicator closed"></span> Market Closed';
            statusElement.classList.add('closed');
            
            // Add message about data
            const messageElement = document.createElement('div');
            messageElement.className = 'market-message';
            messageElement.textContent = 'Chart data shows the last available market session. Live updates will resume when market opens.';
            
            const realtimeHeader = document.querySelector('.realtime-header');
            if (realtimeHeader && !realtimeHeader.querySelector('.market-message')) {
                realtimeHeader.appendChild(messageElement);
            }
        }
        
        // Add status to the header
        const realtimeHeader = document.querySelector('.realtime-header');
        if (realtimeHeader) {
            const existingStatus = realtimeHeader.querySelector('.market-status');
            if (existingStatus) {
                realtimeHeader.replaceChild(statusElement, existingStatus);
            } else {
                realtimeHeader.appendChild(statusElement);
            }
        }
    }
    
    // Update market status immediately and then every minute
    updateMarketStatus();
    setInterval(updateMarketStatus, 60000);
    
    // Subscribe to the default symbol
    socket.emit('subscribe', { symbols: [currentPair] });
    
    // Update trading signal based on enhanced technical indicators
    function updateTradingSignal() {
        if (priceHistory.length < 14) {
            // Not enough data yet
            return;
        }
        
        // Calculate indicators
        const rsi = calculateRSI(priceHistory, 14);
        const currentRSI = rsi[rsi.length - 1];
        const prevRSI = rsi.length > 1 ? rsi[rsi.length - 2] : currentRSI;
        
        const macdResult = calculateMACD(priceHistory);
        const macdHistogram = macdResult.histogram[macdResult.histogram.length - 1];
        const prevMacdHistogram = macdResult.histogram.length > 1 ? macdResult.histogram[macdResult.histogram.length - 2] : macdHistogram;
        
        const bollingerResult = calculateBollingerBands(priceHistory);
        const currentPrice = priceHistory[priceHistory.length - 1];
        const prevPrice = priceHistory.length > 1 ? priceHistory[priceHistory.length - 2] : currentPrice;
        const upperBand = bollingerResult.upper[bollingerResult.upper.length - 1];
        const lowerBand = bollingerResult.lower[bollingerResult.lower.length - 1];
        const middleBand = bollingerResult.middle[bollingerResult.middle.length - 1];
        
        // Calculate Stochastic RSI
        const stochRSI = calculateStochasticRSI(priceHistory);
        const currentStochRSI = stochRSI[stochRSI.length - 1];
        const prevStochRSI = stochRSI.length > 1 ? stochRSI[stochRSI.length - 2] : currentStochRSI;
        
        // Calculate trend direction using EMA
        const ema20 = calculateEMA(priceHistory, 20);
        const ema50 = calculateEMA(priceHistory, 50);
        const currentEMA20 = ema20[ema20.length - 1];
        const currentEMA50 = ema50[ema50.length - 1];
        
        // Determine signal with weighted approach
        let buySignals = 0;
        let sellSignals = 0;
        let buyStrength = 0;
        let sellStrength = 0;
        
        // RSI signals (weighted)
        if (currentRSI < 30) {
            buySignals++;
            buyStrength += (30 - currentRSI) / 30 * 2; // More oversold = stronger signal
        }
        if (currentRSI > 70) {
            sellSignals++;
            sellStrength += (currentRSI - 70) / 30 * 2; // More overbought = stronger signal
        }
        
        // RSI trend signals
        if (currentRSI > prevRSI && currentRSI < 50) {
            buySignals++;
            buyStrength += 0.5; // RSI turning up from below 50
        }
        if (currentRSI < prevRSI && currentRSI > 50) {
            sellSignals++;
            sellStrength += 0.5; // RSI turning down from above 50
        }
        
        // MACD signals (weighted)
        if (macdHistogram > 0) {
            buySignals++;
            buyStrength += Math.min(macdHistogram * 10, 1.5); // Stronger positive histogram = stronger signal
        }
        if (macdHistogram < 0) {
            sellSignals++;
            sellStrength += Math.min(Math.abs(macdHistogram) * 10, 1.5); // Stronger negative histogram = stronger signal
        }
        
        // MACD crossover signals (stronger signals)
        if (macdHistogram > 0 && prevMacdHistogram <= 0) {
            buySignals++;
            buyStrength += 2; // Fresh bullish crossover
        }
        if (macdHistogram < 0 && prevMacdHistogram >= 0) {
            sellSignals++;
            sellStrength += 2; // Fresh bearish crossover
        }
        
        // Bollinger Bands signals (weighted)
        if (currentPrice < lowerBand) {
            buySignals++;
            buyStrength += Math.min((lowerBand - currentPrice) / (middleBand * 0.01) * 0.5, 2); // Further below band = stronger signal
        }
        if (currentPrice > upperBand) {
            sellSignals++;
            sellStrength += Math.min((currentPrice - upperBand) / (middleBand * 0.01) * 0.5, 2); // Further above band = stronger signal
        }
        
        // Bollinger Band squeeze (volatility about to increase)
        const bandWidth = (upperBand - lowerBand) / middleBand;
        if (bandWidth < 0.1) { // Narrow bands indicate potential breakout
            if (currentPrice > prevPrice) {
                buySignals++;
                buyStrength += 1;
            } else {
                sellSignals++;
                sellStrength += 1;
            }
        }
        
        // Stochastic RSI signals
        if (currentStochRSI < 20) {
            buySignals++;
            buyStrength += 1;
        }
        if (currentStochRSI > 80) {
            sellSignals++;
            sellStrength += 1;
        }
        
        // Stochastic RSI crossovers
        if (currentStochRSI > 20 && prevStochRSI <= 20) {
            buySignals++;
            buyStrength += 1.5; // Crossing up from oversold
        }
        if (currentStochRSI < 80 && prevStochRSI >= 80) {
            sellSignals++;
            sellStrength += 1.5; // Crossing down from overbought
        }
        
        // Trend direction from EMAs
        if (currentEMA20 > currentEMA50) {
            buySignals += 0.5;
            buyStrength += 0.5; // Uptrend
        } else {
            sellSignals += 0.5;
            sellStrength += 0.5; // Downtrend
        }
        
        // Price momentum
        const priceChange = (currentPrice - prevPrice) / prevPrice;
        if (priceChange > 0.005) { // 0.5% price increase
            buySignals += 0.5;
            buyStrength += priceChange * 100; // Stronger momentum = stronger signal
        }
        if (priceChange < -0.005) { // 0.5% price decrease
            sellSignals += 0.5;
            sellStrength += Math.abs(priceChange) * 100; // Stronger momentum = stronger signal
        }
        
        // Calculate confidence percentages
        const totalStrength = buyStrength + sellStrength;
        const buyConfidence = totalStrength > 0 ? Math.round((buyStrength / totalStrength) * 100) : 0;
        const sellConfidence = totalStrength > 0 ? Math.round((sellStrength / totalStrength) * 100) : 0;
        
        // Update signal UI with confidence levels
        const tradingSignal = document.getElementById('trading-signal');
        if (tradingSignal) {
            let signalHTML = '';
            
            // Determine signal based on both count and strength
            if ((buySignals > sellSignals && buyStrength > sellStrength && buySignals >= 3) || 
                (buyStrength > sellStrength * 2 && buySignals >= 2)) {
                signalHTML = `<div class="signal-icon">🔼</div><div class="signal-text">BUY Signal <span class="confidence">(${buyConfidence}% confidence)</span></div>`;
                tradingSignal.className = 'signal-box buy';
                tradingSignal.innerHTML = signalHTML;
            } else if ((sellSignals > buySignals && sellStrength > buyStrength && sellSignals >= 3) || 
                       (sellStrength > buyStrength * 2 && sellSignals >= 2)) {
                signalHTML = `<div class="signal-icon">🔽</div><div class="signal-text">SELL Signal <span class="confidence">(${sellConfidence}% confidence)</span></div>`;
                tradingSignal.className = 'signal-box sell';
                tradingSignal.innerHTML = signalHTML;
            } else {
                signalHTML = '<div class="signal-icon">⚖️</div><div class="signal-text">NEUTRAL - Hold Position</div>';
                tradingSignal.className = 'signal-box neutral';
                tradingSignal.innerHTML = signalHTML;
            }
        }
    }
    
    // Calculate EMA (Exponential Moving Average)
    function calculateEMA(prices, period) {
        if (prices.length < period) return [];
        
        const k = 2 / (period + 1);
        let ema = [prices.slice(0, period).reduce((sum, price) => sum + price, 0) / period];
        
        for (let i = period; i < prices.length; i++) {
            ema.push(prices[i] * k + ema[ema.length - 1] * (1 - k));
        }
        
        return ema;
    }
    
    // Calculate Stochastic RSI
    function calculateStochasticRSI(prices, rsiPeriod = 14, stochPeriod = 14) {
        const rsiValues = calculateRSI(prices, rsiPeriod);
        if (rsiValues.length < stochPeriod) return [];
        
        const stochRSI = [];
        
        for (let i = stochPeriod - 1; i < rsiValues.length; i++) {
            const rsiWindow = rsiValues.slice(i - stochPeriod + 1, i + 1);
            const minRSI = Math.min(...rsiWindow);
            const maxRSI = Math.max(...rsiWindow);
            
            if (maxRSI - minRSI === 0) {
                stochRSI.push(50); // Default to neutral if no range
            } else {
                stochRSI.push(((rsiValues[i] - minRSI) / (maxRSI - minRSI)) * 100);
            }
        }
        
        return stochRSI;
    }
    
    // Handle market symbol selection change
    $("#marketSymbolSelector").on("change", function() {
        const newSymbol = $(this).val();
        // Unsubscribe from current symbol
        socket.emit('unsubscribe', { symbols: [currentPair] });
        
        // Update current pair
        currentPair = newSymbol;
        
        // Reset data
        previousPrice = null;
        dayHigh = null;
        dayLow = null;
        priceHistory = [];
        
        // Update UI with loading state
        $("#rt-current-price").text("Loading...").removeClass("positive negative");
        $("#rt-price-change").text("Loading...").removeClass("positive negative");
        $("#rt-day-high").text("Loading...");
        $("#rt-day-low").text("Loading...");
        
        // Reset signal
        $("#trading-signal").removeClass("buy sell neutral")
            .html('<div class="signal-icon">⚠️</div><div class="signal-text">Waiting for data...</div>');
        
        // Subscribe to new symbol
        socket.emit('subscribe', { symbols: [currentPair] });
    });
    
    // Update price history with new data
    socket.on('price_update', function(data) {
        if (data.symbol === currentPair) {
            const price = parseFloat(data.price);
            
            // Check if market is open (for Indian symbols)
            if (data.type === 'indian_update' && data.market_open !== undefined) {
                const marketStatusElement = document.querySelector('.market-status');
                const marketMessageElement = document.querySelector('.market-message');
                
                // If market status element exists but doesn't match current status, update it
                if (marketStatusElement) {
                    if ((data.market_open && !marketStatusElement.classList.contains('open')) ||
                        (!data.market_open && !marketStatusElement.classList.contains('closed'))) {
                        // Force update market status
                        const marketOpen = data.market_open;
                        const statusElement = document.createElement('div');
                        statusElement.className = 'market-status';
                        
                        if (marketOpen) {
                            statusElement.innerHTML = '<span class="status-indicator open"></span> Market Open';
                            statusElement.classList.add('open');
                            
                            // Remove message if exists
                            if (marketMessageElement) {
                                marketMessageElement.remove();
                            }
                        } else {
                            statusElement.innerHTML = '<span class="status-indicator closed"></span> Market Closed';
                            statusElement.classList.add('closed');
                            
                            // Add message if not exists
                            if (!marketMessageElement) {
                                const messageElement = document.createElement('div');
                                messageElement.className = 'market-message';
                                messageElement.textContent = 'Chart data shows the last available market session. Live updates will resume when market opens.';
                                
                                const realtimeHeader = document.querySelector('.realtime-header');
                                if (realtimeHeader) {
                                    realtimeHeader.appendChild(messageElement);
                                }
                            }
                        }
                        
                        // Replace existing status
                        const realtimeHeader = document.querySelector('.realtime-header');
                        if (realtimeHeader) {
                            realtimeHeader.replaceChild(statusElement, marketStatusElement);
                        }
                    }
                }
            }
            
            // Add to price history
            priceHistory.push(price);
            if (priceHistory.length > MAX_PRICE_HISTORY) {
                priceHistory.shift();
            }
            
            // Calculate price change
            let priceChange = 0;
            let priceChangePercent = 0;
            
            if (previousPrice !== null) {
                priceChange = price - previousPrice;
                priceChangePercent = (priceChange / previousPrice) * 100;
            }
            
            // Update day high/low
            if (dayHigh === null || price > dayHigh) {
                dayHigh = price;
            }
            
            if (dayLow === null || price < dayLow) {
                dayLow = price;
            }
            
            // Update UI
            $("#rt-current-price").text(price.toFixed(2));
            
            if (previousPrice !== null) {
                const changeText = priceChange.toFixed(2) + " (" + priceChangePercent.toFixed(2) + "%)";
                $("#rt-price-change").text(changeText);
                
                if (priceChange > 0) {
                    $("#rt-price-change").removeClass("negative").addClass("positive");
                } else if (priceChange < 0) {
                    $("#rt-price-change").removeClass("positive").addClass("negative");
                }
            }
            
            $("#rt-day-high").text(dayHigh.toFixed(2));
            $("#rt-day-low").text(dayLow.toFixed(2));
            
            // Update trading signal if we have enough data
            if (priceHistory.length >= 14) {
                updateTradingSignal();
            }
            
            // Store current price as previous for next update
            previousPrice = price;
        }
    });
}