// Global variables
const state = {
    priceChart: null,
    priceData: [],
    lastUpdateTime: null,
    currentPair: '',
    socket: null,
    demoTimeLeft: 30 * 60, // 30 minutes in seconds
    isConnected: false
};

// Forex Market WebSocket Handler
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing Forex page...');
    
    // Initialize components
    initializeChart();
    setupSocketConnection();
    setupEventListeners();
    startDemoTimer();

    // Get initial pair from select element
    const pairSelect = document.getElementById('pairSelect');
    if (pairSelect?.value) {
        state.currentPair = pairSelect.value;
        updateMarketData(state.currentPair);
    }

    // Set initial data
    const initialData = {
        historical: {
            dates: [],
            prices: {
                open: [],
                high: [],
                low: [],
                close: [],
                volume: []
            },
            indicators: {
                sma: [],
                ema: [],
                rsi: [],
                macd: [],
                macd_signal: []
            }
        }
    };

    // Update display with initial data
    updateDisplayWithData(initialData);
    
    // Set initial trading parameters
    updateTradingParameters({
        broker: 'Quotex',
        payout: '85.0%',
        volatility: '0.2',
        expiry: '0.0027397260273972603',
        riskFreeRate: '0.01'
    });

    // Set initial connection status
    updateConnectionStatus(true);
});

// Initialize the price chart
function initializeChart() {
    const ctx = document.getElementById('priceChart')?.getContext('2d');
    if (!ctx) return;

    state.priceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Price',
                data: [],
                borderColor: '#00e6d0',
                backgroundColor: 'rgba(0, 230, 208, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 5,
                pointHoverBackgroundColor: '#00e6d0',
                pointHoverBorderColor: '#fff',
                pointHoverBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#00e6d0',
                    bodyColor: '#fff',
                    borderColor: '#00e6d0',
                    borderWidth: 1,
                    padding: 10,
                    displayColors: false,
                    callbacks: {
                        label: function(context) {
                            return `Price: ${context.parsed.y.toFixed(5)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { 
                        color: 'rgba(255, 255, 255, 0.1)',
                        drawBorder: false
                    },
                    ticks: { 
                        color: '#fff',
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 8
                    }
                },
                y: {
                    grid: { 
                        color: 'rgba(255, 255, 255, 0.1)',
                        drawBorder: false
                    },
                    ticks: { 
                        color: '#fff',
                        callback: function(value) {
                            return value.toFixed(5);
                        }
                    }
                }
            },
            animation: {
                duration: 750,
                easing: 'easeInOutQuart'
            }
        }
    });
}

// Setup WebSocket connection
function setupSocketConnection() {
    try {
        state.socket = io();
        
        state.socket.on('connect', () => {
            console.log('Connected to WebSocket');
            state.isConnected = true;
            const pairSelect = document.getElementById('pairSelect');
            if (pairSelect?.value) {
                state.currentPair = pairSelect.value;
                state.socket.emit('subscribe', { pair: state.currentPair });
            }
            updateConnectionStatus(true);
        });

        state.socket.on('price_update', function(data) {
            console.log('Received price update:', data);
            
            if (data.error) {
                console.error('WebSocket error:', data.error);
                return;
            }

            // Update current rate
            const currentRateElement = document.getElementById('currentRate');
            const dataSourceElement = document.getElementById('dataSource');
            const lastUpdateElement = document.getElementById('lastUpdate');
            
            if (currentRateElement) {
                currentRateElement.textContent = data.rate ? data.rate.toFixed(5) : 'N/A';
            }
            
            if (dataSourceElement) {
                dataSourceElement.textContent = data.source || 'Real-time';
            }
            
            if (lastUpdateElement) {
                lastUpdateElement.textContent = new Date().toLocaleString();
            }

            // Update option prices
            const callPriceElement = document.getElementById('callPrice');
            const putPriceElement = document.getElementById('putPrice');
            const callMarketPriceElement = document.getElementById('callMarketPrice');
            const putMarketPriceElement = document.getElementById('putMarketPrice');
            
            if (callPriceElement) {
                callPriceElement.textContent = data.call_price ? data.call_price.toFixed(6) : 'N/A';
            }
            if (putPriceElement) {
                putPriceElement.textContent = data.put_price ? data.put_price.toFixed(6) : 'N/A';
            }
            if (callMarketPriceElement) {
                callMarketPriceElement.textContent = data.call_price ? data.call_price.toFixed(6) : 'N/A';
            }
            if (putMarketPriceElement) {
                putMarketPriceElement.textContent = data.put_price ? data.put_price.toFixed(6) : 'N/A';
            }

            // Update trading parameters
            const brokerElement = document.getElementById('broker');
            const payoutElement = document.getElementById('payout');
            const volatilityElement = document.getElementById('volatility');
            const expiryElement = document.getElementById('expiry');
            const riskFreeRateElement = document.getElementById('riskFreeRate');
            
            if (brokerElement) brokerElement.textContent = data.broker || 'Quotex';
            if (payoutElement) payoutElement.textContent = data.payout ? `${(data.payout * 100).toFixed(1)}%` : '85.0%';
            if (volatilityElement) volatilityElement.textContent = data.volatility ? data.volatility.toFixed(2) : '0.20';
            if (expiryElement) expiryElement.textContent = data.expiry ? data.expiry.toFixed(4) : '0.0027';
            if (riskFreeRateElement) riskFreeRateElement.textContent = data.risk_free_rate ? data.risk_free_rate.toFixed(2) : '0.01';

            // Update chart with new price
            if (state.priceChart && data.rate) {
                const now = new Date();
                state.priceChart.data.labels.push(now.toLocaleTimeString());
                state.priceChart.data.datasets[0].data.push(data.rate);
                
                // Keep only last 100 points
                if (state.priceChart.data.labels.length > 100) {
                    state.priceChart.data.labels.shift();
                    state.priceChart.data.datasets[0].data.shift();
                }
                
                state.priceChart.update();
            }
        });

        state.socket.on('disconnect', () => {
            console.log('Disconnected from WebSocket');
            state.isConnected = false;
            updateConnectionStatus(false);
            showErrorState('WebSocket disconnected');
        });

        state.socket.on('connect_error', (error) => {
            console.error('WebSocket connection error:', error);
            state.isConnected = false;
            updateConnectionStatus(false);
            showErrorState('WebSocket connection error');
        });
    } catch (error) {
        console.error('Error setting up WebSocket:', error);
        showErrorState('Failed to setup WebSocket connection');
    }
}

// Setup event listeners
function setupEventListeners() {
    const pairSelect = document.getElementById('pairSelect');
    if (pairSelect) {
        pairSelect.addEventListener('change', function() {
            const newPair = this.value;
            console.log('Pair changed to:', newPair);
            
            // Update current pair in state
            state.currentPair = newPair;
            
            // Unsubscribe from old pair if exists
            if (state.socket && state.currentPair) {
                state.socket.emit('unsubscribe', { pair: state.currentPair });
            }
            
            // Subscribe to new pair
            if (state.socket && newPair) {
                state.socket.emit('subscribe', { pair: newPair });
                updateMarketData(newPair);
            }
        });
    }

    const toggleSignals = document.getElementById('toggleSignals');
    if (toggleSignals) {
        toggleSignals.addEventListener('click', function() {
            const signalsContainer = document.getElementById('signalsContainer');
            signalsContainer?.classList.toggle('hidden');
            this.innerHTML = signalsContainer?.classList.contains('hidden') 
                ? '<i class="fas fa-chevron-down"></i> Click to Show Generated Signals'
                : '<i class="fas fa-chevron-down"></i> Click to Hide Generated Signals';
        });
    }
}

// Update market data
async function updateMarketData(pair) {
    try {
        console.log(`Updating market data for pair: ${pair}`);
        const response = await fetch(`/market_data/${pair.replace('/', '')}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }

        if (!data.historical) {
            throw new Error('No historical data available');
        }

        // Update the display with the received data
        updateDisplayWithData(data);
        
        // Update the chart
        if (data.historical.dates && data.historical.prices) {
            updateChart(data.historical.dates, data.historical.prices);
        }
        
        // Update technical indicators
        if (data.historical.indicators) {
            const currentRate = data.historical.prices.close[data.historical.prices.close.length - 1];
            updateTechnicalIndicators(data.historical.indicators, currentRate);
        }
        
        // Update last update time
        const lastUpdateElement = document.getElementById('lastUpdate');
        if (lastUpdateElement) {
            lastUpdateElement.textContent = new Date().toLocaleString();
        }
        
    } catch (error) {
        console.error('Error fetching market data:', error);
        showErrorState('Error fetching market data. Using WebSocket data as fallback.');
        // The WebSocket connection will provide real-time updates as fallback
    }
}

// Update display with data
function updateDisplayWithData(data) {
    try {
        // Update current rate
        const currentRateElement = document.getElementById('currentRate');
        const dataSourceElement = document.getElementById('dataSource');
        const lastUpdateElement = document.getElementById('lastUpdate');
        
        if (data.historical && data.historical.prices && data.historical.prices.close) {
            const currentRate = data.historical.prices.close[data.historical.prices.close.length - 1];
            if (currentRateElement) {
                currentRateElement.textContent = currentRate ? currentRate.toFixed(5) : 'N/A';
            }
        }
        
        // Update data source
        if (dataSourceElement) {
            dataSourceElement.textContent = 'Yahoo Finance';
        }
        
        // Update last update time
        if (lastUpdateElement) {
            lastUpdateElement.textContent = new Date().toLocaleString();
        }
        
        // Update technical indicators
        if (data.historical && data.historical.indicators) {
            const currentRate = data.historical.prices.close[data.historical.prices.close.length - 1];
            updateTechnicalIndicators(data.historical.indicators, currentRate);
        }
        
        // Update chart
        if (data.historical && data.historical.dates && data.historical.prices) {
            updateChart(data.historical.dates, data.historical.prices);
        }
        
    } catch (error) {
        console.error('Error updating display:', error);
        showErrorState('Error updating display');
    }
}

// Update trading parameters
function updateTradingParameters(params) {
    const elements = {
        broker: document.getElementById('selectedBroker'),
        payout: document.getElementById('payoutVal'),
        volatility: document.getElementById('volatilityVal'),
        expiry: document.getElementById('expiryVal'),
        riskFreeRate: document.getElementById('riskFreeVal')
    };

    if (elements.broker) elements.broker.textContent = params.broker;
    if (elements.payout) elements.payout.textContent = params.payout;
    if (elements.volatility) elements.volatility.textContent = params.volatility;
    if (elements.expiry) elements.expiry.textContent = params.expiry;
    if (elements.riskFreeRate) elements.riskFreeRate.textContent = params.riskFreeRate;
}

// Update connection status
function updateConnectionStatus(connected) {
    const statusElement = document.getElementById('connectionStatus');
    if (statusElement) {
        statusElement.textContent = connected ? 'Connected' : 'Disconnected';
        statusElement.style.color = connected ? '#4caf50' : '#f44336';
    }
}

// Show error state
function showErrorState(errorMessage) {
    const currentRate = document.getElementById('currentRate');
    const dataSource = document.getElementById('dataSource');
    const lastUpdate = document.getElementById('lastUpdate');
    
    if (currentRate) currentRate.textContent = 'Connection Error';
    if (dataSource) {
        dataSource.textContent = 'Disconnected';
        dataSource.style.color = '#f44336';
    }
    if (lastUpdate) {
        lastUpdate.textContent = errorMessage || 'Waiting for updates...';
        lastUpdate.style.color = '#f44336';
    }
}

// Start demo timer
function startDemoTimer() {
    const demoTimeElement = document.getElementById('demo-time');
    if (!demoTimeElement) return;

    function updateTimer() {
        const minutes = Math.floor(state.demoTimeLeft / 60);
        const seconds = state.demoTimeLeft % 60;
        demoTimeElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        
        if (state.demoTimeLeft > 0) {
            state.demoTimeLeft--;
            setTimeout(updateTimer, 1000);
        } else {
            demoTimeElement.textContent = '00:00';
        }
    }

    updateTimer();
}

// Update technical indicators
function updateTechnicalIndicators(indicators, currentRate) {
    if (!indicators) return;

    // Helper function to format indicator value
    const formatValue = (value) => {
        return value !== null && !isNaN(value) ? value.toFixed(5) : 'N/A';
    };

    // Update RSI
    const rsiElement = document.getElementById('rsiValue');
    if (rsiElement && indicators.rsi && indicators.rsi.length > 0) {
        const latestRsi = indicators.rsi[indicators.rsi.length - 1];
        rsiElement.textContent = formatValue(latestRsi);
        if (latestRsi !== null && !isNaN(latestRsi)) {
            if (latestRsi > 70) {
                rsiElement.style.color = '#f44336'; // Overbought
            } else if (latestRsi < 30) {
                rsiElement.style.color = '#4caf50'; // Oversold
            } else {
                rsiElement.style.color = '#ffb300'; // Neutral
            }
        } else {
            rsiElement.style.color = '#ffb300'; // Default color for N/A
        }
    }

    // Update MACD
    const macdElement = document.getElementById('macdValue');
    if (macdElement && indicators.macd && indicators.macd.length > 0) {
        const latestMacd = indicators.macd[indicators.macd.length - 1];
        macdElement.textContent = formatValue(latestMacd);
    }

    // Update SMA and EMA
    const smaElement = document.getElementById('smaValue');
    const emaElement = document.getElementById('emaValue');
    if (smaElement && indicators.sma && indicators.sma.length > 0) {
        const latestSma = indicators.sma[indicators.sma.length - 1];
        smaElement.textContent = formatValue(latestSma);
    }
    if (emaElement && indicators.ema && indicators.ema.length > 0) {
        const latestEma = indicators.ema[indicators.ema.length - 1];
        emaElement.textContent = formatValue(latestEma);
    }

    // Update MACD Signal
    const macdSignalElement = document.getElementById('macdSignalValue');
    if (macdSignalElement && indicators.macd_signal && indicators.macd_signal.length > 0) {
        const latestSignal = indicators.macd_signal[indicators.macd_signal.length - 1];
        macdSignalElement.textContent = formatValue(latestSignal);
    }
}

function updateChart(dates, prices) {
    if (!state.priceChart || !dates || !prices || !prices.close) return;

    // Update chart data
    state.priceChart.data.labels = dates;
    state.priceChart.data.datasets[0].data = prices.close;

    // Update chart
    state.priceChart.update();
}

// Add a toast notification function
function showToast(message, type = 'info') {
    // Create toast element if it doesn't exist
    let toast = document.getElementById('toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast';
        toast.style.position = 'fixed';
        toast.style.bottom = '20px';
        toast.style.right = '20px';
        toast.style.padding = '12px 24px';
        toast.style.borderRadius = '4px';
        toast.style.color = 'white';
        toast.style.zIndex = '1000';
        toast.style.transition = 'opacity 0.3s ease-in-out';
        document.body.appendChild(toast);
    }
    
    // Set toast style based on type
    switch(type) {
        case 'error':
            toast.style.backgroundColor = '#f44336';
            break;
        case 'warning':
            toast.style.backgroundColor = '#ff9800';
            break;
        default:
            toast.style.backgroundColor = '#2196f3';
    }
    
    // Set message and show toast
    toast.textContent = message;
    toast.style.opacity = '1';
    
    // Hide toast after 3 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
    }, 3000);
} 