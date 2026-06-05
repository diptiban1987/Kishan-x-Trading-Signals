// Technical Indicators Chart Module
const TechnicalIndicators = {
    initializeChart: function(ctx, labels = [], prices = []) {
        // First, check if there's an existing chart instance on this canvas
        const existingChart = Chart.getChart(ctx.canvas);
        if (existingChart) {
            existingChart.destroy();
        }

        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Price',
                        data: prices,
                        borderColor: '#00e6d0',
                        backgroundColor: 'rgba(0, 230, 208, 0.1)',
                        tension: 0.1,
                        fill: false,
                        pointRadius: 1,
                        pointHoverRadius: 3,
                        borderWidth: 2,
                        yAxisID: 'price'
                    },
                    {
                        label: 'BB Upper',
                        data: [],
                        borderColor: 'rgba(255, 99, 132, 0.8)',
                        borderDash: [5, 5],
                        fill: false,
                        pointRadius: 0,
                        yAxisID: 'price'
                    },
                    {
                        label: 'BB Lower',
                        data: [],
                        borderColor: 'rgba(255, 99, 132, 0.8)',
                        borderDash: [5, 5],
                        fill: false,
                        pointRadius: 0,
                        yAxisID: 'price'
                    },
                    {
                        label: 'RSI',
                        data: [],
                        borderColor: '#f39c12',
                        backgroundColor: 'rgba(243, 156, 18, 0.1)',
                        fill: false,
                        pointRadius: 0,
                        yAxisID: 'rsi'
                    },
                    {
                        label: 'MACD',
                        data: [],
                        borderColor: '#3498db',
                        backgroundColor: 'rgba(52, 152, 219, 0.1)',
                        fill: false,
                        pointRadius: 0,
                        yAxisID: 'macd'
                    },
                    {
                        label: 'Signal',
                        data: [],
                        borderColor: '#e74c3c',
                        backgroundColor: 'rgba(231, 76, 60, 0.1)',
                        fill: false,
                        pointRadius: 0,
                        yAxisID: 'macd'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: {
                    duration: 0
                },
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                layout: {
                    padding: {
                        top: 20,
                        right: 20,
                        bottom: 20,
                        left: 20
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            color: '#fff',
                            usePointStyle: true,
                            padding: 20,
                            font: {
                                size: 11
                            }
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
                    price: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: {
                            display: true,
                            text: 'Price',
                            color: '#fff'
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#fff'
                        }
                    },
                    rsi: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {
                            display: true,
                            text: 'RSI',
                            color: '#f39c12'
                        },
                        min: 0,
                        max: 100,
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#f39c12'
                        }
                    },
                    macd: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {
                            display: true,
                            text: 'MACD',
                            color: '#3498db'
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#3498db'
                        }
                    }
                }
            }
        });
    },

    updateChartData: function(chart, timestamp, price, indicators = null) {
        if (!chart) return;

        // Remove oldest data point if we exceed MAX_DATA_POINTS
        if (chart.data.labels.length >= 100) {
            chart.data.labels.shift();
            chart.data.datasets.forEach(dataset => dataset.data.shift());
        }

        // Add new data points
        chart.data.labels.push(timestamp);
        chart.data.datasets[0].data.push(price);

        // Update technical indicators
        if (indicators) {
            // Bollinger Bands
            if (typeof indicators.bb_upper === 'number') {
                chart.data.datasets[1].data.push(indicators.bb_upper);
            }
            if (typeof indicators.bb_lower === 'number') {
                chart.data.datasets[2].data.push(indicators.bb_lower);
            }

            // RSI
            if (typeof indicators.rsi === 'number') {
                chart.data.datasets[3].data.push(indicators.rsi);
            }

            // MACD
            if (typeof indicators.macd === 'number') {
                chart.data.datasets[4].data.push(indicators.macd);
            }
            if (typeof indicators.macd_signal === 'number') {
                chart.data.datasets[5].data.push(indicators.macd_signal);
            }
        }

        // Update chart with animation disabled
        chart.update('none');
    },

    updateIndicatorDisplays: function(data) {
        if (!data || !data.indicators) {
            // Set all indicators to N/A if no data
            ['rsiValue', 'macdValue', 'bbValue', 'stochRsiValue'].forEach(id => {
                const element = document.getElementById(id);
                if (element) element.textContent = 'N/A';
            });
            ['rsiSignal', 'macdSignal', 'bbSignal', 'stochRsiSignal'].forEach(id => {
                const element = document.getElementById(id);
                if (element) element.textContent = '';
            });
            return;
        }

        const indicators = data.indicators;

        // Update RSI
        if (typeof indicators.rsi === 'number') {
            const rsiElement = document.getElementById('rsiValue');
            const rsiSignal = document.getElementById('rsiSignal');
            if (rsiElement) rsiElement.textContent = indicators.rsi.toFixed(2);
            if (rsiSignal) {
                if (indicators.rsi > 70) {
                    rsiSignal.textContent = 'Overbought';
                    rsiSignal.className = 'indicator-signal bearish';
                } else if (indicators.rsi < 30) {
                    rsiSignal.textContent = 'Oversold';
                    rsiSignal.className = 'indicator-signal bullish';
                } else {
                    rsiSignal.textContent = 'Neutral';
                    rsiSignal.className = 'indicator-signal neutral';
                }
            }
        }

        // Update MACD
        if (typeof indicators.macd === 'number' && typeof indicators.macd_signal === 'number') {
            const macdElement = document.getElementById('macdValue');
            const macdSignal = document.getElementById('macdSignal');
            if (macdElement) {
                macdElement.textContent = `${indicators.macd.toFixed(6)} / ${indicators.macd_signal.toFixed(6)}`;
            }
            if (macdSignal) {
                if (indicators.macd > indicators.macd_signal) {
                    macdSignal.textContent = 'Bullish';
                    macdSignal.className = 'indicator-signal bullish';
                } else if (indicators.macd < indicators.macd_signal) {
                    macdSignal.textContent = 'Bearish';
                    macdSignal.className = 'indicator-signal bearish';
                } else {
                    macdSignal.textContent = 'Neutral';
                    macdSignal.className = 'indicator-signal neutral';
                }
            }
        }

        // Update Bollinger Bands
        if (typeof indicators.bb_upper === 'number' && typeof indicators.bb_lower === 'number') {
            const bbElement = document.getElementById('bbValue');
            const bbSignal = document.getElementById('bbSignal');
            if (bbElement) {
                bbElement.textContent = `${indicators.bb_lower.toFixed(6)} - ${indicators.bb_upper.toFixed(6)}`;
            }
            if (bbSignal && typeof data.rate === 'number') {
                if (data.rate > indicators.bb_upper) {
                    bbSignal.textContent = 'Overbought';
                    bbSignal.className = 'indicator-signal bearish';
                } else if (data.rate < indicators.bb_lower) {
                    bbSignal.textContent = 'Oversold';
                    bbSignal.className = 'indicator-signal bullish';
                } else {
                    bbSignal.textContent = 'Within Bands';
                    bbSignal.className = 'indicator-signal neutral';
                }
            }
        }

        // Update Stochastic RSI
        if (typeof indicators.stoch_rsi_k === 'number' && typeof indicators.stoch_rsi_d === 'number') {
            const stochElement = document.getElementById('stochRsiValue');
            const stochSignal = document.getElementById('stochRsiSignal');
            if (stochElement) {
                stochElement.textContent = `K:${indicators.stoch_rsi_k.toFixed(2)} D:${indicators.stoch_rsi_d.toFixed(2)}`;
            }
            if (stochSignal) {
                if (indicators.stoch_rsi_k > 80 && indicators.stoch_rsi_d > 80) {
                    stochSignal.textContent = 'Overbought';
                    stochSignal.className = 'indicator-signal bearish';
                } else if (indicators.stoch_rsi_k < 20 && indicators.stoch_rsi_d < 20) {
                    stochSignal.textContent = 'Oversold';
                    stochSignal.className = 'indicator-signal bullish';
                } else {
                    stochSignal.textContent = 'Neutral';
                    stochSignal.className = 'indicator-signal neutral';
                }
            }
        }
    }
};

// Technical Indicators Calculations

// Calculate RSI (Relative Strength Index)
function calculateRSI(prices, period = 14) {
    if (prices.length < period + 1) return null;

    let gains = 0;
    let losses = 0;

    // Calculate initial average gain and loss
    for (let i = 1; i <= period; i++) {
        const difference = prices[i] - prices[i - 1];
        if (difference >= 0) {
            gains += difference;
        } else {
            losses -= difference;
        }
    }

    let avgGain = gains / period;
    let avgLoss = losses / period;

    // Calculate RSI for the first period
    let rs = avgGain / avgLoss;
    let rsi = 100 - (100 / (1 + rs));

    // Calculate RSI for remaining periods
    for (let i = period + 1; i < prices.length; i++) {
        const difference = prices[i] - prices[i - 1];
        let currentGain = 0;
        let currentLoss = 0;

        if (difference >= 0) {
            currentGain = difference;
        } else {
            currentLoss = -difference;
        }

        avgGain = ((avgGain * (period - 1)) + currentGain) / period;
        avgLoss = ((avgLoss * (period - 1)) + currentLoss) / period;

        rs = avgGain / avgLoss;
        rsi = 100 - (100 / (1 + rs));
    }

    return rsi;
}

// Calculate MACD (Moving Average Convergence Divergence)
function calculateMACD(prices, fastPeriod = 12, slowPeriod = 26, signalPeriod = 9) {
    if (prices.length < slowPeriod + signalPeriod) return null;

    // Calculate EMAs
    const fastEMA = calculateEMA(prices, fastPeriod);
    const slowEMA = calculateEMA(prices, slowPeriod);

    // Calculate MACD line
    const macdLine = fastEMA.map((fast, i) => fast - slowEMA[i]);

    // Calculate Signal line
    const signalLine = calculateEMA(macdLine, signalPeriod);

    // Calculate Histogram
    const histogram = macdLine.map((macd, i) => macd - signalLine[i]);

    return {
        macd: macdLine[macdLine.length - 1],
        signal: signalLine[signalLine.length - 1],
        histogram: histogram[histogram.length - 1]
    };
}

// Calculate EMA (Exponential Moving Average)
function calculateEMA(prices, period) {
    const k = 2 / (period + 1);
    const ema = [prices[0]];

    for (let i = 1; i < prices.length; i++) {
        ema.push(prices[i] * k + ema[i - 1] * (1 - k));
    }

    return ema;
}

// Calculate Bollinger Bands
function calculateBollingerBands(prices, period = 20, multiplier = 2) {
    if (prices.length < period) return null;

    const sma = calculateSMA(prices, period);
    const stdDev = calculateStandardDeviation(prices, period);

    const upperBand = sma.map((value, i) => value + (multiplier * stdDev[i]));
    const lowerBand = sma.map((value, i) => value - (multiplier * stdDev[i]));

    return {
        middle: sma[sma.length - 1],
        upper: upperBand[upperBand.length - 1],
        lower: lowerBand[lowerBand.length - 1]
    };
}

// Calculate SMA (Simple Moving Average)
function calculateSMA(prices, period) {
    const sma = [];
    for (let i = period - 1; i < prices.length; i++) {
        const sum = prices.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
        sma.push(sum / period);
    }
    return sma;
}

// Calculate Standard Deviation
function calculateStandardDeviation(prices, period) {
    const stdDev = [];
    for (let i = period - 1; i < prices.length; i++) {
        const slice = prices.slice(i - period + 1, i + 1);
        const mean = slice.reduce((a, b) => a + b, 0) / period;
        const squareDiffs = slice.map(value => Math.pow(value - mean, 2));
        const avgSquareDiff = squareDiffs.reduce((a, b) => a + b, 0) / period;
        stdDev.push(Math.sqrt(avgSquareDiff));
    }
    return stdDev;
}

// Calculate Stochastic RSI
function calculateStochasticRSI(prices, period = 14, kPeriod = 3, dPeriod = 3) {
    if (prices.length < period + kPeriod + dPeriod) return null;

    // Calculate RSI values
    const rsiValues = [];
    for (let i = period; i < prices.length; i++) {
        const rsi = calculateRSI(prices.slice(i - period, i + 1), period);
        if (rsi !== null) {
            rsiValues.push(rsi);
        }
    }

    // Calculate %K
    const kValues = [];
    for (let i = kPeriod - 1; i < rsiValues.length; i++) {
        const slice = rsiValues.slice(i - kPeriod + 1, i + 1);
        const highest = Math.max(...slice);
        const lowest = Math.min(...slice);
        const current = slice[slice.length - 1];
        const k = ((current - lowest) / (highest - lowest)) * 100;
        kValues.push(k);
    }

    // Calculate %D
    const dValues = calculateSMA(kValues, dPeriod);

    return {
        k: kValues[kValues.length - 1],
        d: dValues[dValues.length - 1]
    };
}

// Export functions for use in other files
window.technicalIndicators = {
    calculateRSI,
    calculateMACD,
    calculateBollingerBands,
    calculateStochasticRSI
}; 